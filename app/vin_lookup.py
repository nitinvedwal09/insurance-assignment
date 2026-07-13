import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "vin_registry.json"

# VINs are 17 chars, excluding I, O, Q (easily confused with 1, 0).
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def extract_label_fields(ocr_text: Optional[str]) -> dict:
    """Pull just a VIN and a year (of manufacture/purchase) out of raw OCR text."""
    if not ocr_text:
        return {"vin": None, "year": None}
    vin_match = VIN_RE.search(ocr_text.upper())
    year_match = YEAR_RE.search(ocr_text)
    return {
        "vin": vin_match.group(0) if vin_match else None,
        "year": int(year_match.group(0)) if year_match else None,
    }


@dataclass
class PolicyInfo:
    vin: str
    make: str
    model: str
    year: int
    last_covered: int


class VinRegistry:
    """Resolves a VIN against the mock policy database in data/vin_registry.json."""

    def __init__(self, path: Path = REGISTRY_PATH):
        self._records: dict = json.loads(path.read_text()) if path.exists() else {}

    def resolve(self, vin: Optional[str]) -> Optional[PolicyInfo]:
        if not vin:
            return None
        record = self._records.get(vin.upper())
        if not record:
            return None
        return PolicyInfo(
            vin=vin.upper(),
            make=record["make"],
            model=record["model"],
            year=record["year"],
            last_covered=record["last_covered"],
        )


def serialize_policy(policy: PolicyInfo) -> dict:
    return asdict(policy)
