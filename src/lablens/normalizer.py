from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional
import re

@dataclass
class NormalizedLabResult:
    panel: str
    collection_date: str
    test_name_raw: str
    value_raw: str
    numeric_value: Optional[float]
    qualitative_value: Optional[str]
    unit_raw: Optional[str]
    ref_range_raw: Optional[str]
    ref_low: Optional[float]
    ref_high: Optional[float]
    ref_comparator: Optional[str]
    interpretation: str
    source_page: Optional[int] = None
    confidence: float = 0.80
    # Populated later by database.resolve_canonical_test() once a DB connection is available --
    # see docs/database.md "Alias mapping is database-driven, not hardcoded". This module never
    # guesses a canonical name; lab_test_aliases is the only source of truth for that mapping.
    canonical_test_name: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def parse_numeric(value: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group(0)) if match else None


def parse_reference_range(raw: str | None) -> tuple[Optional[float], Optional[float], Optional[str]]:
    if not raw:
        return None, None, None

    cleaned = raw.strip()
    range_match = re.search(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", cleaned)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2)), "range"

    less_than = re.search(r"<\s*(-?\d+(?:\.\d+)?)", cleaned)
    if less_than:
        return None, float(less_than.group(1)), "<"

    greater_than = re.search(r">\s*(-?\d+(?:\.\d+)?)", cleaned)
    if greater_than:
        return float(greater_than.group(1)), None, ">"

    return None, None, "qualitative"


QUALITATIVE_ABNORMAL_TERMS = {
    "DETECTED",
    "POSITIVE",
    "REACTIVE",
    "ABNORMAL",
    "PRESENT",
}
QUALITATIVE_NORMAL_TERMS = {
    "NOT DETECTED",
    "NEGATIVE",
    "NON-REACTIVE",
    "NONREACTIVE",
    "NORMAL",
    "ABSENT",
}


def interpret_qualitative(value: str) -> str:
    """Classify a qualitative result so abnormal findings (e.g. a positive
    pathogen test) cannot be silently dropped alongside benign ones."""
    key = re.sub(r"\s+", " ", value.strip().upper())
    if key in QUALITATIVE_ABNORMAL_TERMS:
        return "qualitative_abnormal"
    if key in QUALITATIVE_NORMAL_TERMS:
        return "qualitative_normal"
    return "qualitative_indeterminate"


def interpret_value(value: Optional[float], low: Optional[float], high: Optional[float]) -> str:
    if value is None:
        return "qualitative"
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


def split_ref_and_unit(ref_range: str | None) -> tuple[Optional[str], Optional[str]]:
    if not ref_range:
        return None, None
    # Keep the original full range as source truth, but guess the unit for convenience.
    unit_match = re.search(r"(?:\d|>|<)\s*([A-Za-z%/\^0-9.]+(?:/[A-Za-z0-9.]+)?)\s*$", ref_range.strip())
    unit = unit_match.group(1) if unit_match else None
    return ref_range.strip(), unit


def normalize_row(panel: str, collection_date: str, raw_row: dict) -> NormalizedLabResult:
    value_raw = str(raw_row.get("value_raw", "")).strip()
    ref_range_raw, inferred_unit = split_ref_and_unit(raw_row.get("ref_range_raw"))
    numeric_value = parse_numeric(value_raw)
    qualitative_value = None if numeric_value is not None else value_raw
    ref_low, ref_high, comparator = parse_reference_range(ref_range_raw)

    return NormalizedLabResult(
        panel=panel,
        collection_date=collection_date,
        test_name_raw=raw_row["test_name_raw"].strip(),
        value_raw=value_raw,
        numeric_value=numeric_value,
        qualitative_value=qualitative_value,
        unit_raw=raw_row.get("unit_raw") or inferred_unit,
        ref_range_raw=ref_range_raw,
        ref_low=ref_low,
        ref_high=ref_high,
        ref_comparator=comparator,
        interpretation=(
            interpret_value(numeric_value, ref_low, ref_high)
            if numeric_value is not None
            else interpret_qualitative(qualitative_value)
        ),
        source_page=raw_row.get("source_page"),
        confidence=float(raw_row.get("confidence", 0.80)),
    )
