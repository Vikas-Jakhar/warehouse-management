from typing import Any

from app.models.sku import FRAGILITY_LEVELS, HAZARD_CLASSES
from app.services.validation_report import RowError, ValidationReport

REQUIRED_COLUMNS = {"sku_code", "name"}
BOOLEAN_COLUMNS = {"fifo_required", "fefo_required", "lifo_permitted", "requires_expiry"}
NUMERIC_COLUMNS = {
    "length",
    "width",
    "height",
    "weight",
    "volume",
    "min_qty",
    "max_qty",
    "reorder_point",
    "safety_stock",
}
INT_COLUMNS = {"lead_time_days", "shelf_life_days", "picking_priority"}


def _to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_sku_rows(rows: list[dict[str, Any]], existing_sku_codes: set[str]) -> ValidationReport:
    report = ValidationReport(total_rows=len(rows))
    seen_in_file: set[str] = set()

    for idx, raw_row in enumerate(rows, start=1):
        row = {k: (v if v != "" else None) for k, v in raw_row.items()}
        row_errors: list[RowError] = []

        for col in REQUIRED_COLUMNS:
            if row.get(col) in (None, ""):
                row_errors.append(RowError(idx, col, f"Missing required field '{col}'"))

        sku_code = str(row.get("sku_code")).strip() if row.get("sku_code") else None
        if sku_code:
            if sku_code in seen_in_file:
                row_errors.append(RowError(idx, "sku_code", f"Duplicate sku_code '{sku_code}' in file"))
            elif sku_code in existing_sku_codes:
                row_errors.append(RowError(idx, "sku_code", f"sku_code '{sku_code}' already exists"))
            else:
                seen_in_file.add(sku_code)

        for col in NUMERIC_COLUMNS:
            if row.get(col) is not None:
                parsed = _to_float(row.get(col))
                if parsed is None or parsed < 0:
                    row_errors.append(RowError(idx, col, f"{col} must be a non-negative number"))

        for col in INT_COLUMNS:
            if row.get(col) is not None:
                try:
                    int(row.get(col))
                except (TypeError, ValueError):
                    row_errors.append(RowError(idx, col, f"{col} must be an integer"))

        parsed_bools: dict[str, bool] = {}
        for col in BOOLEAN_COLUMNS:
            if row.get(col) is not None:
                parsed = _to_bool(row.get(col))
                if parsed is None:
                    row_errors.append(RowError(idx, col, f"{col} must be true/false"))
                else:
                    parsed_bools[col] = parsed

        fragility = row.get("fragility")
        if fragility and fragility not in FRAGILITY_LEVELS:
            row_errors.append(RowError(idx, "fragility", f"fragility must be one of {sorted(FRAGILITY_LEVELS)}"))

        hazard_class = row.get("hazard_class")
        if hazard_class and hazard_class not in HAZARD_CLASSES:
            row_errors.append(RowError(idx, "hazard_class", f"hazard_class must be one of {sorted(HAZARD_CLASSES)}"))

        # A SKU that requires FEFO management only makes sense if it also
        # tracks expiry - catch the contradiction rather than silently
        # accepting inconsistent policy configuration.
        if parsed_bools.get("fefo_required") and parsed_bools.get("requires_expiry") is False:
            row_errors.append(
                RowError(idx, "requires_expiry", "fefo_required cannot be true when requires_expiry is false")
            )

        if row_errors:
            report.errors.extend(row_errors)
            report.invalid_rows += 1
        else:
            report.valid_rows += 1
            record = dict(row)
            for col in NUMERIC_COLUMNS:
                if record.get(col) is not None:
                    record[col] = _to_float(record[col])
            for col in INT_COLUMNS:
                if record.get(col) is not None:
                    record[col] = int(record[col])
            for col in BOOLEAN_COLUMNS:
                if col in parsed_bools:
                    record[col] = parsed_bools[col]
            report.records.append(record)

    return report
