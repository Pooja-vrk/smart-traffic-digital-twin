"""ML model for congestion prediction."""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from prediction.config import PredictionConfig

logger = logging.getLogger(__name__)


class CongestionPredictionModel:
    """Random Forest model for congestion prediction."""

    def __init__(
        self,
        n_estimators: int = None,
        max_depth: int = None,
        random_state: int = None,
        n_jobs: int = None,
    ):
        """
        Initialize the congestion prediction model.

        Args:
            n_estimators: Number of trees in the forest (uses config default if None).
            max_depth: Maximum depth of trees (uses config default if None).
            random_state: Random seed (uses config default if None).
            n_jobs: Number of parallel jobs (uses config default if None).
        """
        if n_estimators is None:
            n_estimators = PredictionConfig.MODEL_N_ESTIMATORS
        if max_depth is None:
            max_depth = PredictionConfig.MODEL_MAX_DEPTH
        if random_state is None:
            random_state = PredictionConfig.RANDOM_STATE
        if n_jobs is None:
            n_jobs = PredictionConfig.MODEL_N_JOBS

        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=n_jobs,
            warm_start=False,
        )

        self.feature_names: Optional[list[str]] = None
        self.is_trained = False

        logger.info(
            "Initialized RandomForestRegressor with n_estimators=%d, max_depth=%d",
            n_estimators, max_depth
        )

    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> None:
        """
        Train the congestion prediction model.

        Args:
            X: Feature matrix (n_samples, n_features).
            y: Target vector (n_samples,).
            feature_names: List of feature names corresponding to columns in X.

        Raises:
            ValueError: If X and y have incompatible shapes.
        """
        if X.shape[0] != y.shape[0]:
            raise ValueError(
                f"X and y have incompatible shapes: X={X.shape}, y={y.shape}"
            )

        logger.info("Training model on %d samples with %d features", X.shape[0], X.shape[1])

        self.model.fit(X, y)
        self.feature_names = feature_names
        self.is_trained = True

        logger.info("Model training completed")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions on feature matrix.

        Args:
            X: Feature matrix (n_samples, n_features).

        Returns:
            Predicted congestion scores (n_samples,).

        Raises:
            RuntimeError: If model is not trained.
            ValueError: If feature dimensions don't match training data.
        """
        if not self.is_trained:
            raise RuntimeError("Model must be trained before making predictions")

        if X.shape[1] != len(self.feature_names):
            raise ValueError(
                f"Feature dimension mismatch: expected {len(self.feature_names)}, got {X.shape[1]}"
            )

        predictions = self.model.predict(X)

        # Clip predictions to [0, 100] range
        predictions = np.clip(predictions, 0.0, 100.0)

        return predictions

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance scores.

        Returns:
            Dictionary mapping feature names to importance scores.

        Raises:
            RuntimeError: If model is not trained.
        """
        if not self.is_trained:
            raise RuntimeError("Model must be trained to get feature importance")

        if self.feature_names is None:
            raise RuntimeError("Feature names not available")

        importances = self.model.feature_importances_

        return dict(zip(self.feature_names, importances))

    def get_model_info(self) -> Dict:
        """
        Get model metadata.

        Returns:
            Dictionary with model information.
        """
        return {
            "model_type": "RandomForestRegressor",
            "n_estimators": self.model.n_estimators,
            "max_depth": self.model.max_depth,
            "random_state": self.model.random_state,
            "is_trained": self.is_trained,
            "feature_count": len(self.feature_names) if self.feature_names else 0,
            "feature_names": self.feature_names,
        }


class BaselinePredictor:
    """Simple baseline predictor using current congestion score."""

    def __init__(self):
        """Initialize baseline predictor."""
        self.is_trained = True  # Basine doesn't need training

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make baseline predictions using current congestion score.

        Args:
            X: Feature matrix (n_samples, n_features).

        Returns:
            Predicted congestion scores (n_samples,).
        """
        # The baseline simply predicts that future congestion equals current congestion
        # We assume the last feature is current_congestion_score
        predictions = X[:, -1]  # Last column
        return predictions

    def get_model_info(self) -> Dict:
        """Get baseline model metadata."""
        return {
            "model_type": "BaselinePredictor",
            "description": "Predicts future congestion equals current congestion",
            "is_trained": self.is_trained,
        }
