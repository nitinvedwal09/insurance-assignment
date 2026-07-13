import asyncio
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from app import config, storage
from app.agent import AgentSession
from app.bandit import Choice, bandit
from app.damage_classifier import DamageClassifier
from app.llm_client import generate_answer
from app.ocr_pipeline import OCRPipeline
from app.rag import RagIndex
from app.vin_lookup import VinRegistry
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file, if present

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="SmartInspect Self-Optimizing Claims Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_damage_classifier: Optional[DamageClassifier] = None
_ocr_pipeline: Optional[OCRPipeline] = None
_rag_index: Optional[RagIndex] = None
_vin_registry: Optional[VinRegistry] = None


@app.on_event("startup")
def load_models():
    global _damage_classifier, _ocr_pipeline, _rag_index, _vin_registry

    try:
        _damage_classifier = DamageClassifier()
    except Exception as exc:
        logger.warning("Damage classifier initialization failed: %s", exc)
        _damage_classifier = None

    try:
        _ocr_pipeline = OCRPipeline()
    except Exception as exc:
        logger.warning("OCR pipeline initialization failed: %s", exc)
        _ocr_pipeline = None

    try:
        _rag_index = RagIndex()
    except Exception as exc:
        logger.warning("RAG index initialization failed: %s", exc)
        _rag_index = None

    try:
        _vin_registry = VinRegistry()
    except Exception as exc:
        logger.warning("VIN registry initialization failed: %s", exc)
        _vin_registry = None


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/query")
async def query(query: Optional[str] = Form(None), image: Optional[UploadFile] = File(None)):
    image_bytes = await image.read() if image is not None else None
    query_text = (query or "").strip()
    if not query_text and not image_bytes:
        return JSONResponse({"error": "Provide a question, a photo, or both."}, status_code=400)

    transaction_id = storage.new_transaction_id()
    total_start = time.perf_counter()

    image_path = None
    pil_image = None
    if image_bytes is not None:
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        suffix = f".{pil_image.format.lower()}" if pil_image.format else ".jpg"
        image_path = storage.save_image(transaction_id, image_bytes, suffix)


    session = AgentSession(
        transaction_id=transaction_id,
        query=query_text,
        pil_image=pil_image,
        damage_classifier=_damage_classifier,
        ocr_pipeline=_ocr_pipeline,
        rag_index=_rag_index,
        vin_registry=_vin_registry,
    )
    await session.run()


    rag_hits = session.rag_hits
    has_other_grounding = bool(session.policy_payload or session.escalation_payload)
    rag_grounded = has_other_grounding or (
        bool(rag_hits) and max(hit["score"] for hit in rag_hits) >= config.RAG_CONFIDENCE_THRESHOLD
    )

    llm_choice = bandit.choose("llm", session.context(), config.LLM_CHOICES)
    session.bandit_choices.append(llm_choice)

    llm_start = time.perf_counter()
    answer = ""
    try:
        answer = await generate_answer(
            query_text,
            model=llm_choice.action,
            damage_category=session.damage_category,
            label_info=session.ocr_payload,
            rag_chunks=[hit["text"] for hit in rag_hits],
            has_image=pil_image is not None,
            rag_grounded=rag_grounded,
            policy_info=session.policy_payload,
            escalation_info=session.escalation_payload,
        )
    except httpx.HTTPError as exc:
        return JSONResponse({"error": f"LLM request failed: {exc}"}, status_code=502)

    latencies_ms = session.latencies_ms
    latencies_ms["llm_ms"] = (time.perf_counter() - llm_start) * 1000
    latencies_ms["total_ms"] = (time.perf_counter() - total_start) * 1000

    config_used = {
        "llm_model": llm_choice.action,
        "ocr_engine": next((c.action for c in session.bandit_choices if c.decision_point == "ocr"), None),
        "rag_top_k": next((c.action for c in session.bandit_choices if c.decision_point == "topk"), None),
        "damage_backend": next((c.action for c in session.bandit_choices if c.decision_point == "damage"), None),
    }

    await asyncio.to_thread(
        storage.create_transaction,
        transaction_id,
        query_text,
        image_path,
        session.damage_payload,
        session.ocr_payload,
        session.policy_payload,
        session.escalation_payload,
        answer,
        latencies_ms,
        config_used,
        [c.__dict__ for c in session.bandit_choices],
    )

    return {
        "transaction_id": transaction_id,
        "answer": answer,
        "damage_category": session.damage_category,
        "ocr_text": session.ocr_payload,
        "policy": session.policy_payload,
        "escalation": session.escalation_payload,
        "config_used": config_used,
        "latency_ms": latencies_ms,
        "agent_steps": session.steps,
    }


class FeedbackPayload(BaseModel):
    transaction_id: str
    score: int  # 1 = helpful, 0 = unhelpful


@app.post("/feedback")
async def submit_feedback(payload: FeedbackPayload):
    if payload.score not in (0, 1):
        return JSONResponse({"error": "score must be 0 or 1"}, status_code=400)

    transaction = await asyncio.to_thread(storage.get_transaction, payload.transaction_id)
    if transaction is None:
        return JSONResponse({"error": "unknown transaction_id"}, status_code=404)

    await asyncio.to_thread(storage.save_feedback, payload.transaction_id, payload.score)

    latencies_ms = json.loads(transaction["latencies_ms"] or "{}")
    bandit_choices_raw = json.loads(transaction["bandit_choices"] or "[]")
    # Only the latency actually attributable to a bandit-controlled step counts against
    # it -- agent_ms (fixed tool-selection model) would otherwise swamp the signal from
    # the damage backend / OCR engine / RAG top-K / answer LLM choices the bandit is
    # actually learning between. damage_ms is included now that the damage backend
    # (hf vs yolo) is itself a bandit-controlled arm.
    configured_seconds = sum(latencies_ms.get(k, 0) for k in ("damage_ms", "ocr_ms", "rag_ms", "llm_ms")) / 1000

    # Reward blends user feedback with execution latency: a helpful answer scores +80
    # before the latency penalty, an unhelpful one scores 0 before it. +80 (vs. +10)
    # keeps the feedback signal dominant over latency, which otherwise runs into the
    # single-digit seconds for the slower arms (e.g. the 1.5b LLM, PaddleOCR).
    reward = (payload.score * 80) - configured_seconds
    choices = [Choice(**c) for c in bandit_choices_raw]
    bandit.record_reward(choices, reward)

    return {"status": "ok", "reward": reward}


@app.get("/bandit/state")
def bandit_state():
    return storage.all_arm_stats()
