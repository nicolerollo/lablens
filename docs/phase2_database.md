# Phase 2: Database Layer

> For the full entity-relationship diagram, column-by-column data dictionary, and example queries
> with real captured output, see **[database.md](database.md)**. This page is the narrative
> walkthrough; that one is the reference.

Phase 1 ([phase1_parsing.md](phase1_parsing.md)) turns extracted clinical PDF text — in whatever
layout a given source system happens to export — into normalized lab-result objects.
Phase 2 makes that data durable, queryable, and defensible by storing it in a relational schema
that keeps multiple source systems' results attributable while merging them into one patient
history for analytics.

## Design principles

1. **Preserve source truth**  
   Raw test names, raw values, raw units, raw reference ranges, source page, and source text are stored exactly as extracted.

2. **Normalize without overwriting**  
   Canonical test names, normalized units, numeric values, and interpretation fields are stored beside the raw fields, not instead of them.

3. **Reference ranges are result-specific**  
   Different labs can use different reference intervals. LabLens stores the range supplied with each result rather than assuming one universal normal range.

4. **Uncertainty is modeled**  
   Rows with unmapped tests, ambiguous units, low confidence, or **cross-source duplicates** are inserted but flagged in `review_queue` (and exportable via `export_review_queue_csv()`).

5. **Analytics use verified normalized fields**  
   Personal baselines and longitudinal reports use numeric normalized values where available.

## Core tables

- `patients` — synthetic demo patient record. One patient can have many `source_documents`
  across many systems.
- `source_documents` — one row per extracted text/table source file, tagged with
  `source_system` (e.g. `military_health_style_demo`, `academic_medical_center_style_demo`) and `filename`. This is the
  join point for "which provider did this result come from."
- `extraction_runs` — parser name, version, and status for the run that produced a source
  document's rows. Each source format (see [phase1_parsing.md](phase1_parsing.md)) has its own
  `parser_name`.
- `canonical_lab_tests` — canonical lab concepts such as `White blood cell count`.
- `lab_test_aliases` — raw names mapped to canonical concepts, such as `WBC` or `Leukocytes`.
- `units` — raw units and safe normalization mappings.
- `lab_panels` — source panel headers, dates, and performing lab text.
- `lab_results` — raw and normalized individual lab observations.
- `review_queue` — rows needing human validation.

## Useful view

`v_normalized_lab_results` joins the major tables into a readable analytics view.

Example:

```sql
SELECT collection_date, canonical_name, numeric_value, normalized_unit, lab_interpretation
FROM v_normalized_lab_results
WHERE canonical_name = 'White blood cell count'
ORDER BY collection_date;
```

## Multi-source merge, not multi-source duplication

`insert_results()` takes `filename` / `source_system` / `parser_name` arguments and creates one
`source_documents` + `extraction_runs` pair per call, while reusing the same `patients` row. The
demo pipeline calls it once per source system (see [`demo.py`](../src/lablens/demo.py)), so a
patient's CBC or Potassium history can span a military-health-style draw in January and a
academic-medical-center-style draw in February and still resolve to one continuous trend in
`v_normalized_lab_results` — see example query 1b in
[`sql/example_queries.sql`](../sql/example_queries.sql).

## Why this matters

The project is not just a parser. It demonstrates the full clinical data lifecycle:

```text
PDF exports from multiple systems → source-specific parsing → raw result preservation
  → normalization → relational database → longitudinal analytics → physician summary
```
