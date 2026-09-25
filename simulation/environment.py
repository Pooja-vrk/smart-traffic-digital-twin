"""Simulation environment coordinator for the 4-way intersection.

Provides a unified controller-agnostic simulation interface for running
and benchmarking Fixed-Time, Adaptive, or Reinforcement Learning controllers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from simulation.config import ExperimentConfig
from simulation.controllers.base_controller import BaseController
from simulation.metrics import AggregateMetrics, SimulationMetrics
from simulation.state import TrafficState
from simulation.traci_controller import TraCIController


class TrafficSimulationEnvironment:
    """High-level simulation coordinator for digital twin experiments."""

    def __init__(
        self,
        sumocfg_path: Optional[Path | str] = None,
        use_gui: bool = False,
        step_length: float = 1.0,
        seed: Optional[int] = 42,
        tls_id: str = "center",
        controller: Optional[BaseController] = None,
    ) -> None:
        self.controller = controller
        self.traci_controller = TraCIController(
            sumocfg_path=sumocfg_path,
            use_gui=use_gui,
            step_length=step_length,
            seed=seed,
            tls_id=tls_id,
        )

    def set_controller(self, controller: BaseController) -> None:
        """Attach or switch active traffic signal controller."""
        self.controller = controller
        if self.controller:
            self.controller.reset()

    def start(self, use_gui: Optional[bool] = None) -> TrafficState:
        """Start simulation session and return initial state."""
        self.traci_controller.start_simulation(use_gui=use_gui)
        if self.controller:
            self.controller.reset()
        return self.traci_controller.get_current_state()

    def step(self) -> TrafficState:
        """Advance simulation by one second, applying active controller logic if present."""
        current_state = self.traci_controller.get_current_state()

        if self.controller:
            self.controller.step(current_state, self.traci_controller)

        next_state = self.traci_controller.step_simulation()
        return next_state

    def get_state(self) -> TrafficState:
        """Query instantaneous state."""
        return self.traci_controller.get_current_state()

    def get_metrics(self) -> SimulationMetrics:
        """Query instantaneous step metrics."""
        return self.traci_controller.get_metrics()

    def get_aggregate_metrics(self) -> AggregateMetrics:
        """Query cumulative aggregate summary metrics."""
        return self.traci_controller.get_aggregate_metrics()

    def set_signal_phase(self, phase_index: int) -> None:
        """Directly set the active traffic light phase on TraCI."""
        self.traci_controller.set_tls_phase(phase_index)

    def close(self) -> None:
        """Safely close simulation session."""
        self.traci_controller.close_simulation()

    def is_active(self) -> bool:
        """Check whether simulation is actively progressing."""
        return self.traci_controller.is_running()
