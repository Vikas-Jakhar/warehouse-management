"""Shared CSV/Excel/JSON parsing for all bulk-upload endpoints (layout, SKU,
sales, inventory). Kept separate from any one domain's validation rules.
"""

import io
import json
from typing import Any

import pandas as pd


def parse_tabular_upload(filename: str, content: bytes) -> list[dict[str, Any]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    elif lower.endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, dict):
            for key in ("records", "items", "rows", "data"):
                if key in data:
                    data = data[key]
                    break
        df = pd.DataFrame(data)
    else:
        raise ValueError("Unsupported file type. Use .csv, .xlsx, or .json")

    # NaN survives `.where(..., None)` on numeric-dtype columns because pandas
    # casts None back to NaN to preserve the column's float dtype. Casting to
    # object first avoids that recast, so genuinely empty cells become None.
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient="records")
