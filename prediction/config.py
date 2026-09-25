"""Configuration for congestion prediction module."""

from __future__ import annotations

from pathlib import Path
from typing import Dict


class PredictionConfig:
    """Configuration settings for congestion prediction model."""

    # Prediction horizon (seconds into future)
    PREDICTION_HORIZON_SECONDS: float = 30.0

    # Tolerance for finding future snapshot (seconds)
    FUTURE_SNAPSHOT_TOLERANCE_SECONDS: float = 5.0

    # Congestion score weights (must sum to 1.0)
    CONGESTION_WEIGHTS: Dict[str, float] = {
        "total_queue": 0.6,  # Primary signal: total queue length
        "average_queue": 0.2,  # Average queue across approaches
        "waiting_time": 0.15,  # Average waiting time
        "speed_inverse": 0.05,  # Inverse of average speed (lower speed = higher congestion)
    }

    # Congestion classification thresholds
    CONGESTION_THRESHOLDS: Dict[str, int] = {
        "FREE_FLOW": 20,
        "LOW": 40,
        "MODERATE": 60,
        "HIGH": 80,
        "SEVERE": 100,
    }

    # Data sufficiency thresholds
    MIN_SIMULATION_RUNS: int = 3
    MIN_SNAPSHOTS: int = 300
    MIN_TRAINING_SAMPLES: int = 100

    # Train/validation/test split ratios
    TRAIN_RATIO: float = 0.70
    VALIDATION_RATIO: float = 0.15
    TEST_RATIO: float = 0.15

    # Random seed for reproducibility
    RANDOM_STATE: int = 42

    # Model parameters
    MODEL_N_ESTIMATORS: int = 200
    MODEL_MAX_DEPTH: int = 12
    MODEL_N_JOBS: int = -1

    # Model artifact paths
    MODELS_DIR: Path = Path("prediction/models")
    MODEL_PATH: Path = MODELS_DIR / "congestion_model.joblib"
    FEATURE_METADATA_PATH: Path = MODELS_DIR / "feature_metadata.json"

    # Experiment results path
    EXPERIMENTS_DIR: Path = Path("data/experiments/prediction")
    EVALUATION_RESULTS_PATH: Path = EXPERIMENTS_DIR / "prediction_evaluation.json"

    # Feature lag configuration
    LAG_STEPS: list[int] = [1, 2, 3]  # Number of steps to look back
    DELTA_STEPS: list[int] = [1, 3]  # Steps for calculating deltas

    @classmethod
    def get_congestion_thresholds(cls) -> list[tuple[str, int, int]]:
        """Return congestion level ranges as (level, min, max)."""
        thresholds = cls.CONGESTION_THRESHOLDS
        return [
            ("FREE_FLOW", 0, thresholds["FREE_FLOW"]),
            ("LOW", thresholds["FREE_FLOW"] + 1, thresholds["LOW"]),
            ("MODERATE", thresholds["LOW"] + 1, thresholds["MODERATE"]),
            ("HIGH", thresholds["MODERATE"] + 1, thresholds["HIGH"]),
            ("SEVERE", thresholds["HIGH"] + 1, thresholds["SEVERE"]),
        ]

    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure model and experiment directories exist."""
        cls.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        cls.EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
