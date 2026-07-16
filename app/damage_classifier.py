import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from dotenv import load_dotenv
from PIL import Image
from transformers import pipeline
from ultralytics import YOLO

from app import config

load_dotenv()

logger = logging.getLogger(__name__)


HF_CLASS_MAP = {
    "Scratch": "minor_scratch",
    "Crack": "cracked",
    "Dent": "cracked",
    "Tire Flat": "broken",
    "Glass Shatter": "broken",
    "Lamp Broken": "broken",
}
YOLO_CLASS_MAP = {
    "scratch": "minor_scratch",
    "crack": "cracked",
    "dent": "cracked",
    "flat_tire": "broken",
    "shattered_glass": "broken",
    "broken_lamp": "broken",
}

GLASS_SHATTER_RAW_LABELS = {"Glass Shatter", "shattered_glass"}

NO_DAMAGE_EDGE_DENSITY = 0.02
MIN_MODEL_CONFIDENCE = 0.35
MIN_HF_MODEL_CONFIDENCE = 0.90


@dataclass
class ModelPrediction:
    category: str
    confidence: float
    raw_label: Optional[str] = None


@dataclass
class DamageResult:
    category: str
    confidence: float
    no_damage_prefilter: bool  
    backend: str  # "hf"  "yolo"
    raw_label: Optional[str] = None


class DamageClassifier:


    def __init__(
        self,
        hf_model_id: str = "beingamit99/car_damage_detection",
        yolo_weights_path: Optional[str] = None,
        yolo_conf: float = config.YOLO_CONFIDENCE_THRESHOLD,
    ):
        self._hf_pipe = None
        self._yolo = None
        self._yolo_conf = yolo_conf
        self._yolo_load_error: Optional[Exception] = None

        try:
            self._hf_pipe = pipeline("image-classification", model=hf_model_id, token=os.getenv("HF_TOKEN") or None)
        except Exception as exc:
            logger.warning("HF damage classifier failed to initialize: %s", exc)

        weights_path = Path(__file__).parent / (yolo_weights_path or config.YOLO_WEIGHTS_PATH)
        try:
            self._yolo = YOLO(str(weights_path))
        except Exception as exc:
            self._yolo_load_error = exc
            logger.warning("YOLO damage classifier failed to initialize: %s", exc)

    def classify(self, image_or_path, backend: str = "hf") -> DamageResult:
        image = self._to_pil(image_or_path)
        edge_density = self._edge_density(image)

       
        if edge_density < NO_DAMAGE_EDGE_DENSITY:
            return DamageResult(
                category="no_damage",
                confidence=1.0 - edge_density,
                no_damage_prefilter=True,
                backend=backend,
            )

        pred = self._classify_yolo(image) if backend == "yolo" else self._classify_hf(image)
        min_confidence = MIN_HF_MODEL_CONFIDENCE if backend == "hf" else MIN_MODEL_CONFIDENCE
        if pred.confidence < min_confidence:
            pred = ModelPrediction(category="no_damage", confidence=pred.confidence, raw_label=pred.raw_label)

        return DamageResult(
            category=pred.category,
            confidence=pred.confidence,
            no_damage_prefilter=False,
            backend=backend,
            raw_label=pred.raw_label,
        )

    # ---- backend-specific ----

    def _classify_hf(self, image: Image.Image) -> ModelPrediction:
        if self._hf_pipe is None:
            return ModelPrediction(category="no_damage", confidence=0.0, raw_label=None)

        predictions = self._hf_pipe(image)  # sorted by score, descending
        top = predictions[0]
        raw_label, score = top["label"], top["score"]
        return ModelPrediction(category=HF_CLASS_MAP.get(raw_label, "no_damage"), confidence=score, raw_label=raw_label)

    def _classify_yolo(self, image: Image.Image) -> ModelPrediction:
        if self._yolo is None:
            return self._classify_hf(image)

        try:
            results = self._yolo(image, save=False, conf=self._yolo_conf, verbose=False)
        except Exception as exc:
            logger.warning("YOLO inference failed; falling back to HF classifier: %s", exc)
            return self._classify_hf(image)

        best_label, best_score = None, 0.0
        for r in results:
            for box in r.boxes:
                score = float(box.conf[0])
                if score > best_score:
                    best_score = score
                    best_label = r.names[int(box.cls[0])]
        if best_label is None:
            return ModelPrediction(category="no_damage", confidence=0.0, raw_label=None)
        return ModelPrediction(
            category=YOLO_CLASS_MAP.get(best_label, "no_damage"), confidence=best_score, raw_label=best_label
        )

    # ---- helpers ----

    def _to_pil(self, image_or_path) -> Image.Image:
        if isinstance(image_or_path, Image.Image):
            return image_or_path.convert("RGB")
        return Image.open(image_or_path).convert("RGB")

    def _edge_density(self, image: Image.Image) -> float:
        gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, threshold1=50, threshold2=150)
        return float(np.count_nonzero(edges)) / edges.size
