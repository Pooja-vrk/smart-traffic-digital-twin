"""Future target construction for congestion prediction."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from prediction.config import PredictionConfig
from prediction.congestion import build_congestion_score

logger = logging.getLogger(__name__)


def find_future_snapshot(
    snapshots: List[Dict],
    current_time: float,
    horizon_seconds: float,
    tolerance_seconds: float,
) -> Optional[Dict]:
    """
    Find the snapshot closest to the target future time.

    Args:
        snapshots: List of snapshots sorted by simulation_time.
        current_time: Current simulation time.
        horizon_seconds: Prediction horizon in seconds.
        tolerance_seconds: Maximum acceptable deviation from target time.

    Returns:
        The snapshot closest to target_time within tolerance, or None if not found.
    """
    target_time = current_time + horizon_seconds

    # Find the first snapshot at or after target_time
    for snapshot in snapshots:
        snapshot_time = snapshot.get("simulation_time", 0.0)
        time_diff = snapshot_time - target_time

        # If we've passed the target time, check if within tolerance
        if time_diff >= 0:
            if time_diff <= tolerance_seconds:
                return snapshot
            else:
                # Beyond tolerance, no valid snapshot
                return None

    # No snapshot found at or after target time
    return None


def build_future_target(
    current_snapshot: Dict,
    future_snapshot: Dict,
) -> float:
    """
    Build the target congestion score for prediction.

    The target is the congestion score at the future snapshot time.

    Args:
        current_snapshot: Current traffic snapshot (for reference).
        future_snapshot: Future traffic snapshot at horizon.

    Returns:
        Congestion score at the future time.

    Raises:
        ValueError: If future snapshot is invalid.
    """
    if not future_snapshot:
        raise ValueError("Future snapshot is required")

    try:
        target_score = build_congestion_score(future_snapshot)
        logger.debug(
            "Target congestion score: %.2f at time %.2f",
            target_score,
            future_snapshot.get("simulation_time", 0.0)
        )
        return target_score
    except Exception as exc:
        raise ValueError(f"Failed to build target from future snapshot: {exc}") from exc


def create_training_pair(
    current_snapshot: Dict,
    all_snapshots: List[Dict],
    horizon_seconds: float = None,
    tolerance_seconds: float = None,
) -> Optional[tuple[Dict, float]]:
    """
    Create a single training pair (features, target) from current snapshot.

    Args:
        current_snapshot: Current traffic snapshot.
        all_snapshots: All snapshots for this simulation run, sorted by simulation_time.
        horizon_seconds: Prediction horizon (uses config default if None).
        tolerance_seconds: Tolerance for finding future snapshot (uses config default if None).

    Returns:
        Tuple of (current_snapshot_dict, target_congestion_score) or None if no valid future snapshot.
    """
    if horizon_seconds is None:
        horizon_seconds = PredictionConfig.PREDICTION_HORIZON_SECONDS
    if tolerance_seconds is None:
        tolerance_seconds = PredictionConfig.FUTURE_SNAPSHOT_TOLERANCE_SECONDS

    current_time = current_snapshot.get("simulation_time", 0.0)

    # Find future snapshot
    future_snapshot = find_future_snapshot(
        all_snapshots,
        current_time,
        horizon_seconds,
        tolerance_seconds,
    )

    if future_snapshot is None:
        logger.debug(
            "No valid future snapshot found for current_time=%.2f, horizon=%.2f",
            current_time, horizon_seconds
        )
        return None

    # Build target
    try:
        target_score = build_future_target(current_snapshot, future_snapshot)
        return current_snapshot, target_score
    except ValueError as exc:
        logger.warning("Failed to build target: %s", exc)
        return None


def create_training_pairs_for_simulation(
    snapshots: List[Dict],
    horizon_seconds: float = None,
    tolerance_seconds: float = None,
) -> List[tuple[Dict, float]]:
    """
    Create all valid training pairs for a single simulation run.

    Args:
        snapshots: All snapshots for a simulation run, sorted by simulation_time.
        horizon_seconds: Prediction horizon (uses config default if None).
        tolerance_seconds: Tolerance for finding future snapshot (uses config default if None).

    Returns:
        List of (current_snapshot_dict, target_congestion_score) tuples.
    """
    if not snapshots:
        return []

    # Ensure snapshots are sorted by simulation_time
    sorted_snapshots = sorted(snapshots, key=lambda s: s.get("simulation_time", 0.0))

    training_pairs = []
    for i, current_snapshot in enumerate(sorted_snapshots):
        # Use only snapshots after current as candidates for future
        future_candidates = sorted_snapshots[i+1:]

        if not future_candidates:
            continue

        pair = create_training_pair(
            current_snapshot,
            future_candidates,
            horizon_seconds,
            tolerance_seconds,
        )

        if pair is not None:
            training_pairs.append(pair)

    logger.info(
        "Created %d training pairs from %d snapshots (horizon=%.2fs)",
        len(training_pairs),
        len(sorted_snapshots),
        horizon_seconds or PredictionConfig.PREDICTION_HORIZON_SECONDS
    )

    return training_pairs
