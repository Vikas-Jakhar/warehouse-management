"""Prepares a raw sequence of (date, quantity) sales rows into a clean daily
time series, and characterizes it (trend / seasonality / intermittency /
variability) so the model-selection step can pick a sensible model without a
person having to configure one. Per spec section 12: 'the system must not
depend on one hardcoded formula.'
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd


@dataclass
class SeriesProfile:
    length_days: int
    zero_fraction: float
    is_intermittent: bool
    has_trend: bool
    trend_slope: float
    has_weekly_seasonality: bool
    coefficient_of_variation: float
    outlier_count: int


def build_daily_series(rows: list[tuple[date, float]]) -> pd.Series:
    """Aggregates raw sales rows to one total-quantity-per-day series, filling
    any days with no sales as 0 demand (not missing data - the SKU simply
    didn't sell that day) so the series has no gaps for the models below.
    """
    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows, columns=["date", "quantity"])
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date")["quantity"].sum()

    full_index = pd.date_range(start=daily.index.min(), end=daily.index.max(), freq="D")
    daily = daily.reindex(full_index, fill_value=0.0)
    return daily


def detect_outliers(series: pd.Series) -> pd.Series:
    """IQR-based outlier flag. Returns a boolean Series aligned to the input."""
    if len(series) < 8:
        return pd.Series(False, index=series.index)
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series(False, index=series.index)
    lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
    return (series < lower) | (series > upper)


def winsorize_outliers(series: pd.Series, outlier_mask: pd.Series) -> pd.Series:
    """Caps flagged outliers at the nearest non-outlier bound rather than
    dropping them, so a single freak spike doesn't distort model training
    while still preserving the day's data point.
    """
    if not outlier_mask.any():
        return series
    clean_values = series[~outlier_mask]
    if clean_values.empty:
        return series
    cap = clean_values.max()
    floor = clean_values.min()
    return series.clip(lower=floor, upper=cap)


def _has_weekly_seasonality(series: pd.Series) -> bool:
    if len(series) < 21:  # need at least 3 full weeks to say anything
        return False
    try:
        shifted = series.shift(7)
        valid = shifted.notna()
        if valid.sum() < 14:
            return False
        corr = series[valid].corr(shifted[valid])
        return bool(corr is not None and not np.isnan(corr) and corr > 0.3)
    except Exception:  # noqa: BLE001
        return False


def _trend_slope(series: pd.Series) -> tuple[bool, float]:
    if len(series) < 10:
        return False, 0.0
    x = np.arange(len(series))
    y = series.to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    mean_level = max(np.mean(y), 1e-6)
    relative_slope = slope * len(series) / mean_level
    return bool(abs(relative_slope) > 0.15), float(slope)


def profile_series(series: pd.Series) -> SeriesProfile:
    outliers = detect_outliers(series)
    zero_fraction = float((series == 0).mean()) if len(series) else 1.0
    has_trend, slope = _trend_slope(series)
    mean = float(series.mean()) if len(series) else 0.0
    std = float(series.std()) if len(series) else 0.0
    cv = std / mean if mean > 0 else 0.0

    return SeriesProfile(
        length_days=len(series),
        zero_fraction=zero_fraction,
        is_intermittent=zero_fraction > 0.6,
        has_trend=has_trend,
        trend_slope=slope,
        has_weekly_seasonality=_has_weekly_seasonality(series),
        coefficient_of_variation=cv,
        outlier_count=int(outliers.sum()),
    )


def next_horizon_dates(last_date: date, horizon_days: int) -> list[date]:
    return [last_date + timedelta(days=i) for i in range(1, horizon_days + 1)]
