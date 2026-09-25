"""Evaluation script for congestion prediction model."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib

from prediction.config import PredictionConfig
from prediction.data_loader import DataLoader
from prediction.metrics import evaluate_predictions
from prediction.model import BaselinePredictor

logger = logging.getLogger(__name__)


def evaluate_model(
    model_path: Path = None,
) -> dict:
    """
    Evaluate a trained congestion prediction model.

    Args:
        model_path: Path to trained model file (uses config default if None).

    Returns:
        Dictionary with evaluation results.
    """
    if model_path is None:
        model_path = PredictionConfig.MODEL_PATH

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    logger.info("Loading model from %s", model_path)

    # Connect to MongoDB before loading data
    from backend.database.connection import db_manager
    db_manager.connect()

    # Load model
    model = joblib.load(model_path)

    # Load test data
    try:
        data_loader = DataLoader()
        statistics = data_loader.load_historical_data(status="completed")
        logger.info("Loaded historical data for evaluation")
    except Exception as exc:
        raise RuntimeError(f"Failed to load historical data: {exc}")

    # Prepare dataset (to get test set)
    try:
        X, y, feature_names = data_loader.prepare_dataset()
        logger.info("Prepared dataset for evaluation")
    except Exception as exc:
        raise RuntimeError(f"Failed to prepare dataset: {exc}")

    # Get test set
    test_set = data_loader.get_test_set()
    if test_set is None:
        raise RuntimeError("No test set available for evaluation")

    X_test, y_test = test_set

    if len(X_test) == 0:
        raise RuntimeError("Test set is empty")

    logger.info("Evaluating on %d test samples", len(X_test))

    # Make predictions
    y_pred_ml = model.predict(X_test)
    baseline = BaselinePredictor()
    y_pred_baseline = baseline.predict(X_test)

    # Calculate metrics
    metrics = evaluate_predictions(y_test, y_pred_ml, y_pred_baseline)

    # Prepare results
    results = {
        "model_path": str(model_path),
        "test_samples": len(X_test),
        "evaluation_metrics": metrics.to_dict(),
        "model_info": model.get_model_info(),
        "dataset_statistics": statistics.to_dict(),
    }

    # Save results
    PredictionConfig.ensure_directories()
    with open(PredictionConfig.EVALUATION_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    logger.info("Evaluation results saved to %s", PredictionConfig.EVALUATION_RESULTS_PATH)

    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Evaluate congestion prediction model")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Path to trained model file"
    )

    args = parser.parse_args()

    try:
        results = evaluate_model(args.model_path)

        print("\n" + "="*60)
        print("CONGESTION PREDICTION MODEL EVALUATION")
        print("="*60)
        print(f"Model: {results['model_path']}")
        print(f"Test samples: {results['test_samples']}")
        print("\nML Model Metrics:")
        print(f"  MAE:  {results['evaluation_metrics']['ml_model']['mae']:.4f}")
        print(f"  RMSE: {results['evaluation_metrics']['ml_model']['rmse']:.4f}")
        print(f"  R2:   {results['evaluation_metrics']['ml_model']['r2']:.4f}")
        print("\nBaseline Metrics:")
        print(f"  MAE:  {results['evaluation_metrics']['baseline']['mae']:.4f}")
        print(f"  RMSE: {results['evaluation_metrics']['baseline']['rmse']:.4f}")
        print(f"  R2:   {results['evaluation_metrics']['baseline']['r2']:.4f}")
        print("\nImprovement over Baseline:")
        print(f"  MAE reduction:  {results['evaluation_metrics']['improvement_over_baseline']['mae_reduction_pct']:.2f}%")
        print(f"  RMSE reduction: {results['evaluation_metrics']['improvement_over_baseline']['rmse_reduction_pct']:.2f}%")
        print(f"  R2 improvement: {results['evaluation_metrics']['improvement_over_baseline']['r2_improvement']:.4f}")

        if 'classification_accuracy' in results['evaluation_metrics']:
            print(f"\nClassification Accuracy: {results['evaluation_metrics']['classification_accuracy']:.4f}")

        print("\n" + "="*60)

    except Exception as exc:
        logger.error("Evaluation failed: %s", exc)
        print(f"✗ Evaluation failed: {exc}")
