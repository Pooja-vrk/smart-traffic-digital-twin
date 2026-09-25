"""Congestion score calculation and classification."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from prediction.config import PredictionConfig

logger = logging.getLogger(__name__)


def build_congestion_score(snapshot: Dict) -> float:
    """
    Calculate an explainable congestion score from 0-100 based on traffic snapshot.

    Uses queue-related information as the primary signal, with weights configurable
    in PredictionConfig.CONGESTION_WEIGHTS.

    Args:
        snapshot: Traffic snapshot dictionary with fields:
            - queues: {north, south, east, west, total}
            - waiting: {average_seconds}
            - speed: {average_mps}

    Returns:
        Congestion score from 0-100, where higher values indicate worse congestion.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    weights = PredictionConfig.CONGESTION_WEIGHTS

    # Extract queue information
    queues = snapshot.get("queues", {})
    total_queue = queues.get("total", 0)
    north_queue = queues.get("north", 0)
    south_queue = queues.get("south", 0)
    east_queue = queues.get("east", 0)
    west_queue = queues.get("west", 0)

    # Calculate average queue
    avg_queue = (north_queue + south_queue + east_queue + west_queue) / 4.0

    # Extract waiting time
    waiting = snapshot.get("waiting", {})
    avg_waiting_time = waiting.get("average_seconds", 0.0)

    # Extract speed
    speed = snapshot.get("speed", {})
    avg_speed = speed.get("average_mps", 0.0)

    # Validate inputs
    if total_queue < 0 or avg_queue < 0 or avg_waiting_time < 0 or avg_speed < 0:
        raise ValueError(
            f"Invalid traffic metrics: total_queue={total_queue}, "
            f"avg_queue={avg_queue}, avg_waiting_time={avg_waiting_time}, "
            f"avg_speed={avg_speed}"
        )

    # Normalize components to 0-100 range
    # Queue: assume max reasonable queue is 30 vehicles
    normalized_total_queue = min(total_queue / 30.0 * 100, 100)
    normalized_avg_queue = min(avg_queue / 30.0 * 100, 100)

    # Waiting time: assume max reasonable wait is 120 seconds
    normalized_waiting = min(avg_waiting_time / 120.0 * 100, 100)

    # Speed inverse: lower speed = higher congestion
    # Assume free-flow speed is ~15 m/s, minimum is 0
    if avg_speed > 0:
        speed_inverse = (1.0 - min(avg_speed / 15.0, 1.0)) * 100
    else:
        speed_inverse = 100

    # Calculate weighted score
    score = (
        weights["total_queue"] * normalized_total_queue
        + weights["average_queue"] * normalized_avg_queue
        + weights["waiting_time"] * normalized_waiting
        + weights["speed_inverse"] * speed_inverse
    )

    # Clamp to [0, 100]
    score = max(0.0, min(100.0, score))

    logger.debug(
        "Congestion score: %.2f (queue=%.1f, avg_queue=%.1f, wait=%.1f, speed=%.1f)",
        score, total_queue, avg_queue, avg_waiting_time, avg_speed
    )

    return score


def classify_congestion(score: float) -> str:
    """
    Classify congestion score into discrete levels.

    Args:
        score: Congestion score from 0-100.

    Returns:
        Congestion level: "FREE_FLOW", "LOW", "MODERATE", "HIGH", or "SEVERE".

    Raises:
        ValueError: If score is outside [0, 100].
    """
    if not 0 <= score <= 100:
        raise ValueError(f"Congestion score must be in [0, 100], got {score}")

    thresholds = PredictionConfig.CONGESTION_THRESHOLDS

    if score <= thresholds["FREE_FLOW"]:
        return "FREE_FLOW"
    elif score <= thresholds["LOW"]:
        return "LOW"
    elif score <= thresholds["MODERATE"]:
        return "MODERATE"
    elif score <= thresholds["HIGH"]:
        return "HIGH"
    else:
        return "SEVERE"
