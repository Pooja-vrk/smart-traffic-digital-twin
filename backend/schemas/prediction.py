"""Pydantic schemas for congestion prediction API."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class PredictionStatusResponse(BaseModel):
    """Response for prediction model status."""
    model_config = ConfigDict(protected_namespaces=())

    model_available: bool = Field(default=False, description="Whether a trained model is loaded")
    model_name: Optional[str] = Field(default=None, description="Name of the loaded model")
    prediction_horizon: Optional[float] = Field(default=None, description="Prediction horizon in seconds")
    feature_count: int = Field(default=0, description="Number of features used by the model")
    last_training_time: Optional[str] = Field(default=None, description="Timestamp of last model training")
    feature_version: Optional[str] = Field(default=None, description="Feature engineering version")


class PredictionTrainRequest(BaseModel):
    """Request to train prediction model."""
    horizon_seconds: Optional[float] = Field(default=None, description="Prediction horizon in seconds")
    random_state: Optional[int] = Field(default=None, description="Random seed for reproducibility")


class PredictionTrainResponse(BaseModel):
    """Response from training request."""
    model_config = ConfigDict(protected_namespaces=())

    success: bool = Field(default=False, description="Whether training succeeded")
    message: str = Field(default="", description="Human-readable status message")
    dataset_statistics: Optional[Dict[str, Any]] = Field(default=None, description="Statistics about training dataset")
    model_info: Optional[Dict[str, Any]] = Field(default=None, description="Model metadata")
    evaluation_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Evaluation metrics if test set available")
    prediction_horizon: Optional[float] = Field(default=None, description="Prediction horizon used")
    random_state: Optional[int] = Field(default=None, description="Random seed used")


class PredictionCurrentResponse(BaseModel):
    """Response for current congestion prediction."""
    model_config = ConfigDict(protected_namespaces=())

    predicted_congestion_score: float = Field(default=0.0, description="Predicted congestion score (0-100)")
    congestion_level: str = Field(default="UNKNOWN", description="Congestion level classification")
    prediction_horizon: float = Field(default=30.0, description="Prediction horizon in seconds")
    model_name: str = Field(default="unknown", description="Model name")
    model_available: bool = Field(default=False, description="Whether model is available")
    baseline_score: float = Field(default=0.0, description="Baseline prediction (current congestion)")
    current_congestion_score: float = Field(default=0.0, description="Current congestion score")


class PredictionPredictRequest(BaseModel):
    """Request for prediction with custom features."""
    snapshot: Dict[str, Any] = Field(default={}, description="Traffic snapshot data")
    historical_snapshots: Optional[list[Dict[str, Any]]] = Field(default=None, description="Historical snapshots for lag features")


class PredictionPredictResponse(BaseModel):
    """Response from prediction request."""
    model_config = ConfigDict(protected_namespaces=())

    predicted_congestion_score: float = Field(default=0.0, description="Predicted congestion score (0-100)")
    congestion_level: str = Field(default="UNKNOWN", description="Congestion level classification")
    prediction_horizon: float = Field(default=30.0, description="Prediction horizon in seconds")
    model_name: str = Field(default="unknown", description="Model name")
    model_available: bool = Field(default=False, description="Whether model is available")
    baseline_score: float = Field(default=0.0, description="Baseline prediction")
    current_congestion_score: float = Field(default=0.0, description="Current congestion score")


class PredictionHistoryResponse(BaseModel):
    """Response for prediction history."""
    predictions: list[Dict[str, Any]] = Field(default=[], description="List of prediction records")
    count: int = Field(default=0, description="Number of predictions returned")
