"""Parses and validates uploaded warehouse layouts (CSV / Excel / JSON).

Per spec section 7: the upload must never be marked successful if validation
fails, and the caller must get back a precise, row-level error report they
can download and fix. This module only *validates and normalizes* — it never
writes to the database. The API layer decides whether to commit based on the
result.
"""

import io
import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.models.warehouse_layout import LOCATION_TYPES, STORAGE_TYPES, ZONE_TYPES

REQUIRED_COLUMNS = {"location_code", "location_type", "storage_type", "x", "y", "width", "height"}
OPTIONAL_NUMERIC = {"depth", "max_weight", "max_volume"}
OPTIONAL_STRING = {"aisle", "rack", "shelf", "bin", "zone_code", "zone_type", "zone_name"}


@dataclass
class RowError:
    row: int
    field: str
    message: str


@dataclass
class ValidationReport:
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    errors: list[RowError] = field(default_factory=list)
    # Normalized, validated records ready for persistence (only populated if fully valid).
    locations: list[dict[str, Any]] = field(default_factory=list)
    zones: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.total_rows > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "is_valid": self.is_valid,
            "errors": [e.__dict__ for e in self.errors],
        }

    def error_report_csv(self) -> str:
        buf = io.StringIO()
        buf.write("row,field,message\n")
        for e in self.errors:
            safe_message = e.message.replace('"', "'")
            buf.write(f'{e.row},{e.field},"{safe_message}"\n')
        return buf.getvalue()


