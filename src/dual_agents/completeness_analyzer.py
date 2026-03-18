from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CRITICAL_FIELDS: tuple[str, ...] = (
    "motor_power_watts",
    "battery_wh",
    "weight_lbs",
    "max_speed_mph",
)

BRAND_SETS: dict[str, tuple[str, ...]] = {
    "affiliate": (
        "kingbull",
        "puckipuppy",
        "vivi",
        "vanpowers",
        "lacros",
        "tenways",
        "megawheels",
    ),
    "official": (
        "radpower",
        "ride1up",
        "super73",
        "aventon",
        "velotric",
    ),
}

SUPPORTED_INPUT_PATTERN = "data/<brand>/coverage_report.json"


class CompletenessAnalyzerError(ValueError):
    """Raised when the completeness analyzer input files are missing or malformed."""


@dataclass(frozen=True)
class BrandCompleteness:
    brand: str
    brand_type: str
    models_attempted: int
    models_succeeded: int
    critical_coverage: dict[str, float]
    average_critical_coverage: float


def supported_schema_description() -> str:
    return (
        "Supported inputs:\n"
        f"- {SUPPORTED_INPUT_PATTERN}\n"
        "Required top-level keys in each coverage report:\n"
        "- brand: string\n"
        "- products_attempted: integer\n"
        "- products_succeeded: integer\n"
        "- fields: object\n"
        "Required per-field schema for critical fields:\n"
        "- normalized_success: integer\n"
    )


def _require_dict(payload: object, *, context: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise CompletenessAnalyzerError(f"{context} must be an object.")
    return payload


def _require_int(payload: dict[str, object], key: str, *, context: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompletenessAnalyzerError(f"{context}.{key} must be an integer.")
    return value


def _require_string(payload: dict[str, object], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CompletenessAnalyzerError(f"{context}.{key} must be a non-empty string.")
    return value.strip()


def _load_json(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise CompletenessAnalyzerError(f"Missing required coverage report: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CompletenessAnalyzerError(f"Invalid JSON in {path}: {exc}") from exc
    return _require_dict(raw, context=str(path))


def load_coverage_report(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    _require_string(payload, "brand", context=str(path))
    attempted = _require_int(payload, "products_attempted", context=str(path))
    succeeded = _require_int(payload, "products_succeeded", context=str(path))
    if attempted < 0 or succeeded < 0:
        raise CompletenessAnalyzerError(f"{path} product counters must be non-negative.")
    fields = _require_dict(payload.get("fields"), context=f"{path}.fields")
    for field_name in CRITICAL_FIELDS:
        field_payload = _require_dict(fields.get(field_name), context=f"{path}.fields.{field_name}")
        normalized_success = _require_int(
            field_payload,
            "normalized_success",
            context=f"{path}.fields.{field_name}",
        )
        if normalized_success < 0:
            raise CompletenessAnalyzerError(
                f"{path}.fields.{field_name}.normalized_success must be non-negative."
            )
    return payload


def analyze_brand(data_root: Path, *, brand: str, brand_type: str) -> BrandCompleteness:
    report_path = data_root / brand / "coverage_report.json"
    payload = load_coverage_report(report_path)
    attempted = _require_int(payload, "products_attempted", context=str(report_path))
    succeeded = _require_int(payload, "products_succeeded", context=str(report_path))
    denominator = succeeded if succeeded > 0 else attempted
    fields = _require_dict(payload["fields"], context=f"{report_path}.fields")

    critical_coverage: dict[str, float] = {}
    for field_name in CRITICAL_FIELDS:
        field_payload = _require_dict(fields[field_name], context=f"{report_path}.fields.{field_name}")
        normalized_success = _require_int(
            field_payload,
            "normalized_success",
            context=f"{report_path}.fields.{field_name}",
        )
        if denominator <= 0:
            critical_coverage[field_name] = 0.0
        else:
            critical_coverage[field_name] = normalized_success / denominator

    average = sum(critical_coverage.values()) / len(CRITICAL_FIELDS)
    return BrandCompleteness(
        brand=brand,
        brand_type=brand_type,
        models_attempted=attempted,
        models_succeeded=succeeded,
        critical_coverage=critical_coverage,
        average_critical_coverage=average,
    )


def analyze_brand_sets(data_root: Path, *, brand_set_names: tuple[str, ...]) -> list[BrandCompleteness]:
    results: list[BrandCompleteness] = []
    for brand_set_name in brand_set_names:
        try:
            brands = BRAND_SETS[brand_set_name]
        except KeyError as exc:
            raise CompletenessAnalyzerError(f"Unsupported brand set: {brand_set_name}") from exc
        for brand in brands:
            results.append(
                analyze_brand(
                    data_root,
                    brand=brand,
                    brand_type=brand_set_name.capitalize(),
                )
            )
    return results


def format_text_report(results: list[BrandCompleteness]) -> str:
    lines = [
        "TECH SPEC COMPLETENESS ANALYSIS",
        f"Inputs: {SUPPORTED_INPUT_PATTERN}",
        "",
        "Brand            Type        Attempted  Succeeded  Motor   Battery  Weight  Speed   Avg",
        "-----------------------------------------------------------------------------------------",
    ]
    for result in results:
        motor = result.critical_coverage["motor_power_watts"] * 100
        battery = result.critical_coverage["battery_wh"] * 100
        weight = result.critical_coverage["weight_lbs"] * 100
        speed = result.critical_coverage["max_speed_mph"] * 100
        avg = result.average_critical_coverage * 100
        lines.append(
            f"{result.brand:<16} {result.brand_type:<11} {result.models_attempted:<10} "
            f"{result.models_succeeded:<10} {motor:>5.1f}%  {battery:>6.1f}%  {weight:>5.1f}%  "
            f"{speed:>5.1f}%  {avg:>5.1f}%"
        )
    return "\n".join(lines)
