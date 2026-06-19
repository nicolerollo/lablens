from __future__ import annotations

import logging
import re

from .parser import ParsedPanel

logger = logging.getLogger(__name__)

# academic-medical-center-style portal exports lay results out as dot-leader rows under a
# "Panel: ... | Collected: ..." header, instead of the pipe-delimited rows used by the
# military-health-style export in parser.py. Different source systems format PDFs differently;
# this module is one of three source-specific parsers that all feed the same downstream
# normalize_row()/database pipeline.
PANEL_HEADER_RE = re.compile(
    r"^Panel:\s*(?P<panel>[A-Z0-9 ,/&()\-]+?)\s*\|\s*Collected:\s*(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE | re.MULTILINE,
)

ROW_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ,.\-]*?)\s*\.{2,}\s*"
    r"(?P<value>[A-Za-z0-9.<>+-]+)"
    r"(?:\s+(?P<unit>[A-Za-z%/0-9.^]+))?\s+"
    r"Ref:\s*(?P<ref>.+?)\s*$"
)

# Lines real PDF text extraction tends to leave behind that are not part of any result row:
# repeated banner/letterhead text, "Performed At" footers, page-break artifacts. These are
# recognized and skipped quietly (no warning) instead of being logged as unparsable, since
# they're an expected feature of multi-page exports, not an extraction problem.
KNOWN_JUNK_LINE_RE = re.compile(
    r"^(ACADEMIC MEDICAL CENTER|Patient Portal PDF Export|Performed At\b|Page \d+ of \d+)",
    re.IGNORECASE,
)


def _looks_like_junk(line: str) -> bool:
    return bool(KNOWN_JUNK_LINE_RE.match(line))


def _row_from_match(row: re.Match) -> dict:
    ref = row.group("ref").strip()
    unit = row.group("unit")
    ref_range_raw = f"{ref} {unit}".strip() if unit else ref
    return {
        "test_name_raw": row.group("name").strip(),
        "value_raw": row.group("value").strip(),
        "ref_range_raw": ref_range_raw,
        "source_page": None,
        "confidence": 0.85,
    }


def parse_academic_medical_center_text(text: str) -> list[ParsedPanel]:
    """Parse academic-medical-center-style extracted PDF text into the shared ParsedPanel shape.

    Real PDF text extraction is messier than the clean demo fixture suggests: a row's value
    and unit can land on the next line after a column got too narrow, the same letterhead/banner
    can repeat on every page, and a panel can be split across a page break and continue under a
    second copy of its own header. This parser tolerates all three:

    - a line that doesn't match ROW_RE is retried merged with the next line, in case the row was
      simply wrapped onto two lines (see `_row_from_match`)
    - known banner/footer text (`KNOWN_JUNK_LINE_RE`) is skipped quietly
    - a repeated `Panel: ... | Collected: ...` header for the same panel/date just starts a new
      `ParsedPanel` entry; `database.insert_results()` already merges rows sharing the same
      (panel, collection_date) into one `lab_panels` row, so a continued panel is not duplicated
    """
    lines = text.splitlines()
    panels: list[ParsedPanel] = []
    current: ParsedPanel | None = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
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
                logger.warning("Skipping academic-medical-center-style result row found before any panel header: %r", line)
                continue
            current.rows.append(_row_from_match(row))
            continue

        # The row may have been wrapped across a line break (e.g. the value/unit landed on the
        # next line). Try merging with the next line before giving up on this one.
        if i < len(lines):
            merged = f"{line} {lines[i].strip()}"
            merged_row = ROW_RE.match(merged)
            if merged_row:
                if not current:
                    logger.warning("Skipping wrapped academic-medical-center-style result row found before any panel header: %r", merged)
                else:
                    current.rows.append(_row_from_match(merged_row))
                i += 1  # consume the line we merged in
                continue

        if _looks_like_junk(line):
            continue

        logger.warning("Skipping unparsable academic-medical-center-style line: %r", line)

    return panels


def looks_like_academic_medical_center(text: str) -> bool:
    """Heuristic format detector used by sources.detect_source_system()."""
    return bool(PANEL_HEADER_RE.search(text))
