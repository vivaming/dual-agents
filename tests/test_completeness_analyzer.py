from pathlib import Path

import pytest

from dual_agents.completeness_analyzer import (
    CompletenessAnalyzerError,
    analyze_brand_sets,
    format_text_report,
    supported_schema_description,
)


def _write_coverage_report(path: Path, *, brand: str, normalized_success: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "{\n"
        f'  "brand": "{brand}",\n'
        '  "products_attempted": 3,\n'
        '  "products_succeeded": 3,\n'
        '  "fields": {\n'
        '    "motor_power_watts": {"normalized_success": ' + str(normalized_success) + "},\n"
        '    "battery_wh": {"normalized_success": ' + str(normalized_success) + "},\n"
        '    "weight_lbs": {"normalized_success": ' + str(normalized_success) + "},\n"
        '    "max_speed_mph": {"normalized_success": ' + str(normalized_success) + "}\n"
        "  }\n"
        "}\n"
    )


def test_supported_schema_description_mentions_explicit_input_file() -> None:
    description = supported_schema_description()
    assert "data/<brand>/coverage_report.json" in description
    assert "normalized_success" in description


def test_analyze_brand_sets_reads_only_explicit_coverage_reports(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    for brand in ("kingbull", "puckipuppy", "vivi", "vanpowers", "lacros", "tenways", "megawheels"):
        _write_coverage_report(data_root / brand / "coverage_report.json", brand=brand)

    results = analyze_brand_sets(data_root, brand_set_names=("affiliate",))

    assert len(results) == 7
    assert results[0].average_critical_coverage == 1.0
    assert "kingbull" in format_text_report(results)


def test_analyze_brand_sets_fails_on_missing_required_report(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_coverage_report(data_root / "kingbull" / "coverage_report.json", brand="kingbull")

    with pytest.raises(CompletenessAnalyzerError):
        analyze_brand_sets(data_root, brand_set_names=("affiliate",))
