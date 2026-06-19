# Roadmap

## Milestone 1: Synthetic text parser (done)

- Parse panel headers
- Parse result rows
- Normalize numeric values
- Store in SQLite
- Generate Markdown report

## Milestone 1b: Multi-source parsing (done)

- Add a second source-specific parser (`academic_medical_center_style`) with its own header/row layout
- Add a parser registry (`sources.py`) so new source systems are one module + one registry entry
- Tag `source_documents`/`extraction_runs` with `source_system` and `parser_name` per call
- Demonstrate longitudinal merge across sources in the demo report (e.g. a trend spanning a
  military-health-style draw and an academic-medical-center-style draw)
- Classify qualitative (non-numeric) results as abnormal/normal/indeterminate instead of dropping
  them from the numeric-only analytics path

## Milestone 1c: A third source format and auto-detection (done)

- Added `regional_hospital_style`, a third parser with its own header/row layout, proving the
  registry pattern generalizes beyond two formats
- Added `sources.detect_source_system()` / `sources.parse_auto()`: a lightweight format
  auto-detector so the demo no longer has to hardcode which parser applies to which input file

## Milestone 1d: Cross-source duplicate detection (done)

- A single draw reported to two source systems (e.g. a referral lab reporting back to both an
  ordering system and a patient portal) is detected in `insert_results()` by matching
  (canonical test, collection date, value) against existing rows from a *different*
  `source_document_id`
- Flagged rows get `normalization_status = 'possible_duplicate'`, land in the review queue, and
  are excluded from `fetch_numeric_results()` so they aren't double-counted in baseline analytics
- Known limitation: matches on exact value only; a genuinely different same-day redraw would not
  be (and should not be) flagged

## Milestone 1e: Database-driven alias mapping (done)

- Removed the parallel `TEST_ALIASES` Python dictionary from `normalizer.py` -- `lab_test_aliases`
  is now the single source of truth for raw-name -> canonical-test mapping
- Added `database.resolve_canonical_test()`, the one function that performs the lookup; called by
  `insert_results()`, which also writes the resolved name back onto the in-memory result
- `normalize_row()` no longer guesses a canonical name at all; `NormalizedLabResult.canonical_test_name`
  starts `None` and is only populated after a database round-trip
- See [database.md](database.md#alias-mapping-is-database-driven)

## Milestone 1f: Better unit normalization (done)

- `_unit_id()` now matches `unit_raw` case-insensitively
- Seeded realistic CBC cell-count unit variants (`10^3/uL`, `x10^6/uL`, `M/µL`, `K/mcL`, etc.)
  instead of only the two original scientific-notation spellings
- Cut the bundled demo's review-queue noise from 13 rows to 5 -- the remaining rows are genuinely
  unmapped tests or a real cross-source duplicate, not unit-spelling false positives
- See [database.md](database.md#unit-normalization)

## Milestone 1g: A messier parser fixture (done)

- Added `data/sample_input/messy_academic_medical_center_extracted_text.txt`: line-wrapped rows, repeated
  letterhead, a `Performed At:` footer, a panel continuing under a repeated header after a page
  break, and one qualitative result
- `academic_medical_center_parser.py` now recovers wrapped rows via a one-line lookahead merge, and quietly skips
  recognized junk lines instead of logging them as unparsable
- See [phase1_parsing.md](phase1_parsing.md#handling-messy-extraction-artifacts) and
  `tests/test_messy_academic_medical_center_fixture.py`

## Milestone 1h: A small CLI (done)

- Added `lablens parse|ingest|report|export-review|demo` (`src/lablens/cli.py`), registered as the
  `lablens` console script alongside the existing `lablens-demo`
- `parse` and `ingest` auto-detect each input file's source format by default, with
  `--source-system` to force one explicitly
- See the README "CLI" section and `tests/test_cli.py`

## Milestone 1i: Fixed alias re-seed duplication and read-only DB access (done)

- Found and fixed a real database hygiene bug: `connect()` re-running `seed_reference_data()`
  against an existing database duplicated every generic (`source_lab IS NULL`) alias each time,
  since SQL's `UNIQUE(alias_raw, source_lab)` does not consider two `NULL`s equal
- Added the `idx_alias_unique_generic` expression index (`COALESCE(source_lab, '')`) in both
  `sql/schema.sql` and `sql/schema_postgres.sql` to close that gap
- Split `connect()` (creates/seeds, safe to call repeatedly) from `connect_existing()` (read-only,
  raises clearly if the database doesn't exist) and switched `lablens report` /
  `lablens export-review` to the latter
- See [database.md](database.md#reconnecting-must-not-duplicate-generic-aliases) and
  `tests/test_database_phase2.py::test_connecting_repeatedly_does_not_duplicate_generic_aliases`

## Milestone 2: PDF extraction backend

Use existing tools rather than writing a PDF parser from scratch.

Candidate tools:

- `pdfplumber` for text and table extraction
- `PyMuPDF` for robust PDF text access
- Camelot or Tabula for table-heavy PDFs
- OCR fallback for scanned PDFs

## Milestone 3: Human review queue (data model + CSV export done, web UI not started)

`review_queue` captures unmapped tests, ambiguous units, low-confidence rows, abnormal qualitative
findings, and cross-source duplicates (`fetch_review_queue()`). `export_review_queue_csv()` now
writes the whole queue to `data/sample_output/review_queue.csv` on every demo run. Still needed: a
simple web UI where a human can approve, correct, or reject a queued row instead of editing the CSV
or SQL by hand.

## Milestone 4: Better database design (schema done; Postgres schema ported, app not wired up)

The normalized multi-table SQLite schema in `sql/schema.sql` is implemented (see
[database.md](database.md) and [phase2_database.md](phase2_database.md)). `sql/schema_postgres.sql`
and `docker-compose.yml` provide a ready-to-run Postgres port of the same schema. Remaining:
`database.py` itself still only speaks SQLite — making it a real dual-backend application means
swapping the connection layer (see "PostgreSQL migration path" in [database.md](database.md)).

## Milestone 5: Physician report (done)

- latest value
- lab reference range
- personal median
- personal IQR
- trend
- source document/page
- qualitative (non-numeric) findings, surfaced rather than dropped

## Milestone 6: Interoperability

Export selected records as FHIR Observations.
