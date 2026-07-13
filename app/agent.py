import asyncio
import json
import time
from typing import Optional

import httpx
from PIL import Image

from app import config
from app.bandit import Choice, bandit
from app.damage_classifier import GLASS_SHATTER_RAW_LABELS, DamageClassifier
from app.image_regions import crop_plate_region, mask_plate_region
from app.ocr_pipeline import OCRPipeline
from app.rag import RagIndex
from app.vin_lookup import VinRegistry, extract_label_fields, serialize_policy

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "query_knowledge_base",
            "description": (
                "Search the claims knowledge base (coverage policy, repair procedures, "
                "escalation rules) for passages relevant to a question."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The question to search for."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": (
                "Run damage classification and label OCR on the photo attached to this "
                "request. Only callable when a photo was actually attached."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_warranty_status",
            "description": (
                "Look up a serial/VIN number against the insurance policy registry to "
                "check coverage status. Uses the serial/VIN read from the photo if one "
                "was extracted; pass one explicitly if the customer typed it instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "serial_number": {
                        "type": "string",
                        "description": "Serial/VIN to check; omit to use the one already extracted from the photo.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Flag this case for a human adjuster instead of resolving it autonomously. "
                "Call this whenever escalation_rules.md's mandatory triggers apply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger": {"type": "string", "description": "Which escalation trigger fired, in a few words."},
                    "recommended_action": {
                        "type": "string",
                        "description": (
                            "One-line message written directly to the customer (the vehicle owner) "
                            "telling them what to do and what to expect next, e.g. 'Please avoid "
                            "driving until this is repaired -- we'll confirm your coverage shortly.'"
                        ),
                    },
                },
                "required": ["trigger", "recommended_action"],
            },
        },
    },
]


