"""Predictor service for real-time congestion prediction."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import joblib
import numpy as np

from prediction.config import PredictionConfig
from prediction.congestion import classify_congestion
from prediction.feature_engineering import extract_features, get_feature_names, prepare_feature_vector
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

    def get_status(self) -> Dict:
        """
        Get predictor status.

        Returns:
            Dictionary with status information.
        """
        return {
            "model_available": self.is_loaded,
            "model_name": self.feature_metadata.model_name if self.feature_metadata else None,
            "prediction_horizon": self.feature_metadata.prediction_horizon if self.feature_metadata else None,
            "feature_count": len(self.feature_metadata.feature_names) if self.feature_metadata else 0,
            "last_training_time": self.feature_metadata.training_timestamp if self.feature_metadata else None,
            "feature_version": self.feature_metadata.feature_version if self.feature_metadata else None,
        }


# Global predictor instance
predictor = CongestionPredictor()
