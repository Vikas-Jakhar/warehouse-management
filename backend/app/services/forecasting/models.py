"""Candidate forecasting models. Each exposes forecast(train, horizon) ->
np.ndarray of length `horizon`, so the pipeline can backtest and compare them
interchangeably (section 12: 'must not depend on one hardcoded formula').
Every model is defensive about small/degenerate input - a model that can't
run on the available data simply isn't offered as a candidate rather than
raising, so a single failing model never blocks the pipeline.
"""

import warnings

import numpy as np

warnings.filterwarnings("ignore")


def naive(train: np.ndarray, horizon: int) -> np.ndarray:
    """Repeats the last observed value - the baseline every other candidate
    must beat to be worth using.
    """
    last = train[-1] if len(train) else 0.0
    return np.full(horizon, last, dtype=float)


def seasonal_naive(train: np.ndarray, horizon: int, period: int = 7) -> np.ndarray:
    """Repeats the value from `period` steps ago, cycling - a strong, simple
    baseline whenever weekly seasonality is present.
    """
    if len(train) < period:
        return naive(train, horizon)
    last_cycle = train[-period:]
    return np.array([last_cycle[i % period] for i in range(horizon)], dtype=float)


def moving_average(train: np.ndarray, horizon: int, window: int = 7) -> np.ndarray:
    window = min(window, len(train)) or 1
    avg = float(np.mean(train[-window:]))
    return np.full(horizon, avg, dtype=float)


def croston(train: np.ndarray, horizon: int, alpha: float = 0.2) -> np.ndarray:
    """Croston's method for intermittent demand: separately smooths demand
    *size* (non-zero values) and the *interval* between demand events, then
    forecasts their ratio. Standard exponential smoothing badly over- or
    under-forecasts intermittent series, which is why this gets offered
    specifically when zero_fraction is high.
    """
    demand_sizes = []
    intervals = []
    since_last = 0
    for value in train:
        since_last += 1
        if value > 0:
            demand_sizes.append(value)
            intervals.append(since_last)
            since_last = 0

    if not demand_sizes:
        return np.zeros(horizon, dtype=float)

    z = demand_sizes[0]
    p = intervals[0] if intervals else 1
    for i in range(1, len(demand_sizes)):
        z = alpha * demand_sizes[i] + (1 - alpha) * z
        p = alpha * intervals[i] + (1 - alpha) * p

    rate = z / p if p > 0 else 0.0
    return np.full(horizon, rate, dtype=float)


def exponential_smoothing(train: np.ndarray, horizon: int) -> np.ndarray | None:
    if len(train) < 10:
        return None
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        series = np.where(train <= 0, 1e-6, train)  # multiplicative-safe
        model = ExponentialSmoothing(series, trend="add", seasonal=None, initialization_method="estimated")
        fitted = model.fit(optimized=True)
        forecast = fitted.forecast(horizon)
        return np.clip(np.asarray(forecast, dtype=float), 0, None)
    except Exception:  # noqa: BLE001
        return None


def holt_winters_seasonal(train: np.ndarray, horizon: int, period: int = 7) -> np.ndarray | None:
    if len(train) < period * 2 + 1:
        return None
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        series = np.where(train <= 0, 1e-6, train)
        model = ExponentialSmoothing(
            series, trend="add", seasonal="add", seasonal_periods=period, initialization_method="estimated"
        )
        fitted = model.fit(optimized=True)
        forecast = fitted.forecast(horizon)
        return np.clip(np.asarray(forecast, dtype=float), 0, None)
    except Exception:  # noqa: BLE001
        return None


def sarima(train: np.ndarray, horizon: int, period: int = 7) -> np.ndarray | None:
    if len(train) < period * 3:
        return None
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        model = SARIMAX(
            train,
            order=(1, 1, 1),
            seasonal_order=(1, 0, 1, period),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fitted = model.fit(disp=False)
        forecast = fitted.forecast(horizon)
        return np.clip(np.asarray(forecast, dtype=float), 0, None)
    except Exception:  # noqa: BLE001
        return None


def random_forest_lags(train: np.ndarray, horizon: int, n_lags: int = 7) -> np.ndarray | None:
    """Lag-feature regression - useful once there's enough history for the
    model to learn a real lag structure instead of memorizing noise.
    Forecasts recursively: each predicted step becomes a lag feature for the
    next.
    """
    if len(train) < n_lags + 10:
        return None
    try:
        from sklearn.ensemble import RandomForestRegressor

        X, y = [], []
        for i in range(n_lags, len(train)):
            X.append(train[i - n_lags : i])
            y.append(train[i])
        X, y = np.array(X), np.array(y)

        model = RandomForestRegressor(n_estimators=200, max_depth=6, random_state=42)
        model.fit(X, y)

        history = list(train[-n_lags:])
        predictions = []
        for _ in range(horizon):
            next_val = model.predict(np.array(history[-n_lags:]).reshape(1, -1))[0]
            next_val = max(0.0, float(next_val))
            predictions.append(next_val)
            history.append(next_val)
        return np.array(predictions, dtype=float)
    except Exception:  # noqa: BLE001
        return None


MODEL_REGISTRY = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "moving_average": moving_average,
    "croston": croston,
    "exponential_smoothing": exponential_smoothing,
    "holt_winters_seasonal": holt_winters_seasonal,
    "sarima": sarima,
    "random_forest": random_forest_lags,
}
