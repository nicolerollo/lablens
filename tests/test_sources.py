from lablens.sources import SOURCE_PARSERS, detect_source_system, parse_auto


MILITARY_HEALTH_TEXT = "CBC WITH DIFFERENTIAL - Final result (2026-01-14 09:22 AM CDT)\nWBC | 7.2 | 4.0 - 11.0 K/uL | 10"
ACADEMIC_MEDICAL_CENTER_TEXT = "Panel: CBC WITH DIFFERENTIAL | Collected: 2026-02-10\n  WBC .................. 6.4 K/uL Ref: 4.0-11.0"
REGIONAL_HOSPITAL_TEXT = "=== CBC WITH DIFFERENTIAL === Date: 2026-05-01\nWBC=6.0 K/uL (range 4.0-11.0)"


def test_registry_has_all_three_sources():
    assert set(SOURCE_PARSERS) == {"military_health_style", "academic_medical_center_style", "regional_hospital_style"}


def test_detect_source_system_identifies_each_format():
    assert detect_source_system(MILITARY_HEALTH_TEXT) == "military_health_style"
    assert detect_source_system(ACADEMIC_MEDICAL_CENTER_TEXT) == "academic_medical_center_style"
    assert detect_source_system(REGIONAL_HOSPITAL_TEXT) == "regional_hospital_style"


def test_detect_source_system_returns_none_for_unrecognized_text():
    assert detect_source_system("just some plain text with no recognizable header") is None


def test_parse_auto_dispatches_to_the_right_parser():
    source_system, panels = parse_auto(ACADEMIC_MEDICAL_CENTER_TEXT)
    assert source_system == "academic_medical_center_style"
    assert panels[0].panel == "CBC WITH DIFFERENTIAL"
