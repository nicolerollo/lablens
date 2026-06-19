# Phase 3: Physician-facing summaries

Phase 3 turns normalized longitudinal lab observations into a concise report that a clinician could skim quickly. The goal is not diagnosis or medical decision support. The goal is clear presentation of structured data.

## Report outputs

The demo pipeline now writes two report formats:

```text
data/sample_output/physician_summary.md
data/sample_output/physician_summary.html
```

The Markdown report is easy to review in GitHub. The HTML report is styled for printing or opening in a browser.

## What the report shows

Each canonical lab test receives a longitudinal summary:

- latest value and date
- lab-provided reference interval from the source document
- latest lab interpretation: low, normal, high, or (for non-numeric results) qualitative_normal /
  qualitative_abnormal / qualitative_indeterminate
- patient-specific median
- patient-specific mean
- interquartile range (IQR)
- observed minimum and maximum
- percent change from personal median
- simple trend flag: rising, falling, stable, or insufficient data
- review priority: routine, monitor trend, review, or review first
- compact sparkline history in the HTML report

## Why median and IQR matter

Average values can be distorted by acute illness, treatment changes, surgery, steroids, or outlier lab draws. LabLens reports the mean because it is familiar, but uses median and IQR as the primary personal-baseline statistics.

With fewer than three observations, there isn't really a baseline yet — the IQR collapses to the
one or two values seen, which would otherwise produce a confident-sounding but meaningless "at
personal baseline" flag. Below that threshold, LabLens reports the personal-baseline flag as
`insufficient history` instead, and that case is treated as neutral (not "monitor trend") in the
review-priority logic below, so a single normal result with no other signal doesn't get escalated
just because there isn't enough history yet.

## Review priority logic

The priority flag is intentionally conservative and descriptive:

- `review first`: latest value is abnormal and there is another signal such as directional trend, persistent abnormality, or marked deviation from baseline
- `review`: latest value is abnormal or notably outside the personal baseline
- `monitor trend`: value is not currently abnormal but is moving or outside the usual IQR
- `routine`: no major synthetic signal in the available data

These flags are not clinical advice. They are a presentation aid for deciding what a human reviewer should look at first.

## Qualitative results

Not every lab result is numeric — pathogen panels and some serologies report `DETECTED` /
`Not Detected` or `Positive` / `Negative` instead of a number. Earlier versions of this pipeline
classified every non-numeric result simply as `"qualitative"`, which meant a result like a positive
pathogen test was filtered out of the report alongside benign negative results, because the
analytics layer only operates on numeric values.

LabLens now classifies qualitative results into `qualitative_normal`, `qualitative_abnormal`, or
`qualitative_indeterminate` (`normalizer.interpret_qualitative`) using a keyword list, and the report
generator surfaces `qualitative_abnormal` findings at the top of the review priorities section instead
of dropping them.

## Source-truth principle

LabLens does not replace the performing laboratory's reference range with a universal literature range. The source lab range is shown directly, while personal baseline is calculated separately from the patient's own historical values.

## Multi-source longitudinal view

Because the underlying database merges results from every source system the patient's records were
extracted from (see [phase1_parsing.md](phase1_parsing.md) and [phase2_database.md](phase2_database.md)),
a single row in this report can represent a trend that spans a military-health-style draw and a
academic-medical-center-style draw. The report itself does not show which system each historical point
came from — that provenance lives in the database (`source_documents.source_system`) and is
queryable via [`sql/example_queries.sql`](../sql/example_queries.sql) — but it is what makes the
longitudinal trend possible in the first place.

## A note on language

Every label in this report is deliberately descriptive rather than diagnostic: "review first" means
"a human should look at this soon," not "this is a confirmed clinical finding." The report does not
suggest a cause, a treatment, or a diagnosis for any result — it organizes structured lab history so
a clinician can triage faster, not so the software can replace their judgment.