class AgentSession:
    """Drives the ReAct-style tool-selection loop for one /query request.

    AGENT_MODEL (a local tool-calling model) decides which tool to call and in what
    order; this class executes whatever it asks for. The RAG top-K, OCR engine, and
    final-answer LLM used along the way are chosen by the contextual bandit (see
    bandit.py) rather than being fixed, and every choice made is recorded in
    self.bandit_choices so main.py can apply the /feedback reward to the right arms.
    """

    def __init__(
        self,
        transaction_id: str,
        query: str,
        pil_image: Optional[Image.Image],
        damage_classifier: DamageClassifier,
        ocr_pipeline: OCRPipeline,
        rag_index: RagIndex,
        vin_registry: VinRegistry,
    ):
        self.transaction_id = transaction_id
        self.query = query
        self._pil_image = pil_image
        self._damage_classifier = damage_classifier
        self._ocr_pipeline = ocr_pipeline
        self._rag_index = rag_index
        self._vin_registry = vin_registry

        self.damage_category: Optional[str] = None
        self.damage_payload: Optional[dict] = None
        self.ocr_payload: Optional[dict] = None
        self.policy_payload: Optional[dict] = None
        self.rag_hits: list = []
        self.escalated = False
        self.escalation_payload: Optional[dict] = None
        self.latencies_ms: dict = {}
        self.bandit_choices: list[Choice] = []
        self.steps: list[dict] = []
        self._image_analyzed = False

    def context(self) -> str:
        return self.damage_category or "none"

    async def run(self) -> None:
        agent_start = time.perf_counter()
        messages = [
            {"role": "system", "content": config.AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self.query
                if self.query
                else "(No question was asked -- a photo was uploaded. Decide what's worth looking into before describing it.)",
            },
        ]
        if self._pil_image is None:
            messages.append({"role": "system", "content": "Note: no photo was attached to this request."})

        settled = False
        for _ in range(config.MAX_AGENT_STEPS):
            message = await self._call_model(messages)
            if message.get("thinking"):
                self.steps.append({"type": "thought", "text": message["thinking"]})

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                settled = True
                break

            messages.append(message)
            for call in tool_calls:
                fn = call["function"]
                await self._force_tool_call(fn["name"], fn.get("arguments") or {}, messages)

        if not settled:
            # Loop exhausted MAX_AGENT_STEPS without the model settling on an answer --
            # don't let a confused small-model loop silently drop the case.
            await self._force_tool_call(
                "escalate_to_human",
                {"trigger": "reasoning loop limit reached", "recommended_action": "Manual review needed."},
                messages,
            )
        elif self._pil_image is not None and not self._image_analyzed:
            # A small tool-calling model can settle on an answer without ever looking at
            # an attached photo, silently ignoring evidence that was right there --
            # force one analyze_image call and give it one more turn to react to it.
            await self._force_tool_call("analyze_image", {}, messages)
            message = await self._call_model(messages)
            if message.get("thinking"):
                self.steps.append({"type": "thought", "text": message["thinking"]})
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                messages.append(message)
                for call in tool_calls:
                    fn = call["function"]
                    await self._force_tool_call(fn["name"], fn.get("arguments") or {}, messages)

        # The tool-calling model doesn't reliably call query_knowledge_base on its own --
        # with a query present it often burns its MAX_AGENT_STEPS budget on analyze_image
        # and settles before ever searching the KB, and with no query there's nothing for
        # the tool's argument to come from in the first place. Either way the final answer
        # ends up ungrounded and the answer LLM improvises instead of using repair-procedure
        # text, so force one lookup whenever nothing was retrieved yet.
        if not self.rag_hits:
            if self.query and self.damage_category:
                fallback_query = f"{self.query} ({self.damage_category} damage)"
            elif self.query:
                fallback_query = self.query
            elif self.damage_category:
                fallback_query = f"repair steps for {self.damage_category} damage"
            else:
                fallback_query = None
            if fallback_query:
                await self._force_tool_call("query_knowledge_base", {"query": fallback_query}, messages)

        self.latencies_ms["agent_ms"] = (time.perf_counter() - agent_start) * 1000

    async def _call_model(self, messages: list[dict]) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                config.OLLAMA_URL,
                json={
                    "model": config.AGENT_MODEL,
                    "messages": messages,
                    "tools": TOOL_SCHEMAS,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
            )
            response.raise_for_status()
            return response.json().get("message", {})

    async def _force_tool_call(self, name: str, args: dict, messages: list[dict]) -> None:
        self.steps.append({"type": "tool_call", "tool": name, "args": args})
        observation = await self._execute_tool(name, args)
        self.steps.append({"type": "tool_result", "tool": name, "result": observation})
        messages.append({"role": "tool", "content": json.dumps(observation)})

    async def _execute_tool(self, name: str, args: dict) -> dict:
        if name == "query_knowledge_base":
            return await self._tool_query_knowledge_base(args.get("query", self.query))
        if name == "analyze_image":
            return await self._tool_analyze_image()
        if name == "check_warranty_status":
            return self._tool_check_warranty_status(args.get("serial_number"))
        if name == "escalate_to_human":
            return self._tool_escalate_to_human(args.get("trigger", ""), args.get("recommended_action", ""))
        return {"error": f"Unknown tool '{name}'"}

    async def _tool_query_knowledge_base(self, query: str) -> dict:
        if self._rag_index is None:
            return {"error": "RAG knowledge base is unavailable right now."}

        top_k_choice = bandit.choose("topk", self.context(), [str(k) for k in config.RAG_TOPK_CHOICES])
        self.bandit_choices.append(top_k_choice)
        top_k = int(top_k_choice.action)

        start = time.perf_counter()
        hits = await asyncio.to_thread(self._rag_index.query, query, top_k)
        self.latencies_ms["rag_ms"] = self.latencies_ms.get("rag_ms", 0) + (time.perf_counter() - start) * 1000
        self.rag_hits = hits
        return {"hits": hits, "top_k_used": top_k}

    async def _tool_analyze_image(self) -> dict:
        if self._pil_image is None:
            return {"error": "No photo was attached to this request."}
        if self._image_analyzed:
            return {"damage": self.damage_payload, "label": self.ocr_payload}
        if self._damage_classifier is None or self._ocr_pipeline is None:
            return {"error": "Image analysis is unavailable right now."}

        if config.CROP_VIN_PLATE_REGION:
            damage_image = mask_plate_region(self._pil_image, config.VIN_PLATE_REGION_FRACTION)
            ocr_image = crop_plate_region(self._pil_image, config.VIN_PLATE_REGION_FRACTION)
        else:
            damage_image = self._pil_image
            ocr_image = self._pil_image

        # Damage classification runs first (independent of OCR engine choice) so its
        # category can serve as the bandit context for the OCR-engine decision below.
        # Its own bandit context is the query's presence/absence -- the damage category
        # isn't known yet at this point, so it can't serve as its own context.
        damage_backend_choice = bandit.choose(
            "damage", "has_query" if self.query else "no_query", config.DAMAGE_BACKENDS
        )
        self.bandit_choices.append(damage_backend_choice)

        damage_start = time.perf_counter()
        damage_result = await asyncio.to_thread(
            self._damage_classifier.classify, damage_image, damage_backend_choice.action
        )
        self.latencies_ms["damage_ms"] = (time.perf_counter() - damage_start) * 1000

        self.damage_category = damage_result.category
        self.damage_payload = {
            "category": damage_result.category,
            "confidence": damage_result.confidence,
            "no_damage_prefilter": damage_result.no_damage_prefilter,
            "backend": damage_result.backend,
            "raw_label": damage_result.raw_label,
        }

        ocr_choice = bandit.choose("ocr", self.context(), config.OCR_ENGINES)
        self.bandit_choices.append(ocr_choice)

        ocr_start = time.perf_counter()
        ocr_result = await asyncio.to_thread(self._ocr_pipeline.read, ocr_image, ocr_choice.action)
        self.latencies_ms["ocr_ms"] = (time.perf_counter() - ocr_start) * 1000

        fields = extract_label_fields(ocr_result.text)
        self.ocr_payload = fields if (fields["vin"] or fields["year"]) else None

        self._image_analyzed = True

        # escalation_rules.md marks Glass Shatter as a mandatory, always-escalate safety
        # trigger (visibility/driving risk) -- too important to leave to the small
        # agent model remembering to call escalate_to_human on its own. Checked against
        # the raw model label (from whichever backend the bandit picked) since "broken"
        # (the collapsed category) also covers flat tires and broken lamps, which aren't
        # safety-critical the same way.
        if damage_result.raw_label in GLASS_SHATTER_RAW_LABELS and not self.escalated:
            self._tool_escalate_to_human(
                "Glass Shatter (safety-relevant damage)",
                "For your safety, please avoid driving until this is repaired -- shattered glass can "
                "compromise your visibility and the vehicle's security. We're escalating your claim to "
                "a specialist to confirm your coverage and get your replacement scheduled.",
            )

        return {"damage": self.damage_payload, "label": self.ocr_payload, "ocr_engine_used": ocr_choice.action}

    def _tool_check_warranty_status(self, serial_number: Optional[str]) -> dict:
        if self._vin_registry is None:
            return {"error": "VIN registry lookup is unavailable right now."}

        vin = serial_number or (self.ocr_payload or {}).get("vin")
        if not vin:
            return {"error": "No serial/VIN available to check."}
        policy_info = self._vin_registry.resolve(vin)
        if not policy_info:
            return {"error": f"No policy on file for serial/VIN {vin}."}
        self.policy_payload = serialize_policy(policy_info)
        return self.policy_payload

    def _tool_escalate_to_human(self, trigger: str, recommended_action: str) -> dict:
        # Prefer the policy lookup's VIN (confirmed against the registry) but fall back
        # to the raw OCR read -- escalation can fire (e.g. Glass Shatter) before/without
        # check_warranty_status ever being called, so policy_payload alone would report
        # "unreadable" even when OCR did extract a VIN.
        vin = (self.policy_payload or {}).get("vin") or (self.ocr_payload or {}).get("vin") or "unreadable"
        summary = {
            "transaction_id": self.transaction_id,
            "damage_category": self.damage_category,
            "damage_confidence": self.damage_payload["confidence"] if self.damage_payload else None,
            "vin": vin,
            "trigger": trigger,
            "recommended_action": recommended_action,
        }
        self.escalated = True
        self.escalation_payload = summary
        return summary
