"""Predictor service for real-time congestion prediction."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

import joblib
import numpy as np

from backend.schemas.traffic import PredictionLiveInfo
from prediction.config import PredictionConfig
from prediction.congestion import build_congestion_score, classify_congestion
from prediction.feature_engineering import extract_features, get_feature_names, prepare_feature_vector
from prediction.live_evaluator import LiveForecastTracker
from prediction.model import BaselinePredictor, CongestionPredictionModel

logger = logging.getLogger(__name__)


class FeatureMetadata:
    """Metadata about features used for training."""

    def __init__(
        self,
        feature_names: list[str],
        feature_version: str,
        target_definition: str,
        prediction_horizon: float,
        model_name: str,
        model_parameters: Dict,
        training_timestamp: str,
        dataset_size: int,
        random_seed: int,
    ):
        self.feature_names = feature_names
        self.feature_version = feature_version
        self.target_definition = target_definition
        self.prediction_horizon = prediction_horizon
        self.model_name = model_name
        self.model_parameters = model_parameters
        self.training_timestamp = training_timestamp
        self.dataset_size = dataset_size
        self.random_seed = random_seed

    def to_dict(self) -> Dict:
        """Convert metadata to dictionary."""
        return {
            "feature_names": self.feature_names,
            "feature_version": self.feature_version,
            "target_definition": self.target_definition,
            "prediction_horizon": self.prediction_horizon,
            "model_name": self.model_name,
            "model_parameters": self.model_parameters,
            "training_timestamp": self.training_timestamp,
            "dataset_size": self.dataset_size,
            "random_seed": self.random_seed,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "FeatureMetadata":
        """Create FeatureMetadata from dictionary."""
        return cls(
            feature_names=data["feature_names"],
            feature_version=data["feature_version"],
            target_definition=data["target_definition"],
            prediction_horizon=data["prediction_horizon"],
            model_name=data["model_name"],
            model_parameters=data["model_parameters"],
            training_timestamp=data["training_timestamp"],
            dataset_size=data["dataset_size"],
            random_seed=data["random_seed"],
        )


class CongestionPredictor:
    """Real-time congestion prediction service."""

    def __init__(self):
        """Initialize the predictor."""
        self.model: Optional[CongestionPredictionModel] = None
        self.baseline: BaselinePredictor = BaselinePredictor()
        self.feature_metadata: Optional[FeatureMetadata] = None
        self.is_loaded = False
        self.live_tracker = LiveForecastTracker(
            horizon_seconds=PredictionConfig.PREDICTION_HORIZON_SECONDS,
            match_tolerance_seconds=1.0,
        )
        self._history: deque = deque(maxlen=10)
        self._current_simulation_id: Optional[str] = None
        self._cached_step_key: Optional[tuple] = None
        self._cached_step_prediction: Optional[PredictionLiveInfo] = None

    def reset_live_tracker(self, simulation_id: Optional[str] = None) -> None:
        """Reset time-aligned evaluation tracker and rolling snapshot history."""
        self._current_simulation_id = simulation_id
        self._history.clear()
        self._cached_step_key = None
        self._cached_step_prediction = None
        self.live_tracker.reset(simulation_id)

    def get_live_tracker_metrics(self) -> Dict[str, Any]:
        """Return cumulative live MAE/RMSE and time-aligned evaluation statistics."""
        return self.live_tracker.get_metrics()

    def load_model(
        self,
        model_path: Optional[Path] = None,
        metadata_path: Optional[Path] = None,
    ) -> bool:
        """
        Load trained model and feature metadata from disk.

        Args:
            model_path: Path to model file (uses config default if None).
            metadata_path: Path to metadata file (uses config default if None).

        Returns:
            True if model loaded successfully, False otherwise.
        """
        if model_path is None:
            model_path = PredictionConfig.MODEL_PATH
        if metadata_path is None:
            metadata_path = PredictionConfig.FEATURE_METADATA_PATH

        if not model_path.exists():
            logger.warning("Model file not found: %s", model_path)
            return False

        if not metadata_path.exists():
            logger.warning("Feature metadata file not found: %s", metadata_path)
            return False

        try:
            # Load model
            self.model = joblib.load(model_path)

            # Load metadata
            with open(metadata_path, "r") as f:
                metadata_dict = json.load(f)
            self.feature_metadata = FeatureMetadata.from_dict(metadata_dict)

            # Validate feature ordering
            expected_features = get_feature_names()
            if self.feature_metadata.feature_names != expected_features:
                logger.warning(
                    "Feature names mismatch between model and current implementation. "
                    "Model: %s, Current: %s",
                    self.feature_metadata.feature_names[:5],
                    expected_features[:5]
                )

            self.is_loaded = True
            logger.info("Model loaded successfully from %s", model_path)
            return True

        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            return False

    def predict(
        self,
        snapshot: Dict,
        historical_snapshots: Optional[list[Dict]] = None,
    ) -> Dict:
        """
        Predict future congestion for a traffic snapshot.

        Args:
            snapshot: Current traffic snapshot.
            historical_snapshots: Historical snapshots for lag features (optional).

        Returns:
            Dictionary with prediction results.

        Raises:
            RuntimeError: If model is not loaded.
        """
        if not self.is_loaded or self.model is None:
            raise RuntimeError("Model is not loaded. Call load_model() first.")

        # Extract features
        features = extract_features(snapshot, historical_snapshots)
        feature_vector = prepare_feature_vector(features)

        # Reshape for prediction
        X = feature_vector.reshape(1, -1)

        # Make prediction
        predicted_score = self.model.predict(X)[0]

        # Classify congestion level
        congestion_level = classify_congestion(predicted_score)

        # Get baseline prediction
        baseline_score = self.baseline.predict(X)[0]

        return {
            "predicted_congestion_score": float(predicted_score),
            "congestion_level": congestion_level,
            "prediction_horizon": self.feature_metadata.prediction_horizon if self.feature_metadata else PredictionConfig.PREDICTION_HORIZON_SECONDS,
            "model_name": self.feature_metadata.model_name if self.feature_metadata else "unknown",
            "model_available": True,
            "baseline_score": float(baseline_score),
            "current_congestion_score": features.get("current_congestion_score", 0.0),
        }

    def predict_live(
        self,
        snapshot: Dict,
        simulation_id: Optional[str] = None,
        step: int = 0,
        simulation_time: float = 0.0,
    ) -> PredictionLiveInfo:
        """
        Produce a non-fatal, cached real-time congestion forecast with 80% CI and live evaluation.

        - Avoids redundant inference if called multiple times for the same simulation step.
        - Isolates failures (returns safe fallback with model_available=False instead of throwing).
        - Automatically manages temporal lag feature history.
        - Verifies past predictions against actual observed congestion at t + 30s.
        """
        # Step cache check: prevent duplicate inference for identical simulation step
        cache_key = (simulation_id, step, round(float(simulation_time), 2))
        if self._cached_step_key == cache_key and self._cached_step_prediction is not None:
            return self._cached_step_prediction

        # Reset history and tracker if simulation ID changed
        if simulation_id is not None and simulation_id != self._current_simulation_id:
            self.reset_live_tracker(simulation_id)

        # Lazy load model if needed
        if not self.is_loaded or self.model is None:
            self.load_model()

        # Compute current actual congestion score for this snapshot
        try:
            current_score = float(build_congestion_score(snapshot))
        except Exception:
            current_score = 0.0

        # Step 1: Time-aligned verification of past predictions targeting current simulation_time
        if simulation_id is not None:
            self.live_tracker.evaluate_step(
                simulation_id=simulation_id,
                simulation_time=simulation_time,
                actual_score=current_score,
            )

        # Retrieve running verification metrics
        eval_metrics = self.live_tracker.get_metrics()

        # Fallback if model could not be loaded
        if not self.is_loaded or self.model is None:
            fallback = PredictionLiveInfo(
                model_available=False,
                model_name=None,
                predicted_score=round(current_score, 2),
                current_score=round(current_score, 2),
                congestion_level=classify_congestion(current_score) if 0 <= current_score <= 100 else "FREE_FLOW",
                horizon_seconds=PredictionConfig.PREDICTION_HORIZON_SECONDS,
                trend="STABLE",
                confidence_lower=round(current_score, 2),
                confidence_upper=round(current_score, 2),
                std_dev=0.0,
                baseline_score=round(current_score, 2),
                evaluated_samples=eval_metrics.get("evaluated_samples", 0),
                live_mae=eval_metrics.get("live_mae"),
                live_rmse=eval_metrics.get("live_rmse"),
                baseline_mae=eval_metrics.get("baseline_mae"),
                mae_improvement_pct=eval_metrics.get("mae_improvement_pct"),
                last_verified_actual=eval_metrics.get("last_verified_actual"),
                last_verified_predicted=eval_metrics.get("last_verified_predicted"),
            )
            self._cached_step_key = cache_key
            self._cached_step_prediction = fallback
            return fallback

        try:
            # Extract features using rolling snapshot history
            hist_list = list(self._history)
            features = extract_features(snapshot, hist_list if hist_list else None)
            feature_vector = prepare_feature_vector(features)
            X = feature_vector.reshape(1, -1)

            # Predict future congestion score
            predicted_score = float(self.model.predict(X)[0])
            predicted_score = max(0.0, min(100.0, predicted_score))

            # Empirical 80% confidence interval across the 200 random forest trees
            conf_lower = predicted_score
            conf_upper = predicted_score
            std_dev = 0.0

            inner_rf = getattr(self.model, "model", None)
            if inner_rf is not None and hasattr(inner_rf, "estimators_") and len(inner_rf.estimators_) > 0:
                tree_preds = np.array([tree.predict(X)[0] for tree in inner_rf.estimators_])
                conf_lower = float(np.percentile(tree_preds, 10))
                conf_upper = float(np.percentile(tree_preds, 90))
                std_dev = float(np.std(tree_preds))

                conf_lower = max(0.0, min(100.0, conf_lower))
                conf_upper = max(0.0, min(100.0, conf_upper))
                std_dev = round(std_dev, 2)

            # Congestion level classification
            congestion_level = classify_congestion(predicted_score)

            # Trend relative to current score
            diff = predicted_score - current_score
            if diff > 2.0:
                trend = "INCREASING"
            elif diff < -2.0:
                trend = "DECREASING"
            else:
                trend = "STABLE"

            baseline_score = current_score

            # Record this forecast for future evaluation at (simulation_time + 30.0s)
            if simulation_id is not None:
                self.live_tracker.record_forecast(
                    simulation_id=simulation_id,
                    step=step,
                    simulation_time=simulation_time,
                    predicted_score=predicted_score,
                    baseline_score=baseline_score,
                    horizon_seconds=self.feature_metadata.prediction_horizon if self.feature_metadata else PredictionConfig.PREDICTION_HORIZON_SECONDS,
                )

            # Update rolling snapshot history
            self._history.append(dict(snapshot))

            result = PredictionLiveInfo(
                model_available=True,
                model_name=self.feature_metadata.model_name if self.feature_metadata else "RandomForestRegressor",
                predicted_score=round(predicted_score, 2),
                current_score=round(current_score, 2),
                congestion_level=congestion_level,
                horizon_seconds=self.feature_metadata.prediction_horizon if self.feature_metadata else PredictionConfig.PREDICTION_HORIZON_SECONDS,
                trend=trend,
                confidence_lower=round(conf_lower, 2),
                confidence_upper=round(conf_upper, 2),
                std_dev=std_dev,
                baseline_score=round(baseline_score, 2),
                evaluated_samples=eval_metrics.get("evaluated_samples", 0),
                live_mae=eval_metrics.get("live_mae"),
                live_rmse=eval_metrics.get("live_rmse"),
                baseline_mae=eval_metrics.get("baseline_mae"),
                mae_improvement_pct=eval_metrics.get("mae_improvement_pct"),
                last_verified_actual=eval_metrics.get("last_verified_actual"),
                last_verified_predicted=eval_metrics.get("last_verified_predicted"),
            )

            self._cached_step_key = cache_key
            self._cached_step_prediction = result
            return result

        except Exception as exc:
            logger.warning("predict_live failed: %s; returning fallback", exc)
            fallback = PredictionLiveInfo(
                model_available=False,
                model_name=self.feature_metadata.model_name if self.feature_metadata else None,
                predicted_score=round(current_score, 2),
                current_score=round(current_score, 2),
                congestion_level="UNKNOWN",
                trend="STABLE",
                baseline_score=round(current_score, 2),
                evaluated_samples=eval_metrics.get("evaluated_samples", 0),
                live_mae=eval_metrics.get("live_mae"),
                live_rmse=eval_metrics.get("live_rmse"),
            )
            self._cached_step_key = cache_key
            self._cached_step_prediction = fallback
            return fallback

    def get_status(self) -> Dict:
        """
        Get predictor status including top feature importances.

        Returns:
            Dictionary with status information.
        """
        importances = None
        if self.is_loaded and self.model is not None:
            try:
                importances = self.model.get_feature_importance()
                if importances:
                    # Sort by importance descending, take top 8
                    importances = dict(sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:8])
            except Exception:
                importances = None

        return {
            "model_available": self.is_loaded,
            "model_name": self.feature_metadata.model_name if self.feature_metadata else None,
            "prediction_horizon": self.feature_metadata.prediction_horizon if self.feature_metadata else None,
            "feature_count": len(self.feature_metadata.feature_names) if self.feature_metadata else 0,
            "last_training_time": self.feature_metadata.training_timestamp if self.feature_metadata else None,
            "feature_version": self.feature_metadata.feature_version if self.feature_metadata else None,
            "feature_importances": importances,
        }


# Global predictor instance
predictor = CongestionPredictor()
