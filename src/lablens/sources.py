from __future__ import annotations

from typing import Callable

from .parser import ParsedPanel, parse_extracted_text, looks_like_military_health
from .academic_medical_center_parser import parse_academic_medical_center_text, looks_like_academic_medical_center
from .regional_hospital_parser import parse_regional_hospital_text, looks_like_regional_hospital

# Registry of source-specific parsers. Each fragmented healthcare system (a military health system,
# an academic medical center, a regional hospital, ...) exports PDFs in its own layout. LabLens
# keeps one small parser per source format and funnels all of them into the same
# ParsedPanel -> normalize_row() -> database pipeline, instead of trying to write one
# parser that handles every layout.
SOURCE_PARSERS: dict[str, Callable[[str], list[ParsedPanel]]] = {
    "military_health_style": parse_extracted_text,
    "academic_medical_center_style": parse_academic_medical_center_text,
    "regional_hospital_style": parse_regional_hospital_text,
}

# Cheap format detectors -- each just checks whether that source's header pattern appears
# anywhere in the text. This is intentionally simple: it lets the demo and tests show
# auto-detection without claiming to robustly classify arbitrary, unseen PDF export layouts.
_DETECTORS: dict[str, Callable[[str], bool]] = {
    "military_health_style": looks_like_military_health,
    "academic_medical_center_style": looks_like_academic_medical_center,
    "regional_hospital_style": looks_like_regional_hospital,
}


def parse_by_source(text: str, source_system: str) -> list[ParsedPanel]:
    try:
        parser_fn = SOURCE_PARSERS[source_system]
    except KeyError as exc:
        raise ValueError(
            f"Unknown source_system '{source_system}'. Known parsers: {sorted(SOURCE_PARSERS)}"
        ) from exc
    return parser_fn(text)


def detect_source_system(text: str) -> str | None:
    """Guess which source format `text` is, based on each parser's header pattern.

    Returns the matching source_system key, or None if zero or more than one format
    matched (ambiguous input should be handled explicitly by the caller, not guessed at).
    """
    matches = [name for name, detector in _DETECTORS.items() if detector(text)]
    return matches[0] if len(matches) == 1 else None


def parse_auto(text: str) -> tuple[str, list[ParsedPanel]]:
    """Detect the source format and parse it. Raises ValueError if detection is ambiguous."""
    source_system = detect_source_system(text)
    if source_system is None:
        raise ValueError(
            "Could not confidently detect a single source format for this text. "
            "Call parse_by_source(text, source_system) with an explicit source_system instead."
        )
    return source_system, parse_by_source(text, source_system)
