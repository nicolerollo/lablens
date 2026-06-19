from lablens.analytics import compute_baselines
from lablens.report import generate_markdown_report, generate_html_report


def test_phase3_baseline_summary_flags_review_priority():
    rows = [
        {"canonical_test_name": "Potassium", "collection_date": "2026-01-01", "numeric_value": 3.7, "interpretation": "normal", "ref_low": 3.5, "ref_high": 5.1, "ref_comparator": "range", "unit_raw": "mmol/L"},
        {"canonical_test_name": "Potassium", "collection_date": "2026-02-01", "numeric_value": 3.6, "interpretation": "normal", "ref_low": 3.5, "ref_high": 5.1, "ref_comparator": "range", "unit_raw": "mmol/L"},
        {"canonical_test_name": "Potassium", "collection_date": "2026-03-01", "numeric_value": 3.2, "interpretation": "low", "ref_low": 3.5, "ref_high": 5.1, "ref_comparator": "range", "unit_raw": "mmol/L"},
    ]
    summaries = compute_baselines(rows)
    potassium = summaries[0]

    assert potassium.test_name == "Potassium"
    assert potassium.median_value == 3.6
    assert potassium.mean_value == 3.5
    assert potassium.latest_interpretation == "low"
    assert potassium.review_priority in {"review", "review first"}


def test_low_observation_count_reports_insufficient_history_not_a_false_baseline():
    """With only one or two draws, q1 == q3 == the value(s) seen, so the old logic reported the
    confident-sounding 'at personal baseline' for a number with no real baseline behind it yet.
    Below MIN_OBSERVATIONS_FOR_BASELINE, the flag should say so plainly instead."""
    rows = [
        {"canonical_test_name": "Glucose", "collection_date": "2026-01-01", "numeric_value": 95.0, "interpretation": "normal", "ref_low": 70.0, "ref_high": 99.0, "ref_comparator": "range", "unit_raw": "mg/dL"},
    ]
    summaries = compute_baselines(rows)
    glucose = summaries[0]

    assert glucose.observations == 1
    assert glucose.personal_baseline_flag == "insufficient history"
    # A single normal result with no trend signal should not be escalated to "monitor trend"
    # just because there isn't enough history for a real baseline.
    assert glucose.review_priority == "routine"


def test_phase3_reports_include_physician_friendly_fields():
    rows = [
        {"canonical_test_name": "C-reactive protein", "collection_date": "2026-01-01", "numeric_value": 2.0, "interpretation": "normal", "ref_low": None, "ref_high": 8.0, "ref_comparator": "<", "unit_raw": "mg/L"},
        {"canonical_test_name": "C-reactive protein", "collection_date": "2026-02-01", "numeric_value": 10.0, "interpretation": "high", "ref_low": None, "ref_high": 8.0, "ref_comparator": "<", "unit_raw": "mg/L"},
        {"canonical_test_name": "C-reactive protein", "collection_date": "2026-03-01", "numeric_value": 12.0, "interpretation": "high", "ref_low": None, "ref_high": 8.0, "ref_comparator": "<", "unit_raw": "mg/L"},
    ]
    summaries = compute_baselines(rows)
    md = generate_markdown_report(summaries)
    html = generate_html_report(summaries)

    assert "Review priorities" in md
    assert "Personal median" in md
    assert "Δ from median" in md
    assert "Clinician-facing longitudinal table" in html
    assert "<svg" in html


def test_abnormal_qualitative_result_appears_in_reports():
    qualitative_rows = [
        {
            "canonical_test_name": None,
            "test_name_raw": "Respiratory Syncytial Virus",
            "qualitative_value": "DETECTED",
            "interpretation": "qualitative_abnormal",
            "collection_date": "2026-04-20",
            "panel": "RESPIRATORY PATHOGEN PANEL",
        }
    ]
    md = generate_markdown_report([], qualitative_rows)
    html = generate_html_report([], qualitative_rows)

    assert "Respiratory Syncytial Virus" in md
    assert "DETECTED" in md
    assert "Qualitative results" in html
    assert "DETECTED" in html
