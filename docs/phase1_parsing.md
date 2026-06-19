# Phase 1: Source-specific parsing

## The problem

A patient's lab history is rarely sitting in one place. It is fragmented across whatever
systems happened to order or report each test — a military health record system like a military health system,
a hospital system like an academic medical center, a regional system like a regional hospital, and more.
Each system exports lab results as a PDF designed to be *read*, not *queried*: nicely formatted
for a human skimming a portal, but not structured data.

LabLens does not do OCR or PDF table extraction itself — that's a solved problem with mature
tools (`pdfplumber`, `PyMuPDF`, Camelot, Tabula; see [roadmap.md](roadmap.md)). LabLens picks up
right where those tools leave off: **extracted text**, in whatever shape that source system's PDF
happened to produce, and turns it into one normalized longitudinal record per patient.

## One parser per source format

Because every system lays its exports out differently, LabLens uses **one small, source-specific
parser per format** rather than trying to write a single parser that handles every layout:

| Source format | Module | Example layout |
|---|---|---|
| `military_health_style` | [`parser.py`](../src/lablens/parser.py) | Pipe-delimited rows under a `PANEL - Final result (date)` header |
| `academic_medical_center_style` | [`academic_medical_center_parser.py`](../src/lablens/academic_medical_center_parser.py) | Dot-leader rows under a `Panel: ... \| Collected: ...` header |
| `regional_hospital_style` | [`regional_hospital_parser.py`](../src/lablens/regional_hospital_parser.py) | `key=value` rows under a `=== PANEL === Date: ...` banner header |

```text
WBC | 7.2 | 4.0 - 11.0 K/uL | 10               <- military-health-style row
WBC .................. 6.4 K/uL Ref: 4.0-11.0  <- academic-medical-center-style row
WBC=6.0 K/uL (range 4.0-11.0)                  <- regional-hospital-style row
```

All three parsers produce the same `ParsedPanel` shape (panel name, collection date, and a list of
raw row dicts), so everything downstream — normalization, database storage, baseline analytics,
and the physician report — is completely unaware of which source system a result came from. Adding
a fourth source system means adding one more parser module and one more line in the
[`sources.py`](../src/lablens/sources.py) registry, not touching the rest of the pipeline.

```python
# src/lablens/sources.py
SOURCE_PARSERS = {
    "military_health_style": parse_extracted_text,
    "academic_medical_center_style": parse_academic_medical_center_text,
    "regional_hospital_style": parse_regional_hospital_text,
}
```

## Format auto-detection

Each parser module also exposes a `looks_like_*(text)` detector that checks whether that source's
header pattern appears in the text. `sources.detect_source_system(text)` runs every registered
detector and returns the one matching format, or `None` if zero or more than one matched:

```python
>>> from lablens.sources import detect_source_system
>>> detect_source_system(academic_medical_center_text)
'academic_medical_center_style'
```

`sources.parse_auto(text)` combines detection and parsing in one call, and is what the demo
pipeline uses instead of hardcoding which parser applies to which file. This is intentionally a
simple heuristic, not a robust classifier — ambiguous input returns `None` rather than guessing,
and the caller can always fall back to `parse_by_source(text, source_system)` with an explicit
format.

## What each parser is responsible for

- Recognizing panel headers and the result rows beneath them, in that source's own layout.
- Preserving the raw test name, raw value, and raw reference-range text exactly as extracted —
  no cleanup or interpretation happens yet.
- Logging (not silently discarding) lines that don't match the expected shape — a malformed row
  or a result line that appears before any panel header is a real extraction problem worth
  surfacing, not something to drop quietly.

## What happens next

Parsed rows are handed to `normalize_row()` in [`normalizer.py`](../src/lablens/normalizer.py),
which handles unit/value splitting, numeric/qualitative classification, and reference-range
parsing — identically regardless of which source parser produced the row. Test-name **aliasing**
(mapping `WBC`/`Leukocytes`/etc. to one canonical concept) deliberately does **not** happen here —
it's resolved later, against the database, by `database.resolve_canonical_test()`. See
[database.md](database.md#alias-mapping-is-database-driven) for why that lookup lives in the
database layer instead of a parallel Python dictionary, and [phase2_database.md](phase2_database.md)
for how the normalized result is stored.

## Handling messy extraction artifacts

The other three sample inputs are clean for demo readability, but real PDF text extraction rarely
is. `data/sample_input/messy_academic_medical_center_extracted_text.txt` is deliberately messier, and
[`academic_medical_center_parser.py`](../src/lablens/academic_medical_center_parser.py) is built to tolerate it:

- **Line-wrapped rows** — a result's value and unit landed on the line after its test name
  (a narrow PDF column wrapping mid-row). The parser retries a failed line merged with the line
  that follows it, and only falls back to a warning if that still doesn't match a known row shape.
- **Repeated letterhead/banner text** and **`Performed At:` footers** — recognized by
  `KNOWN_JUNK_LINE_RE` and skipped quietly, since they're an expected feature of multi-page
  exports, not an extraction problem worth flagging.
- **A panel split across a page break**, continuing under a second copy of its own
  `Panel: ... | Collected: ...` header — the parser just emits a second `ParsedPanel` for the same
  (panel, date); `database.insert_results()` already merges rows sharing the same
  (`panel_name_raw`, `collection_date`) into one `lab_panels` row downstream, so the continuation
  isn't duplicated.
- **A qualitative (non-numeric) result** in the mix — handled the same as any other source's
  qualitative row.

See `tests/test_messy_academic_medical_center_fixture.py` for the test coverage proving each of these recovers
correctly, and try it yourself:

```bash
lablens parse data/sample_input/messy_academic_medical_center_extracted_text.txt
```

## Demo

The bundled demo (`lablens-demo`) auto-detects and parses all three source formats against
synthetic sample input representing the *same* synthetic patient seen at three different health
systems, and inserts all three into one patient's record:

```text
data/sample_input/synthetic_lab_summary.txt               (military_health_style)
data/sample_input/academic_medical_center_style_lab_summary.txt             (academic_medical_center_style)
data/sample_input/regional_hospital_style_lab_summary.txt    (regional_hospital_style)
```

The resulting longitudinal report blends results from all three sources — for example, a
Potassium trend that includes a military-health-style draw from January, an academic-medical-center-style draw
from February, and a regional-hospital-style draw from May shows up as one continuous trend, not
three disconnected histories. The sample data also includes one deliberately duplicated result
(the same Sodium draw reported by two systems on the same date) so the database's cross-source
duplicate detection has something real to catch — see [database.md](database.md).
