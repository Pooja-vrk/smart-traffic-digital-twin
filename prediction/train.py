"""Training pipeline for congestion prediction model."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib

from prediction.config import PredictionConfig
from prediction.data_loader import DataLoader
from prediction.feature_engineering import get_feature_names
from prediction.metrics import evaluate_predictions
from prediction.model import BaselinePredictor, CongestionPredictionModel
from prediction.predictor import FeatureMetadata

logger = logging.getLogger(__name__)


def train_model(
    horizon_seconds: float = None,
    random_state: int = None,
) -> tuple[bool, str, dict]:
    """
    Train the congestion prediction model on historical data.

    Args:
        horizon_seconds: Prediction horizon in seconds (uses config default if None).
        random_state: Random seed (uses config default if None).

    Returns:
        Tuple of (success, message, metrics_dict).
    """
    if horizon_seconds is None:
        horizon_seconds = PredictionConfig.PREDICTION_HORIZON_SECONDS
    if random_state is None:
        random_state = PredictionConfig.RANDOM_STATE

    logger.info("Starting congestion prediction model training...")
    logger.info("Prediction horizon: %.2f seconds", horizon_seconds)

    # Ensure directories exist
    PredictionConfig.ensure_directories()

    # Connect to MongoDB before loading data
    from backend.database.connection import db_manager
    db_manager.connect()

    # Load historical data
    try:
        data_loader = DataLoader()
        statistics = data_loader.load_historical_data(status="completed")
        logger.info("Dataset statistics: %s", statistics.to_dict())
    except Exception as exc:
        error_msg = f"Failed to load historical data: {exc}"
        logger.error(error_msg)
        return False, error_msg, {}

    # Check data sufficiency
    is_sufficient, sufficiency_msg = data_loader.check_data_sufficiency()
    if not is_sufficient:
        error_msg = f"Insufficient training data: {sufficiency_msg}"
        logger.warning(error_msg)
        return False, error_msg, statistics.to_dict()

    # Prepare dataset
    try:
        X, y, feature_names = data_loader.prepare_dataset(random_state=random_state)
        logger.info("Prepared dataset: X shape=%s, y shape=%s", X.shape, y.shape)
    except Exception as exc:
        error_msg = f"Failed to prepare dataset: {exc}"
        logger.error(error_msg)
        return False, error_msg, statistics.to_dict()

    # Initialize model
    model = CongestionPredictionModel(random_state=random_state)

    # Train model
    try:
        model.train(X, y, feature_names)
        logger.info("Model training completed")
    except Exception as exc:
        error_msg = f"Model training failed: {exc}"
        logger.error(error_msg)
        return False, error_msg, statistics.to_dict()

    # Evaluate on test set
    test_set = data_loader.get_test_set()
    if test_set is not None:
        X_test, y_test = test_set
        if len(X_test) > 0:
            try:
                y_pred_ml = model.predict(X_test)
                baseline = BaselinePredictor()
                y_pred_baseline = baseline.predict(X_test)

                metrics = evaluate_predictions(y_test, y_pred_ml, y_pred_baseline)
                logger.info("Evaluation metrics: %s", metrics.to_dict())
            except Exception as exc:
                logger.warning("Evaluation failed: %s", exc)
                metrics = None
        else:
            logger.warning("Test set is empty, skipping evaluation")
            metrics = None
    else:
        logger.warning("No test set available, skipping evaluation")
        metrics = None

    # Save model
    try:
        joblib.dump(model, PredictionConfig.MODEL_PATH)
        logger.info("Model saved to %s", PredictionConfig.MODEL_PATH)
    except Exception as exc:
        error_msg = f"Failed to save model: {exc}"
        logger.error(error_msg)
        return False, error_msg, statistics.to_dict()

    # Save feature metadata
    try:
        metadata = FeatureMetadata(
            feature_names=feature_names,
            feature_version="1.0",
            target_definition="congestion_score_0_100",
            prediction_horizon=horizon_seconds,
            model_name="RandomForestRegressor",
            model_parameters=model.get_model_info(),
            training_timestamp=datetime.now(timezone.utc).isoformat(),
            dataset_size=len(X),
            random_seed=random_state,
        )

        with open(PredictionConfig.FEATURE_METADATA_PATH, "w") as f:
            json.dump(metadata.to_dict(), f, indent=2)

        logger.info("Feature metadata saved to %s", PredictionConfig.FEATURE_METADATA_PATH)
    except Exception as exc:
        error_msg = f"Failed to save feature metadata: {exc}"
        logger.error(error_msg)
        return False, error_msg, statistics.to_dict()

    # Prepare result
    result = {
        "dataset_statistics": statistics.to_dict(),
        "model_info": model.get_model_info(),
        "evaluation_metrics": metrics.to_dict() if metrics else None,
        "prediction_horizon": horizon_seconds,
        "random_state": random_state,
    }

    success_msg = f"Model training completed successfully. Dataset: {len(X)} samples."
    logger.info(success_msg)

    return True, success_msg, result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    success, message, result = train_model()

    if success:
        print(f"[SUCCESS] {message}")
        print(f"  Training samples: {result['dataset_statistics']['num_training_samples']}")
        if result['evaluation_metrics']:
            print(f"  Test MAE: {result['evaluation_metrics']['ml_model']['mae']:.4f}")
            print(f"  Test RMSE: {result['evaluation_metrics']['ml_model']['rmse']:.4f}")
            print(f"  Test R2: {result['evaluation_metrics']['ml_model']['r2']:.4f}")
    else:
        print(f"[FAILED] {message}")
