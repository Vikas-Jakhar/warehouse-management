from datetime import date, datetime
from typing import Any

from app.models.inventory import INVENTORY_STATUSES
from app.services.validation_report import RowError, ValidationReport

REQUIRED_COLUMNS = {"sku_id", "quantity"}


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


def validate_inventory_rows(
    rows: list[dict[str, Any]],
    known_sku_codes: set[str],
    known_location_codes: set[str],
) -> ValidationReport:
    """Per section 10: validates unknown SKUs, unknown storage locations,
    negative/invalid quantities, and invalid dates. `sku_id` / `location_id`
    in the upload refer to sku_code / location_code respectively, resolved to
    real foreign keys by the caller once validation passes. Uploaded
    inventory always lands as the *actual* current location (or unplaced,
    awaiting put-away, if no location is given) — never a recommendation.
    """
    report = ValidationReport(total_rows=len(rows))

    for idx, raw_row in enumerate(rows, start=1):
        row = {k: (v if v != "" else None) for k, v in raw_row.items()}
        row_errors: list[RowError] = []

        for col in REQUIRED_COLUMNS:
            if row.get(col) in (None, ""):
                row_errors.append(RowError(idx, col, f"Missing required field '{col}'"))

        sku_code = str(row.get("sku_id")).strip() if row.get("sku_id") else None
        if sku_code and sku_code not in known_sku_codes:
            row_errors.append(RowError(idx, "sku_id", f"Unknown SKU '{sku_code}' — upload the SKU master first"))

        location_code = row.get("location_id")
        if location_code and location_code not in known_location_codes:
            row_errors.append(
                RowError(idx, "location_id", f"Unknown storage location '{location_code}' — upload the layout first")
            )

        quantity = _to_float(row.get("quantity"))
        if row.get("quantity") is not None and quantity is None:
            row_errors.append(RowError(idx, "quantity", "quantity must be numeric"))
        elif quantity is not None and quantity < 0:
            row_errors.append(RowError(idx, "quantity", "quantity cannot be negative"))

        reserved = _to_float(row.get("reserved_quantity")) or 0.0
        damaged = _to_float(row.get("damaged_quantity")) or 0.0
        for col, val in (("reserved_quantity", row.get("reserved_quantity")), ("damaged_quantity", row.get("damaged_quantity"))):
            if val is not None and _to_float(val) is None:
                row_errors.append(RowError(idx, col, f"{col} must be numeric"))
            elif val is not None and _to_float(val) < 0:
                row_errors.append(RowError(idx, col, f"{col} cannot be negative"))

        if quantity is not None and (reserved + damaged) > quantity:
            row_errors.append(
                RowError(idx, "reserved_quantity", "reserved_quantity + damaged_quantity cannot exceed quantity")
            )

        manufacturing_date = _parse_date(row.get("manufacturing_date"))
        if row.get("manufacturing_date") is not None and manufacturing_date is None:
            row_errors.append(RowError(idx, "manufacturing_date", "Invalid date"))

        receiving_date = _parse_date(row.get("receiving_date"))
        if row.get("receiving_date") is not None and receiving_date is None:
            row_errors.append(RowError(idx, "receiving_date", "Invalid date"))

        expiry_date = _parse_date(row.get("expiry_date"))
        if row.get("expiry_date") is not None and expiry_date is None:
            row_errors.append(RowError(idx, "expiry_date", "Invalid date"))
        if expiry_date and receiving_date and expiry_date < receiving_date:
            row_errors.append(RowError(idx, "expiry_date", "expiry_date cannot be before receiving_date"))

        status = row.get("status")
        if status and status not in INVENTORY_STATUSES:
            row_errors.append(RowError(idx, "status", f"status must be one of {sorted(INVENTORY_STATUSES)}"))

        if row_errors:
            report.errors.extend(row_errors)
            report.invalid_rows += 1
        else:
            report.valid_rows += 1
            report.records.append(
                {
                    "sku_code": sku_code,
                    "location_code": location_code,
                    "quantity": quantity,
                    "reserved_quantity": reserved,
                    "damaged_quantity": damaged,
                    "status": status or ("awaiting_putaway" if not location_code else "in_stock"),
                    "batch_number": row.get("batch_number"),
                    "lot_number": row.get("lot_number"),
                    "manufacturing_date": manufacturing_date,
                    "receiving_date": receiving_date or date.today(),
                    "expiry_date": expiry_date,
                }
            )

    return report
