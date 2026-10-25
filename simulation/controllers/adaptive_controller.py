"""Rule-Based Adaptive traffic signal controller.

Dynamically actuates signal timings based on real-time queue pressure
differential between conflicting corridors (North-South vs East-West).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from simulation.config import AdaptiveConfig
from simulation.controllers.base_controller import BaseController, SignalSafetyManager
from simulation.coordination.adaptive_optimizer import AdaptiveSignalOptimizer
from simulation.state import TrafficState

logger = logging.getLogger(__name__)


class AdaptiveController(BaseController):
    """Rule-Based Actuated signal controller responding dynamically to multi-metric corridor pressure."""

    def __init__(
        self,
        config: Optional[AdaptiveConfig] = None,
        tls_id: str = "center",
    ) -> None:
        self.config = config or AdaptiveConfig()

        safety_mgr = SignalSafetyManager(
            min_green_seconds=self.config.min_green_seconds,
            yellow_seconds=self.config.yellow_seconds,
            max_green_seconds=self.config.max_green_seconds,
        )

        super().__init__(name="Rule-Based Adaptive", tls_id=tls_id, safety_manager=safety_mgr)

        self.optimizer = AdaptiveSignalOptimizer(
            min_green_seconds=self.config.min_green_seconds,
            max_green_seconds=self.config.max_green_seconds,
        )

        self._active_green = SignalSafetyManager.NS_GREEN
        self._last_ns_pressure = 0
        self._last_ew_pressure = 0
        self._last_decision_reason: Optional[str] = None

    def reset(self) -> None:
        """Reset adaptive controller state."""
        super().reset()
        self._active_green = SignalSafetyManager.NS_GREEN
        self._last_ns_pressure = 0
        self._last_ew_pressure = 0
        self._last_decision_reason = None

    def decide_target_phase(self, state: TrafficState) -> int:
        """Evaluate real-time corridor pressure and decide optimal target green phase.

        Evaluates queue length, waiting delay, and vehicle density via AdaptiveSignalOptimizer.

        Args:
            state: Instantaneous traffic state extracted from TraCI.

        Returns:
            int: Desired green phase (0 for NS_GREEN, 2 for EW_GREEN).
        """
        ns_metrics, ew_metrics = self.optimizer.evaluate_corridor_demand(state)

        # Retain backward-compatible integer pressures
        self._last_ns_pressure = int(ns_metrics.composite_pressure)
        self._last_ew_pressure = int(ew_metrics.composite_pressure)

        current_green = self.safety_manager.current_phase
        if current_green not in SignalSafetyManager.GREEN_PHASES:
            # During yellow transition, maintain target phase
            return self.safety_manager.target_green_phase

        elapsed_green = self.safety_manager.time_in_current_phase
        threshold = float(self.config.pressure_difference_threshold)

        should_switch, reason = self.optimizer.should_switch_phase(
            current_phase=current_green,
            elapsed_green=elapsed_green,
            ns_metrics=ns_metrics,
            ew_metrics=ew_metrics,
            pressure_difference_threshold=threshold,
        )
        self._last_decision_reason = reason

        if should_switch:
            if current_green == SignalSafetyManager.NS_GREEN:
                self._active_green = SignalSafetyManager.EW_GREEN
                logger.debug("Adaptive switch requested: NS -> EW (%s)", reason)
            else:
                self._active_green = SignalSafetyManager.NS_GREEN
                logger.debug("Adaptive switch requested: EW -> NS (%s)", reason)
        else:
            self._active_green = current_green

        return self._active_green

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats["config"] = self.config.to_dict()
        stats["last_ns_pressure"] = self._last_ns_pressure
        stats["last_ew_pressure"] = self._last_ew_pressure
        stats["last_decision_reason"] = self._last_decision_reason
        return stats