def parse_upload(filename: str, content: bytes) -> list[dict[str, Any]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    elif lower.endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict) and "locations" in data:
            data = data["locations"]
        df = pd.DataFrame(data)
    else:
        raise ValueError("Unsupported file type. Use .csv, .xlsx, or .json")

    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_layout_rows(
    rows: list[dict[str, Any]],
    existing_location_codes: set[str],
    existing_zone_codes: set[str],
    warehouse_already_has_receiving: bool = False,
    warehouse_already_has_dispatch: bool = False,
) -> ValidationReport:
    report = ValidationReport(total_rows=len(rows))

    seen_codes_in_file: set[str] = set()
    seen_zone_codes_in_file: dict[str, dict[str, Any]] = {}
    has_receiving = False
    has_dispatch = False
    bounding_boxes: list[tuple[int, str, float, float, float, float]] = []

    for idx, raw_row in enumerate(rows, start=1):
        row_errors: list[RowError] = []
        row = {k: (v if v != "" else None) for k, v in raw_row.items()}

        missing = [c for c in REQUIRED_COLUMNS if row.get(c) in (None, "")]
        for col in missing:
            row_errors.append(RowError(idx, col, f"Missing required field '{col}'"))

        location_code = str(row.get("location_code")).strip() if row.get("location_code") else None
        if location_code:
            if location_code in seen_codes_in_file:
                row_errors.append(RowError(idx, "location_code", f"Duplicate location_code '{location_code}' in file"))
            elif location_code in existing_location_codes:
                row_errors.append(RowError(idx, "location_code", f"location_code '{location_code}' already exists"))
            else:
                seen_codes_in_file.add(location_code)

        location_type = row.get("location_type")
        if location_type and location_type not in LOCATION_TYPES:
            row_errors.append(
                RowError(idx, "location_type", f"Unsupported location_type '{location_type}'. Allowed: {sorted(LOCATION_TYPES)}")
            )
        if location_type == "receiving":
            has_receiving = True
        if location_type == "dispatch":
            has_dispatch = True

        storage_type = row.get("storage_type")
        if storage_type and storage_type not in STORAGE_TYPES:
            row_errors.append(
                RowError(idx, "storage_type", f"Unsupported storage_type '{storage_type}'. Allowed: {sorted(STORAGE_TYPES)}")
            )

        x = _to_float(row.get("x"))
        y = _to_float(row.get("y"))
        if row.get("x") is not None and x is None:
            row_errors.append(RowError(idx, "x", "x must be numeric"))
        elif x is not None and x < 0:
            row_errors.append(RowError(idx, "x", "x must be >= 0"))
        if row.get("y") is not None and y is None:
            row_errors.append(RowError(idx, "y", "y must be numeric"))
        elif y is not None and y < 0:
            row_errors.append(RowError(idx, "y", "y must be >= 0"))

        width = _to_float(row.get("width"))
        height = _to_float(row.get("height"))
        if row.get("width") is not None and (width is None or width <= 0):
            row_errors.append(RowError(idx, "width", "width must be a positive number"))
        if row.get("height") is not None and (height is None or height <= 0):
            row_errors.append(RowError(idx, "height", "height must be a positive number"))

        for numeric_field in OPTIONAL_NUMERIC:
            raw_val = row.get(numeric_field)
            if raw_val is not None:
                parsed = _to_float(raw_val)
                if parsed is None or parsed < 0:
                    row_errors.append(RowError(idx, numeric_field, f"{numeric_field} must be a non-negative number"))

        zone_code = row.get("zone_code")
        if zone_code:
            zone_type = row.get("zone_type")
            if zone_code not in existing_zone_codes and zone_code not in seen_zone_codes_in_file:
                if not zone_type or zone_type not in ZONE_TYPES:
                    row_errors.append(
                        RowError(
                            idx,
                            "zone_type",
                            f"zone_code '{zone_code}' is not a known zone; provide a valid zone_type to create it. Allowed: {sorted(ZONE_TYPES)}",
                        )
                    )
                else:
                    seen_zone_codes_in_file[zone_code] = {
                        "zone_code": zone_code,
                        "zone_type": zone_type,
                        "name": row.get("zone_name") or zone_code,
                    }

        if not row_errors and x is not None and y is not None and width is not None and height is not None:
            bounding_boxes.append((idx, location_code or f"row{idx}", x, y, width, height))

        if row_errors:
            report.errors.extend(row_errors)
            report.invalid_rows += 1
        else:
            report.valid_rows += 1
            report.locations.append(
                {
                    "location_code": location_code,
                    "location_type": location_type,
                    "storage_type": storage_type,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "depth": _to_float(row.get("depth")),
                    "max_weight": _to_float(row.get("max_weight")),
                    "max_volume": _to_float(row.get("max_volume")),
                    "aisle": row.get("aisle"),
                    "rack": row.get("rack"),
                    "shelf": row.get("shelf"),
                    "bin": row.get("bin"),
                    "zone_code": zone_code,
                }
            )

    # Overlap check: two rectangles overlap if they intersect on both axes.
    overlapping_codes: set[str] = set()
    for i in range(len(bounding_boxes)):
        idx_a, code_a, xa, ya, wa, ha = bounding_boxes[i]
        for j in range(i + 1, len(bounding_boxes)):
            idx_b, code_b, xb, yb, wb, hb = bounding_boxes[j]
            overlap_x = xa < xb + wb and xb < xa + wa
            overlap_y = ya < yb + hb and yb < ya + ha
            if overlap_x and overlap_y:
                report.errors.append(
                    RowError(idx_b, "x/y", f"Location '{code_b}' overlaps with '{code_a}' (row {idx_a})")
                )
                overlapping_codes.add(code_b)

    if overlapping_codes:
        kept_locations = [loc for loc in report.locations if loc["location_code"] not in overlapping_codes]
        removed = len(report.locations) - len(kept_locations)
        report.locations = kept_locations
        report.valid_rows = max(0, report.valid_rows - removed)
        report.invalid_rows += removed

    if report.total_rows > 0:
        if not has_receiving and not warehouse_already_has_receiving:
            report.errors.append(RowError(0, "location_type", "Layout is missing a receiving point (location_type='receiving')"))
        if not has_dispatch and not warehouse_already_has_dispatch:
            report.errors.append(RowError(0, "location_type", "Layout is missing a dispatch point (location_type='dispatch')"))

    report.zones = seen_zone_codes_in_file
    return report
