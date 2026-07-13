from dataclasses import dataclass, field
from typing import Optional, Union

import numpy as np
from PIL import Image

MIN_TEXT_CONFIDENCE = 0.35

ImageInput = Union[str, Image.Image, np.ndarray]


@dataclass
class TextDetection:
    text: str
    confidence: float
    source: str  # "easyocr" | "paddleocr" | "rapidocr"


@dataclass
class OCRResult:
    text: str  
    confidence: float  
    source: str  # "easyocr" | "paddleocr" | "rapidocr" 
    detections: list[TextDetection] = field(default_factory=list)


class OCRPipeline:

    def __init__(
        self,
        load_easyocr: bool = True,
        load_paddleocr: bool = True,
        load_rapidocr: bool = True,
        languages: tuple[str, ...] = ("en",),
    ):
        self._easyocr_reader = None
        if load_easyocr:
            import easyocr

            self._easyocr_reader = easyocr.Reader(list(languages), gpu=False)

        self._paddle_ocr = None
        if load_paddleocr:
            from paddleocr import PaddleOCR

            self._paddle_ocr = PaddleOCR(use_textline_orientation=True, lang="en", enable_mkldnn=False)

        self._rapid_ocr = None
        if load_rapidocr:
            from rapidocr_onnxruntime import RapidOCR

            self._rapid_ocr = RapidOCR()

    def read(
        self,
        image_or_path: ImageInput,
        backend: str = "all",
        min_confidence: float = MIN_TEXT_CONFIDENCE,
    ) -> OCRResult:
        detections: list[TextDetection] = []
        if backend in ("easyocr", "all") and self._easyocr_reader is not None:
            detections.extend(self._read_easyocr(image_or_path, min_confidence))
        if backend in ("paddleocr", "all") and self._paddle_ocr is not None:
            detections.extend(self._read_paddleocr(image_or_path, min_confidence))
        if backend in ("rapidocr", "all") and self._rapid_ocr is not None:
            detections.extend(self._read_rapidocr(image_or_path, min_confidence))

        if not detections:
            return OCRResult(text="", confidence=0.0, source="none")

        text = " ".join(d.text for d in detections)
        avg_confidence = sum(d.confidence for d in detections) / len(detections)
        source = "ensemble" if backend == "all" else backend
        return OCRResult(text=text, confidence=avg_confidence, source=source, detections=detections)

    # ---- backend-specific ----

    def _read_easyocr(self, image_or_path: ImageInput, min_confidence: float) -> list[TextDetection]:
        results = self._easyocr_reader.readtext(self._to_array(image_or_path))
        return [
            TextDetection(text=text, confidence=score, source="easyocr")
            for _, text, score in results
            if score >= min_confidence
        ]

    def _read_paddleocr(self, image_or_path: ImageInput, min_confidence: float) -> list[TextDetection]:
        results = self._paddle_ocr.ocr(self._to_array(image_or_path))
        out = []
        for page in results or []:
            texts, scores = page["rec_texts"], page["rec_scores"]
            for text, score in zip(texts, scores):
                if score >= min_confidence:
                    out.append(TextDetection(text=text, confidence=score, source="paddleocr"))
        return out

    def _read_rapidocr(self, image_or_path: ImageInput, min_confidence: float) -> list[TextDetection]:
        results, _ = self._rapid_ocr(self._to_array(image_or_path))
        out = []
        for _, text, score in results or []:
            if score >= min_confidence:
                out.append(TextDetection(text=text, confidence=score, source="rapidocr"))
        return out

    # ---- helpers ----

    def _to_array(self, image_or_path: ImageInput) -> np.ndarray:
        if isinstance(image_or_path, np.ndarray):
            return image_or_path
        if isinstance(image_or_path, Image.Image):
            return np.array(image_or_path.convert("RGB"))
        return np.array(Image.open(image_or_path).convert("RGB"))


if __name__ == "__main__":
    import sys
    import time

    img_path = sys.argv[1] if len(sys.argv) > 1 else r"C:\projects\assignment\files\vin_1FTFW1ET1EFA71234.png"

    pipeline = OCRPipeline()
    st = time.time()
    result = pipeline.read(img_path, backend="all")
    print(f"Time taken: {time.time() - st:.2f}s")
    print(f"Merged text: {result.text}")
    print(f"Avg confidence: {result.confidence:.2%}")
    for d in result.detections:
        print(f"  [{d.source}] {d.text!r} ({d.confidence:.2%})")
