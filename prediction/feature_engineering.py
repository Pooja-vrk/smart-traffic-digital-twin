"""Feature engineering for congestion prediction."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

from prediction.config import PredictionConfig
from prediction.congestion import build_congestion_score

logger = logging.getLogger(__name__)


def extract_features(
    snapshot: Dict,
    historical_snapshots: Optional[List[Dict]] = None,
) -> Dict[str, float]:
    """
    Extract features from a traffic snapshot for prediction.

    Uses only information available at prediction time (no future data).
    Includes temporal lag features when historical snapshots are provided.

    Args:
        snapshot: Current traffic snapshot.
        historical_snapshots: List of previous snapshots in chronological order
                              (oldest first, most recent last).

    Returns:
        Dictionary of feature names to values.
    """
    features: Dict[str, float] = {}

    # Extract basic queue information
    queues = snapshot.get("queues", {})
    features["north_queue"] = float(queues.get("north", 0))
    features["south_queue"] = float(queues.get("south", 0))
    features["east_queue"] = float(queues.get("east", 0))
    features["west_queue"] = float(queues.get("west", 0))
    features["total_queue"] = float(queues.get("total", 0))

    # Queue statistics
    features["max_queue"] = max(
        features["north_queue"],
        features["south_queue"],
        features["east_queue"],
        features["west_queue"],
    )
    features["average_queue"] = (
        features["north_queue"] + features["south_queue"] +
        features["east_queue"] + features["west_queue"]
    ) / 4.0

    # Queue imbalance (deviation from equal distribution)
    if features["total_queue"] > 0:
        expected_per_approach = features["total_queue"] / 4.0
        features["queue_imbalance"] = (
            abs(features["north_queue"] - expected_per_approach) +
            abs(features["south_queue"] - expected_per_approach) +
            abs(features["east_queue"] - expected_per_approach) +
            abs(features["west_queue"] - expected_per_approach)
        ) / expected_per_approach
    else:
        features["queue_imbalance"] = 0.0

    # Waiting time
    waiting = snapshot.get("waiting", {})
    features["average_waiting_time"] = float(waiting.get("average_seconds", 0.0))

    # Speed
    speed = snapshot.get("speed", {})
    features["average_speed"] = float(speed.get("average_mps", 0.0))

    # Signal information
    signal = snapshot.get("signal", {})
    features["phase_index"] = float(signal.get("phase_index", 0))
    features["elapsed_green"] = float(signal.get("elapsed_seconds", 0.0))

    # Controller type (one-hot encoding)
    controller = snapshot.get("controller", "fixed").lower()
    features["controller_fixed"] = 1.0 if controller == "fixed" else 0.0
    features["controller_adaptive"] = 1.0 if controller == "adaptive" else 0.0
    features["controller_dqn"] = 1.0 if controller == "dqn" else 0.0

    # Simulation time
    features["simulation_time"] = float(snapshot.get("simulation_time", 0.0))

    # Current congestion score
    try:
        features["current_congestion_score"] = build_congestion_score(snapshot)
    except Exception as exc:
        logger.warning("Failed to calculate congestion score for feature extraction: %s", exc)
        features["current_congestion_score"] = 0.0

    # Temporal lag features
    if historical_snapshots:
        features.update(_extract_lag_features(historical_snapshots))
    else:
        # Initialize lag features to 0 when no historical data available
        for lag in PredictionConfig.LAG_STEPS:
            features[f"queue_total_lag_{lag}"] = 0.0
        for delta in PredictionConfig.DELTA_STEPS:
            features[f"queue_total_delta_{delta}"] = 0.0
        for lag in PredictionConfig.LAG_STEPS:
            features[f"speed_lag_{lag}"] = 0.0
        features["speed_delta_1"] = 0.0

    return features


def _extract_lag_features(historical_snapshots: List[Dict]) -> Dict[str, float]:
    """
    Extract temporal lag and delta features from historical snapshots.

    Args:
        historical_snapshots: List of previous snapshots (oldest first).

    Returns:
        Dictionary of lag feature names to values.
    """
    lag_features: Dict[str, float] = {}

    if not historical_snapshots:
        return lag_features

    # Ensure we have the most recent snapshots at the end
    # Sort by simulation_time to be safe
    sorted_snapshots = sorted(historical_snapshots, key=lambda s: s.get("simulation_time", 0))

    # Extract total queue history
    queue_history = [
        float(s.get("queues", {}).get("total", 0))
        for s in sorted_snapshots
    ]

    speed_history = [
        float(s.get("speed", {}).get("average_mps", 0.0))
        for s in sorted_snapshots
    ]

    # Lag features for queue
    for lag in PredictionConfig.LAG_STEPS:
        if len(queue_history) >= lag:
            lag_features[f"queue_total_lag_{lag}"] = queue_history[-lag]
        else:
            lag_features[f"queue_total_lag_{lag}"] = 0.0

    # Delta features for queue
    for delta in PredictionConfig.DELTA_STEPS:
        if len(queue_history) >= delta:
            lag_features[f"queue_total_delta_{delta}"] = queue_history[-1] - queue_history[-delta]
        else:
            lag_features[f"queue_total_delta_{delta}"] = 0.0

    # Lag features for speed
    for lag in PredictionConfig.LAG_STEPS:
        if len(speed_history) >= lag:
            lag_features[f"speed_lag_{lag}"] = speed_history[-lag]
        else:
            lag_features[f"speed_lag_{lag}"] = 0.0

    # Delta features for speed
    if len(speed_history) >= 1:
        lag_features["speed_delta_1"] = speed_history[-1] - speed_history[-2] if len(speed_history) >= 2 else 0.0
    else:
        lag_features["speed_delta_1"] = 0.0

    return lag_features


def get_feature_names() -> List[str]:
    """
    Return the canonical list of feature names expected by the model.

    This ensures consistent feature ordering between training and inference.

    Returns:
        List of feature names in the expected order.
    """
    # Base features
    base_features = [
        "north_queue",
        "south_queue",
        "east_queue",
        "west_queue",
        "total_queue",
        "max_queue",
        "average_queue",
        "queue_imbalance",
        "average_waiting_time",
        "average_speed",
        "phase_index",
        "elapsed_green",
        "controller_fixed",
        "controller_adaptive",
        "controller_dqn",
        "simulation_time",
        "current_congestion_score",
    ]

    # Lag features
    lag_features = []
    for lag in PredictionConfig.LAG_STEPS:
        lag_features.append(f"queue_total_lag_{lag}")
    for delta in PredictionConfig.DELTA_STEPS:
        lag_features.append(f"queue_total_delta_{delta}")
    for lag in PredictionConfig.LAG_STEPS:
        lag_features.append(f"speed_lag_{lag}")
    lag_features.append("speed_delta_1")

    return base_features + lag_features


def prepare_feature_vector(features: Dict[str, float]) -> np.ndarray:
    """
    Convert feature dictionary to numpy array in canonical order.

    Args:
        features: Dictionary of feature names to values.

    Returns:
        Numpy array of features in canonical order.

    Raises:
        ValueError: If required features are missing.
    """
    feature_names = get_feature_names()
    feature_vector = []

    for name in feature_names:
        if name not in features:
            raise ValueError(f"Missing required feature: {name}")
        feature_vector.append(features[name])

    return np.array(feature_vector, dtype=np.float32)


def validate_no_future_leakage(features: Dict[str, float], snapshot_time: float) -> bool:
    """
    Validate that features do not contain future information.

    This is a safety check to prevent data leakage.

    Args:
        features: Extracted features.
        snapshot_time: Current simulation time.

    Returns:
        True if no future leakage detected, False otherwise.
    """
    # Check that simulation_time in features matches snapshot_time
    if "simulation_time" in features:
        if abs(features["simulation_time"] - snapshot_time) > 0.1:
            logger.warning(
                "Feature simulation_time (%.2f) differs from snapshot_time (%.2f)",
                features["simulation_time"], snapshot_time
            )
            return False

    # Lag features should not be from the future
    # This is implicitly handled by construction, but we check for negative deltas
    for key, value in features.items():
        if "delta" in key and value < 0:
            # Negative delta is acceptable (decreasing trend)
            pass
        elif "lag" in key and value < 0:
            logger.warning("Negative lag value detected: %s = %.2f", key, value)
            return False

    return True
