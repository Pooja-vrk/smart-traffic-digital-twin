"""Congestion prediction endpoints."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException

from backend.schemas.prediction import (
    PredictionCurrentResponse,
    PredictionHistoryResponse,
    PredictionPredictRequest,
    PredictionPredictResponse,
    PredictionStatusResponse,
    PredictionTrainRequest,
    PredictionTrainResponse,
)
from backend.services.simulation_manager import sim_manager
from prediction.config import PredictionConfig
from prediction.predictor import predictor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prediction", tags=["Prediction"])


@router.get(
    "/status",
    response_model=PredictionStatusResponse,
    summary="Prediction Model Status",
)
async def get_prediction_status() -> PredictionStatusResponse:
    """Retrieve the current status of the congestion prediction model."""
    status = predictor.get_status()
    return PredictionStatusResponse(**status)


@router.post(
    "/train",
    response_model=PredictionTrainResponse,
    summary="Train Prediction Model",
)
async def train_prediction_model(request: PredictionTrainRequest) -> PredictionTrainResponse:
    """
    Train or retrain the congestion prediction model using historical MongoDB data.

    This process loads historical traffic snapshots, builds training pairs,
    trains a RandomForestRegressor, and saves the model for future predictions.
    """
    try:
        from prediction.train import train_model

        horizon = request.horizon_seconds
        random_state = request.random_state

        success, message, result = train_model(
            horizon_seconds=horizon,
            random_state=random_state,
        )

        # Reload model if training succeeded
        if success:
            predictor.load_model()

        return PredictionTrainResponse(
            success=success,
            message=message,
            dataset_statistics=result.get("dataset_statistics"),
            model_info=result.get("model_info"),
            evaluation_metrics=result.get("evaluation_metrics"),
            prediction_horizon=result.get("prediction_horizon"),
            random_state=result.get("random_state"),
        )

    except Exception as exc:
        logger.error("Training failed: %s", exc)
        return PredictionTrainResponse(
            success=False,
            message=f"Training failed: {str(exc)}",
        )


@router.get(
    "/current",
    response_model=PredictionCurrentResponse,
    summary="Current Congestion Prediction",
)
async def get_current_prediction() -> PredictionCurrentResponse:
    """
    Predict future congestion using the latest available traffic state.

    Uses the most recent traffic snapshot from the active or last simulation.
    """
    # Try to load model if not already loaded
    if not predictor.is_loaded:
        predictor.load_model()

    # Get latest traffic snapshot
    latest_snapshot = sim_manager.get_current_traffic()
    if latest_snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No current traffic state available. Start a simulation first."
        )

    # Convert to dict
    snapshot_dict = latest_snapshot.model_dump()

    # Make prediction
    try:
        prediction = predictor.predict(snapshot_dict, historical_snapshots=None)
        return PredictionCurrentResponse(**prediction)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Prediction service unavailable: {str(exc)}"
        )
    except Exception as exc:
        logger.error("Prediction failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(exc)}"
        )


@router.post(
    "/predict",
    response_model=PredictionPredictResponse,
    summary="Predict Congestion from Features",
)
async def predict_congestion(request: PredictionPredictRequest) -> PredictionPredictResponse:
    """
    Predict future congestion from provided traffic feature data.

    This endpoint allows external systems to submit traffic features
    and receive congestion predictions.
    """
    # Try to load model if not already loaded
    if not predictor.is_loaded:
        predictor.load_model()

    try:
        prediction = predictor.predict(
            request.snapshot,
            historical_snapshots=request.historical_snapshots,
        )
        return PredictionPredictResponse(**prediction)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Prediction service unavailable: {str(exc)}"
        )
    except Exception as exc:
        logger.error("Prediction failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(exc)}"
        )


@router.get(
    "/history",
    response_model=PredictionHistoryResponse,
    summary="Prediction History",
)
async def get_prediction_history(limit: int = 100) -> PredictionHistoryResponse:
    """
    Retrieve recent prediction results from MongoDB.

    Returns persisted prediction records if available.
    """
    # TODO: Implement once congestion_predictions collection is added
    return PredictionHistoryResponse(
        predictions=[],
        count=0,
    )
