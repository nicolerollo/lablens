from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from .normalizer import normalize_row, NormalizedLabResult

logger = logging.getLogger(__name__)

PANEL_HEADER_RE = re.compile(
    r"^(?P<panel>[A-Z0-9 ,/&()\-]+?)\s+-\s+Final result\s+\((?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.MULTILINE,
)

# Expected synthetic/extracted line format:
# WBC | 7.2 | 4.0 - 11.0 K/uL
# Rows are pipe-delimited after text/table extraction.
# Example: WBC | 7.2 | 4.0 - 11.0 K/uL | 10

@dataclass
class ParsedPanel:
    panel: str
    collection_date: str
    rows: list[dict]


def parse_extracted_text(text: str) -> list[ParsedPanel]:
    panels: list[ParsedPanel] = []
    current: ParsedPanel | None = None

    for line in text.splitlines():
        line = line.strip()
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

        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            logger.warning("Skipping unparsable line (expected at least 3 '|'-delimited fields): %r", line)
            continue
        if not current:
            logger.warning("Skipping result row found before any panel header: %r", line)
            continue

        page = None
        if len(parts) >= 4 and parts[3].isdigit():
            page = int(parts[3])
        current.rows.append(
            {
                "test_name_raw": parts[0],
                "value_raw": parts[1],
                "ref_range_raw": parts[2],
                "source_page": page,
                "confidence": 0.90,
            }
        )

    return panels


def looks_like_military_health(text: str) -> bool:
    """Heuristic format detector used by sources.detect_source_system()."""
    return bool(PANEL_HEADER_RE.search(text))


def normalize_panels(panels: Iterable[ParsedPanel]) -> list[NormalizedLabResult]:
    normalized: list[NormalizedLabResult] = []
    for panel in panels:
        for row in panel.rows:
            normalized.append(normalize_row(panel.panel, panel.collection_date, row))
    return normalized
