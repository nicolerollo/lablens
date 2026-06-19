# Data model

LabLens stores each patient's lab history as one relational record set, even though the source
data is fragmented across multiple healthcare systems. See [phase2_database.md](phase2_database.md)
for the full schema; this page documents the analytics-facing shape of a normalized result —
the columns exposed by `v_normalized_lab_results` and consumed by `fetch_numeric_results()` /
`fetch_qualitative_results()` in [`database.py`](../src/lablens/database.py).

## Normalized result shape

| Column | Purpose |
|---|---|
| `panel` | Raw or normalized panel name, such as CBC or CMP |
| `collection_date` | Date/time associated with the result header |
| `test_name_raw` | Exact test name extracted from the source text |
| `canonical_test_name` | Project's mapped concept name |
| `value_raw` | Exact extracted value |
| `numeric_value` | Parsed numeric value, when available |
| `qualitative_value` | Text value for qualitative tests |
| `unit_raw` | Extracted or inferred unit |
| `ref_range_raw` | Exact reference interval text |
| `ref_low` / `ref_high` | Parsed numeric bounds, when available |
| `ref_comparator` | `range`, `<`, `>`, or `qualitative` |
| `interpretation` | `normal` / `high` / `low`, or for non-numeric results `qualitative_normal` / `qualitative_abnormal` / `qualitative_indeterminate` |
| `source_page` | Page from the source PDF or extraction output, when available |
| `confidence` | Heuristic confidence score for review prioritization |

This shape is intentionally source-agnostic: a row produced by the military-health-style parser and a row
produced by the academic-medical-center-style parser (see [phase1_parsing.md](phase1_parsing.md)) look
identical at this layer. Which source system and document a result came from is still tracked —
in `source_documents.source_system` and `source_documents.filename` — it is just one join away
rather than baked into this analytics-facing view.

## Implemented schema

The relational schema actually implemented in [`sql/schema.sql`](../sql/schema.sql) separates:

- `patients`
- `source_documents` — one row per extracted-text input file, tagged with `source_system`
- `extraction_runs` — which parser (and version) produced a source document's rows
- `lab_panels`
- `canonical_lab_tests`
- `lab_test_aliases`
- `units`
- `lab_results` — raw and normalized fields side by side
- `review_queue`

See [phase2_database.md](phase2_database.md) for the full table-by-table design rationale.

## Possible future expansion

- `unit_conversions` as its own table if non-linear conversions are ever needed
- `reference_intervals` as its own table if literature/lab-specific ranges need versioning
  independent of individual results
- `review_events` to track reviewer actions over time instead of a single `status` column

The key design principle, now and in any future expansion, is preserving source truth while
adding normalized fields for analytics.
