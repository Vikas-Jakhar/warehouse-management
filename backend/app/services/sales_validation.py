from datetime import date, datetime
from typing import Any

from app.services.validation_report import RowError, ValidationReport

REQUIRED_COLUMNS = {"date", "sku_id", "quantity_sold"}


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_sales_rows(
    rows: list[dict[str, Any]],
    known_sku_codes: set[str],
    known_warehouse_codes: set[str] | None = None,
) -> ValidationReport:
    """Per section 9: validates invalid dates, missing SKU IDs, duplicate
    records, negative quantities, missing values, unknown SKUs, incorrect
    data types, and inconsistent warehouse references. `sku_id` in the
    upload file refers to the SKU's `sku_code`, resolved to a real FK by the
    caller after validation passes.
    """
    report = ValidationReport(total_rows=len(rows))
    seen_dupes: set[tuple[str, str, str | None]] = set()

    for idx, raw_row in enumerate(rows, start=1):
        row = {k: (v if v != "" else None) for k, v in raw_row.items()}
        row_errors: list[RowError] = []

        for col in REQUIRED_COLUMNS:
            if row.get(col) in (None, ""):
                row_errors.append(RowError(idx, col, f"Missing required field '{col}'"))

        parsed_date = _parse_date(row.get("date"))
        if row.get("date") is not None and parsed_date is None:
            row_errors.append(RowError(idx, "date", f"Invalid date '{row.get('date')}'"))

        sku_code = str(row.get("sku_id")).strip() if row.get("sku_id") else None
        if sku_code and sku_code not in known_sku_codes:
            row_errors.append(RowError(idx, "sku_id", f"Unknown SKU '{sku_code}' — upload the SKU master first"))

        warehouse_code = row.get("warehouse_id")
        if known_warehouse_codes is not None and warehouse_code and warehouse_code not in known_warehouse_codes:
            row_errors.append(RowError(idx, "warehouse_id", f"Unknown warehouse reference '{warehouse_code}'"))

        qty = _to_float(row.get("quantity_sold"))
        if row.get("quantity_sold") is not None and qty is None:
            row_errors.append(RowError(idx, "quantity_sold", "quantity_sold must be numeric"))
        elif qty is not None and qty < 0:
            row_errors.append(RowError(idx, "quantity_sold", "quantity_sold cannot be negative"))

        dedupe_key = (sku_code or "", str(parsed_date) if parsed_date else "", row.get("order_id"))
        if sku_code and parsed_date and dedupe_key in seen_dupes:
            row_errors.append(RowError(idx, "order_id", "Duplicate sales record (same SKU, date, and order_id)"))
        else:
            seen_dupes.add(dedupe_key)

        if row_errors:
            report.errors.extend(row_errors)
            report.invalid_rows += 1
        else:
            report.valid_rows += 1
            report.records.append(
                {
                    "sku_code": sku_code,
                    "warehouse_code": warehouse_code,
                    "sale_date": parsed_date,
                    "quantity_sold": qty,
                    "order_id": row.get("order_id"),
                    "customer_segment": row.get("customer_segment"),
                    "sales_channel": row.get("sales_channel"),
                    "region": row.get("region"),
                    "promotion": bool(row.get("promotion")) if row.get("promotion") is not None else False,
                    "price": _to_float(row.get("price")),
                    "discount": _to_float(row.get("discount")),
                    "holiday_flag": bool(row.get("holiday_flag")) if row.get("holiday_flag") is not None else False,
                    "returns": _to_float(row.get("returns")) or 0.0,
                    "stockout_flag": bool(row.get("stockout_flag")) if row.get("stockout_flag") is not None else False,
                }
            )

    return report
