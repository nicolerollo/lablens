from __future__ import annotations

import logging
import re

from .parser import ParsedPanel

logger = logging.getLogger(__name__)

# regional-hospital-style portal exports use a third distinct layout: a "=== PANEL ===" banner
# header followed by key=value rows with an inline "(range ...)" annotation. This is the third
# source-specific parser (alongside parser.py and academic_medical_center_parser.py), proving the registry pattern
# in sources.py generalizes to more than two formats without touching downstream code.
PANEL_HEADER_RE = re.compile(
    r"^===\s*(?P<panel>[A-Z0-9 ,/&()\-]+?)\s*===\s*Date:\s*(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.MULTILINE,
)

ROW_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ,.\-]*?)\s*=\s*"
    r"(?P<value>[A-Za-z0-9.<>+-]+)"
    r"(?:\s+(?P<unit>[A-Za-z%/0-9.^]+))?\s*"
    r"\(range\s*(?P<ref>.+?)\)\s*$",
    re.IGNORECASE,
)


def parse_regional_hospital_text(text: str) -> list[ParsedPanel]:
    """Parse regional-hospital-style extracted PDF text into the shared ParsedPanel shape."""
    panels: list[ParsedPanel] = []
    current: ParsedPanel | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        header = PANEL_HEADER_RE.match(line)
        if header:
            current = ParsedPanel(
                panel=header.group("panel").strip().upper(),
                collection_date=header.group("date"),
                rows=[],
            )
            panels.append(current)
            continue

        row = ROW_RE.match(line)
        if row:
            if not current:
                logger.warning("Skipping regional-hospital-style result row found before any panel header: %r", line)
                continue
            ref = row.group("ref").strip()
            unit = row.group("unit")
            ref_range_raw = f"{ref} {unit}".strip() if unit else ref
            current.rows.append(
                {
                    "test_name_raw": row.group("name").strip(),
                    "value_raw": row.group("value").strip(),
                    "ref_range_raw": ref_range_raw,
                    "source_page": None,
                    "confidence": 0.85,
                }
            )
            continue

        logger.warning("Skipping unparsable regional-hospital-style line: %r", line)

    return panels


def looks_like_regional_hospital(text: str) -> bool:
    """Heuristic format detector used by sources.detect_source_system()."""
    return bool(PANEL_HEADER_RE.search(text))
