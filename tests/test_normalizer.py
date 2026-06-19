from lablens.normalizer import parse_reference_range, normalize_row, interpret_qualitative


def test_qualitative_detected_is_flagged_abnormal():
    result = normalize_row(
        "RESPIRATORY PATHOGEN PANEL",
        "2026-04-20",
        {"test_name_raw": "Respiratory Syncytial Virus", "value_raw": "DETECTED", "ref_range_raw": "Not Detected"},
    )
    assert result.numeric_value is None
    assert result.qualitative_value == "DETECTED"
    assert result.interpretation == "qualitative_abnormal"


def test_qualitative_not_detected_is_normal():
    assert interpret_qualitative("Not Detected") == "qualitative_normal"


def test_qualitative_unknown_term_is_indeterminate():
    assert interpret_qualitative("Indeterminate") == "qualitative_indeterminate"


def test_parse_standard_range():
    assert parse_reference_range("4.0 - 11.0 K/uL") == (4.0, 11.0, "range")


def test_parse_less_than_range():
    assert parse_reference_range("<8.0 mg/L") == (None, 8.0, "<")


def test_normalize_high_value():
    result = normalize_row(
        "CBC WITH DIFFERENTIAL",
        "2026-01-14",
        {"test_name_raw": "WBC", "value_raw": "12.2", "ref_range_raw": "4.0 - 11.0 K/uL"},
    )
    # normalize_row() no longer guesses a canonical name itself -- that's resolved later via
    # database.resolve_canonical_test() against lab_test_aliases. See test_database_phase2.py
    # for alias-resolution coverage.
    assert result.canonical_test_name is None
    assert result.test_name_raw == "WBC"
    assert result.numeric_value == 12.2
    assert result.interpretation == "high"
