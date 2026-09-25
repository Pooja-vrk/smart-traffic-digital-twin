"""Fixed-Time traffic signal controller.

Implements a deterministic, time-split cyclical signal timing plan
serving as the baseline comparison benchmark.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from simulation.config import FixedTimeConfig
from simulation.controllers.base_controller import BaseController, SignalSafetyManager
from simulation.state import TrafficState


class FixedTimeController(BaseController):
    """Deterministic Fixed-Time signal controller cycling through preset green/yellow intervals."""

    def __init__(
        self,
        config: Optional[FixedTimeConfig] = None,
        tls_id: str = "center",
    ) -> None:
        self.config = config or FixedTimeConfig()

        safety_mgr = SignalSafetyManager(
            min_green_seconds=self.config.ns_green_seconds,
            yellow_seconds=self.config.ns_yellow_seconds,
            max_green_seconds=max(self.config.ns_green_seconds, self.config.ew_green_seconds),
        )

        super().__init__(name="Fixed-Time", tls_id=tls_id, safety_manager=safety_mgr)

        self._active_green = SignalSafetyManager.NS_GREEN
        self._elapsed_in_green = 0.0

    def reset(self) -> None:
        """Reset fixed-time controller cycle."""
        super().reset()
        self._active_green = SignalSafetyManager.NS_GREEN
        self._elapsed_in_green = 0.0

    def decide_target_phase(self, state: TrafficState) -> int:
        """Advance deterministic timer and return target green phase."""
        target_duration = (
            self.config.ns_green_seconds
            if self._active_green == SignalSafetyManager.NS_GREEN
            else self.config.ew_green_seconds
        )

        self._elapsed_in_green += 1.0

        if self._elapsed_in_green >= target_duration:
            # Switch target green corridor
            self._active_green = (
                SignalSafetyManager.EW_GREEN
                if self._active_green == SignalSafetyManager.NS_GREEN
                else SignalSafetyManager.NS_GREEN
            )
            self._elapsed_in_green = 0.0

        return self._active_green

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats["config"] = self.config.to_dict()
        stats["active_green"] = self._active_green
        stats["elapsed_in_green"] = round(self._elapsed_in_green, 1)
        return stats
