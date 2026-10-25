"""Live forecast tracking and time-aligned empirical evaluation for traffic predictions."""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingForecast:
    """A forecast issued at simulation timestamp t targeting (t + horizon)."""
    simulation_id: str
    issue_step: int
    issue_time: float
    target_time: float
    predicted_score: float
    baseline_score: float


class LiveForecastTracker:
    """
    Tracks pending forecasts and performs time-aligned evaluation against actual observations.

    Guarantees zero data leakage by recording model forecasts made at t and evaluating
    them only when simulation time advances to t + 30.0s (+/- match tolerance).
    Computes live cumulative MAE, RMSE, and baseline comparisons across all verified steps.
    """

    def __init__(
        self,
        horizon_seconds: float = 30.0,
        match_tolerance_seconds: float = 1.0,
    ):
        self.horizon_seconds = float(horizon_seconds)
        self.match_tolerance_seconds = float(match_tolerance_seconds)
        self._lock = threading.Lock()

        self.pending_forecasts: List[PendingForecast] = []
        self.current_simulation_id: Optional[str] = None

        # Cumulative verification statistics
        self.evaluated_samples: int = 0
        self.sum_model_abs_error: float = 0.0
        self.sum_model_sq_error: float = 0.0
        self.sum_baseline_abs_error: float = 0.0
        self.sum_baseline_sq_error: float = 0.0

        self.last_verified_actual: Optional[float] = None
        self.last_verified_predicted: Optional[float] = None
        self.last_verified_baseline: Optional[float] = None
        self.last_verified_time: Optional[float] = None

    def reset(self, simulation_id: Optional[str] = None) -> None:
        """Reset pending forecasts and accumulated accuracy metrics for a new run."""
        with self._lock:
            self.pending_forecasts.clear()
            self.current_simulation_id = simulation_id
            self.evaluated_samples = 0
            self.sum_model_abs_error = 0.0
            self.sum_model_sq_error = 0.0
            self.sum_baseline_abs_error = 0.0
            self.sum_baseline_sq_error = 0.0
            self.last_verified_actual = None
            self.last_verified_predicted = None
            self.last_verified_baseline = None
            self.last_verified_time = None
        logger.debug("LiveForecastTracker reset for simulation_id=%s", simulation_id)

    def record_forecast(
        self,
        simulation_id: str,
        step: int,
        simulation_time: float,
        predicted_score: float,
        baseline_score: float,
        horizon_seconds: Optional[float] = None,
    ) -> None:
        """Record a forecast issued at current simulation time targeting (time + horizon)."""
        h = float(horizon_seconds) if horizon_seconds is not None else self.horizon_seconds
        target_time = round(simulation_time + h, 2)

        with self._lock:
            if self.current_simulation_id is not None and simulation_id != self.current_simulation_id:
                # Simulation session changed; reset tracker for new run
                self.pending_forecasts.clear()
                self.current_simulation_id = simulation_id
                self.evaluated_samples = 0
                self.sum_model_abs_error = 0.0
                self.sum_model_sq_error = 0.0
                self.sum_baseline_abs_error = 0.0
                self.sum_baseline_sq_error = 0.0
                self.last_verified_actual = None
                self.last_verified_predicted = None
                self.last_verified_baseline = None
                self.last_verified_time = None
            elif self.current_simulation_id is None:
                self.current_simulation_id = simulation_id

            self.pending_forecasts.append(
                PendingForecast(
                    simulation_id=simulation_id,
                    issue_step=step,
                    issue_time=simulation_time,
                    target_time=target_time,
                    predicted_score=float(predicted_score),
                    baseline_score=float(baseline_score),
                )
            )

    def evaluate_step(
        self,
        simulation_id: str,
        simulation_time: float,
        actual_score: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Check if any pending forecasts match the current simulation_time.

        If a match is found within tolerance, evaluate prediction error against
        actual_score and update running accuracy metrics.
        """
        with self._lock:
            if not self.pending_forecasts:
                return None

            matched_forecast: Optional[PendingForecast] = None
            remaining: List[PendingForecast] = []

            for pf in self.pending_forecasts:
                # Check match within tolerance window
                if matched_forecast is None and abs(simulation_time - pf.target_time) <= self.match_tolerance_seconds:
                    matched_forecast = pf
                elif pf.target_time < (simulation_time - 5.0):
                    # Stale forecast that missed its window (e.g. jumped or interrupted), prune it
                    continue
                else:
                    remaining.append(pf)

            self.pending_forecasts = remaining

            if matched_forecast is not None:
                model_err = abs(matched_forecast.predicted_score - actual_score)
                model_sq_err = (matched_forecast.predicted_score - actual_score) ** 2
                baseline_err = abs(matched_forecast.baseline_score - actual_score)
                baseline_sq_err = (matched_forecast.baseline_score - actual_score) ** 2

                self.evaluated_samples += 1
                self.sum_model_abs_error += model_err
                self.sum_model_sq_error += model_sq_err
                self.sum_baseline_abs_error += baseline_err
                self.sum_baseline_sq_error += baseline_sq_err

                self.last_verified_actual = round(actual_score, 2)
                self.last_verified_predicted = round(matched_forecast.predicted_score, 2)
                self.last_verified_baseline = round(matched_forecast.baseline_score, 2)
                self.last_verified_time = simulation_time

                return {
                    "matched_issue_time": matched_forecast.issue_time,
                    "target_time": matched_forecast.target_time,
                    "predicted_score": matched_forecast.predicted_score,
                    "actual_score": actual_score,
                    "baseline_score": matched_forecast.baseline_score,
                    "model_abs_error": model_err,
                    "baseline_abs_error": baseline_err,
                }

            return None

    def get_metrics(self) -> Dict[str, Any]:
        """Compute consolidated live verification metrics."""
        with self._lock:
            if self.evaluated_samples == 0:
                return {
                    "evaluated_samples": 0,
                    "live_mae": None,
                    "live_rmse": None,
                    "baseline_mae": None,
                    "baseline_rmse": None,
                    "mae_improvement_pct": None,
                    "last_verified_actual": None,
                    "last_verified_predicted": None,
                }

            n = float(self.evaluated_samples)
            m_mae = self.sum_model_abs_error / n
            m_rmse = math.sqrt(self.sum_model_sq_error / n)
            b_mae = self.sum_baseline_abs_error / n
            b_rmse = math.sqrt(self.sum_baseline_sq_error / n)

            improvement = ((b_mae - m_mae) / b_mae * 100.0) if b_mae > 1e-6 else 0.0

            return {
                "evaluated_samples": self.evaluated_samples,
                "live_mae": round(m_mae, 3),
                "live_rmse": round(m_rmse, 3),
                "baseline_mae": round(b_mae, 3),
                "baseline_rmse": round(b_rmse, 3),
                "mae_improvement_pct": round(improvement, 1),
                "last_verified_actual": self.last_verified_actual,
                "last_verified_predicted": self.last_verified_predicted,
            }
