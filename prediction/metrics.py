"""Evaluation metrics for congestion prediction."""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from prediction.congestion import classify_congestion

logger = logging.getLogger(__name__)


class PredictionMetrics:
    """Container for prediction evaluation metrics."""

    def __init__(
        self,
        mae: float,
        rmse: float,
        r2: float,
        baseline_mae: float,
        baseline_rmse: float,
        baseline_r2: float,
        classification_accuracy: Optional[float] = None,
    ):
        self.mae = mae
        self.rmse = rmse
        self.r2 = r2
        self.baseline_mae = baseline_mae
        self.baseline_rmse = baseline_rmse
        self.baseline_r2 = baseline_r2
        self.classification_accuracy = classification_accuracy

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary."""
        result = {
            "ml_model": {
                "mae": round(self.mae, 4),
                "rmse": round(self.rmse, 4),
                "r2": round(self.r2, 4),
            },
            "baseline": {
                "mae": round(self.baseline_mae, 4),
                "rmse": round(self.baseline_rmse, 4),
                "r2": round(self.baseline_r2, 4),
            },
            "improvement_over_baseline": {
                "mae_reduction_pct": round(
                    (self.baseline_mae - self.mae) / self.baseline_mae * 100, 2
                    if self.baseline_mae > 0 else 0.0
                ),
                "rmse_reduction_pct": round(
                    (self.baseline_rmse - self.rmse) / self.baseline_rmse * 100, 2
                    if self.baseline_rmse > 0 else 0.0
                ),
                "r2_improvement": round(self.r2 - self.baseline_r2, 4),
            },
        }

        if self.classification_accuracy is not None:
            result["classification_accuracy"] = round(self.classification_accuracy, 4)

        return result


def calculate_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Dict[str, float]:
    """
    Calculate regression evaluation metrics.

    Args:
        y_true: True target values.
        y_pred: Predicted values.

    Returns:
        Dictionary with MAE, RMSE, and R² scores.
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)

    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
    }


def calculate_classification_accuracy(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """
    Calculate classification accuracy based on congestion levels.

    Args:
        y_true: True congestion scores.
        y_pred: Predicted congestion scores.

    Returns:
        Classification accuracy (0-1).
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")

    correct = 0
    for true_score, pred_score in zip(y_true, y_pred):
        true_level = classify_congestion(true_score)
        pred_level = classify_congestion(pred_score)
        if true_level == pred_level:
            correct += 1

    accuracy = correct / len(y_true)
    return accuracy


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred_ml: np.ndarray,
    y_pred_baseline: np.ndarray,
) -> PredictionMetrics:
    """
    Evaluate ML model predictions against baseline.

    Args:
        y_true: True target values.
        y_pred_ml: ML model predictions.
        y_pred_baseline: Baseline predictions.

    Returns:
        PredictionMetrics object with evaluation results.
    """
    # Calculate ML model metrics
    ml_metrics = calculate_regression_metrics(y_true, y_pred_ml)

    # Calculate baseline metrics
    baseline_metrics = calculate_regression_metrics(y_true, y_pred_baseline)

    # Calculate classification accuracy
    try:
        classification_accuracy = calculate_classification_accuracy(y_true, y_pred_ml)
    except Exception as exc:
        logger.warning("Failed to calculate classification accuracy: %s", exc)
        classification_accuracy = None

    logger.info(
        "ML Model - MAE: %.4f, RMSE: %.4f, R²: %.4f",
        ml_metrics["mae"], ml_metrics["rmse"], ml_metrics["r2"]
    )
    logger.info(
        "Baseline - MAE: %.4f, RMSE: %.4f, R²: %.4f",
        baseline_metrics["mae"], baseline_metrics["rmse"], baseline_metrics["r2"]
    )

    return PredictionMetrics(
        mae=ml_metrics["mae"],
        rmse=ml_metrics["rmse"],
        r2=ml_metrics["r2"],
        baseline_mae=baseline_metrics["mae"],
        baseline_rmse=baseline_metrics["rmse"],
        baseline_r2=baseline_metrics["r2"],
        classification_accuracy=classification_accuracy,
    )
