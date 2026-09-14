"""Standard forecast accuracy metrics (section 12). All functions take
parallel arrays of actual vs. predicted values over the backtest window.
"""

import numpy as np


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Undefined when actual demand is zero; return None rather than inf/NaN
    so callers can fall back to WAPE, which the spec lists as the safer
    metric for intermittent demand.
    """
    nonzero = actual != 0
    if not nonzero.any():
        return None
    return float(np.mean(np.abs((actual[nonzero] - predicted[nonzero]) / actual[nonzero])) * 100)


def wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Weighted Absolute Percentage Error - well-defined even with zero-demand
    days, which is why it's the primary metric used for model selection here.
    """
    denom = np.sum(np.abs(actual))
    if denom == 0:
        return float(np.sum(np.abs(predicted)))
    return float(np.sum(np.abs(actual - predicted)) / denom * 100)


def bias(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Positive bias = systematic over-forecasting; negative = under-forecasting."""
    return float(np.mean(predicted - actual))


def evaluate_all(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "mape": mape(actual, predicted),
        "wape": wape(actual, predicted),
        "bias": bias(actual, predicted),
    }
