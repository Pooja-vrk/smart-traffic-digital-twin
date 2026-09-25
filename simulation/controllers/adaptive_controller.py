"""Rule-Based Adaptive traffic signal controller.

Dynamically actuates signal timings based on real-time queue pressure
differential between conflicting corridors (North-South vs East-West).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from simulation.config import AdaptiveConfig
from simulation.controllers.base_controller import BaseController, SignalSafetyManager
from simulation.state import TrafficState

logger = logging.getLogger(__name__)


class AdaptiveController(BaseController):
    """Rule-Based Actuated signal controller responding dynamically to queue pressure."""

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

        self._active_green = SignalSafetyManager.NS_GREEN
        self._last_ns_pressure = 0
        self._last_ew_pressure = 0

    def reset(self) -> None:
        """Reset adaptive controller state."""
        super().reset()
        self._active_green = SignalSafetyManager.NS_GREEN
        self._last_ns_pressure = 0
        self._last_ew_pressure = 0

    def decide_target_phase(self, state: TrafficState) -> int:
        """Evaluate real-time corridor pressure and decide optimal target green phase.

        Args:
            state: Instantaneous traffic state extracted from TraCI.

        Returns:
            int: Desired green phase (0 for NS_GREEN, 2 for EW_GREEN).
        """
        # Corridor queue pressures
        ns_pressure = state.north.queue_length + state.south.queue_length
        ew_pressure = state.east.queue_length + state.west.queue_length

        self._last_ns_pressure = ns_pressure
        self._last_ew_pressure = ew_pressure

        current_green = self.safety_manager.current_phase
        if current_green not in SignalSafetyManager.GREEN_PHASES:
            # During yellow transition, maintain target phase
            return self.safety_manager.target_green_phase

        elapsed_green = self.safety_manager.time_in_current_phase
        threshold = self.config.pressure_difference_threshold

        if current_green == SignalSafetyManager.NS_GREEN:
            # Check if EW demand significantly exceeds NS demand
            ew_demand_dominant = (ew_pressure - ns_pressure) >= threshold
            max_green_reached = elapsed_green >= self.config.max_green_seconds

            if (ew_demand_dominant or max_green_reached) and (elapsed_green >= self.config.min_green_seconds):
                self._active_green = SignalSafetyManager.EW_GREEN
                logger.debug(
                    "Adaptive switch requested: NS -> EW (NS_Q=%d, EW_Q=%d, Elapsed=%.1fs)",
                    ns_pressure, ew_pressure, elapsed_green
                )
            else:
                self._active_green = SignalSafetyManager.NS_GREEN

        elif current_green == SignalSafetyManager.EW_GREEN:
            # Check if NS demand significantly exceeds EW demand
            ns_demand_dominant = (ns_pressure - ew_pressure) >= threshold
            max_green_reached = elapsed_green >= self.config.max_green_seconds

            if (ns_demand_dominant or max_green_reached) and (elapsed_green >= self.config.min_green_seconds):
                self._active_green = SignalSafetyManager.NS_GREEN
                logger.debug(
                    "Adaptive switch requested: EW -> NS (NS_Q=%d, EW_Q=%d, Elapsed=%.1fs)",
                    ns_pressure, ew_pressure, elapsed_green
                )
            else:
                self._active_green = SignalSafetyManager.EW_GREEN

        return self._active_green

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats["config"] = self.config.to_dict()
        stats["last_ns_pressure"] = self._last_ns_pressure
        stats["last_ew_pressure"] = self._last_ew_pressure
        return stats
