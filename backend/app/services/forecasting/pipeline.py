"""Orchestrates the full forecasting pipeline for one SKU's daily demand
series, matching the stages in spec section 12:
validate -> prepare time-series -> train models -> evaluate models ->
generate forecasts -> save results.

This module is pure (no DB, no Celery) so it's directly unit-testable; the
Celery task in tasks.py is a thin wrapper that persists what this returns.
"""

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from app.services.forecasting import metrics as metrics_mod
from app.services.forecasting.models import MODEL_REGISTRY
from app.services.forecasting.timeseries import (
    SeriesProfile,
    build_daily_series,
    detect_outliers,
    next_horizon_dates,
    profile_series,
    winsorize_outliers,
)

MIN_HISTORY_DAYS = 3


@dataclass
class ModelEvaluation:
    model_name: str
    mae: float
    rmse: float
    mape: float | None
    wape: float
    bias: float
    chosen: bool = False


@dataclass
class ForecastOutcome:
    sku_id: str
    horizon_dates: list[date] = field(default_factory=list)
    forecast_values: list[float] = field(default_factory=list)
    lower_ci: list[float] = field(default_factory=list)
    upper_ci: list[float] = field(default_factory=list)
    chosen_model: str | None = None
    evaluations: list[ModelEvaluation] = field(default_factory=list)
    profile: SeriesProfile | None = None
    skipped_reason: str | None = None


def _candidate_models(profile: SeriesProfile) -> list[str]:
    """Picks which models are even worth trying, based on the series'
    characteristics - this is the 'automatically select or compare models
    based on data size, seasonality, trend, intermittent demand, demand
    variability' requirement from section 12.
    """
    candidates = ["naive", "moving_average"]

    if profile.is_intermittent:
        candidates.append("croston")
        return candidates  # seasonal/ARIMA models are unreliable on sparse series

    if profile.has_weekly_seasonality:
        candidates.append("seasonal_naive")

    if profile.length_days >= 10:
        candidates.append("exponential_smoothing")

    if profile.has_weekly_seasonality and profile.length_days >= 15:
        candidates.append("holt_winters_seasonal")

    if profile.length_days >= 21:
        candidates.append("sarima")

    if profile.length_days >= 17:
        candidates.append("random_forest")

    return candidates


def _backtest(train: np.ndarray, test: np.ndarray, model_name: str) -> ModelEvaluation | None:
    fn = MODEL_REGISTRY[model_name]
    predicted = fn(train, len(test))
    if predicted is None:
        return None
    scores = metrics_mod.evaluate_all(test, predicted)
    return ModelEvaluation(
        model_name=model_name,
        mae=scores["mae"],
        rmse=scores["rmse"],
        mape=scores["mape"],
        wape=scores["wape"],
        bias=scores["bias"],
    )


def run_forecast_for_sku(
    sku_id: str,
    sales_rows: list[tuple[date, float]],
    horizon_days: int,
) -> ForecastOutcome:
    outcome = ForecastOutcome(sku_id=sku_id)

    series = build_daily_series(sales_rows)
    if len(series) < MIN_HISTORY_DAYS:
        outcome.skipped_reason = f"Not enough sales history ({len(series)} day(s); need at least {MIN_HISTORY_DAYS})"
        return outcome

    outliers = detect_outliers(series)
    clean_series = winsorize_outliers(series, outliers)
    profile = profile_series(clean_series)
    outcome.profile = profile

    values = clean_series.to_numpy(dtype=float)
    test_size = max(1, min(7, len(values) // 5)) if len(values) >= MIN_HISTORY_DAYS + 1 else 0

    evaluations: list[ModelEvaluation] = []
    if test_size > 0 and len(values) - test_size >= 2:
        train, test = values[:-test_size], values[-test_size:]
        for name in _candidate_models(profile):
            result = _backtest(train, test, name)
            if result is not None:
                evaluations.append(result)

    if not evaluations:
        # Not enough data to backtest meaningfully - fall back to naive
        # against the full series rather than failing the job outright.
        evaluations = [
            ModelEvaluation(model_name="naive", mae=0, rmse=0, mape=None, wape=0, bias=0),
        ]

    evaluations.sort(key=lambda e: e.wape)
    best = evaluations[0]
    best.chosen = True
    outcome.evaluations = evaluations
    outcome.chosen_model = best.model_name

    # Refit the chosen model on the *full* cleaned series for the real forecast.
    forecast_fn = MODEL_REGISTRY[best.model_name]
    final_forecast = forecast_fn(values, horizon_days)
    if final_forecast is None:
        final_forecast = MODEL_REGISTRY["naive"](values, horizon_days)

    residual_std = max(float(np.std(values)) * 0.5, 1e-6) if best.rmse == 0 else best.rmse
    z = 1.28  # ~80% interval
    lower = np.clip(final_forecast - z * residual_std, 0, None)
    upper = final_forecast + z * residual_std

    last_date = clean_series.index[-1].date()
    outcome.horizon_dates = next_horizon_dates(last_date, horizon_days)
    outcome.forecast_values = [round(float(v), 3) for v in final_forecast]
    outcome.lower_ci = [round(float(v), 3) for v in lower]
    outcome.upper_ci = [round(float(v), 3) for v in upper]

    return outcome
