from lablens.regional_hospital_parser import parse_regional_hospital_text, looks_like_regional_hospital
from lablens.parser import normalize_panels


def test_parse_regional_hospital_panel_and_rows():
    text = """
    === CBC WITH DIFFERENTIAL === Date: 2026-05-01
    WBC=6.0 K/uL (range 4.0-11.0)
    RBC=4.45 M/uL (range 3.70-5.10)
    """
    panels = parse_regional_hospital_text(text)
    assert len(panels) == 1
    assert panels[0].panel == "CBC WITH DIFFERENTIAL"
    assert panels[0].collection_date == "2026-05-01"
    assert len(panels[0].rows) == 2

    results = normalize_panels(panels)
    # Canonical-test resolution is database-driven (database.resolve_canonical_test); the parser
    # and normalizer only preserve the raw test name.
    assert results[0].test_name_raw == "WBC"
    assert results[0].canonical_test_name is None
    assert results[0].numeric_value == 6.0
    assert results[0].ref_low == 4.0
    assert results[0].ref_high == 11.0


def test_row_before_header_is_skipped():
    text = """
    WBC=6.0 K/uL (range 4.0-11.0)
    === CBC WITH DIFFERENTIAL === Date: 2026-05-01
    RBC=4.45 M/uL (range 3.70-5.10)
    """
    panels = parse_regional_hospital_text(text)
    assert len(panels) == 1
    assert len(panels[0].rows) == 1


def test_looks_like_detector():
    assert looks_like_regional_hospital("=== CBC === Date: 2026-05-01\nWBC=6.0 K/uL (range 4.0-11.0)")
    assert not looks_like_regional_hospital("WBC | 7.2 | 4.0 - 11.0 K/uL | 10")
