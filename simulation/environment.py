"""Simulation environment coordinator for the 4-way intersection.

Provides a unified controller-agnostic simulation interface for running
and benchmarking Fixed-Time, Adaptive, or Reinforcement Learning controllers.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from simulation.controllers.base_controller import BaseController

from simulation.config import ExperimentConfig
from simulation.coordination import MultiIntersectionCoordinator, MultiIntersectionState
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
        simulation_id: Optional[str] = None,
        enable_agentic_engine: bool = True,
        enable_emergency_priority: bool = True,
    ) -> None:
        self.controller = controller
        self.simulation_id = simulation_id
        self.enable_emergency_priority = enable_emergency_priority
        if self.controller is not None:
            self.controller.enable_emergency_priority = enable_emergency_priority

        self.traci_controller = TraCIController(
            sumocfg_path=sumocfg_path,
            use_gui=use_gui,
            step_length=step_length,
            seed=seed,
            tls_id=tls_id,
        )

        self.coordinator = MultiIntersectionCoordinator(primary_intersection_id=tls_id)

        self.agentic_engine: Optional[Any] = None
        if enable_agentic_engine and self.controller is not None:
            from simulation.agentic.engine import AgenticTrafficEngine
            self.agentic_engine = AgenticTrafficEngine(
                controller=self.controller,
                simulation_id=self.simulation_id,
                enable_emergency_priority=enable_emergency_priority,
            )

    def set_controller(self, controller: BaseController) -> None:
        """Attach or switch active traffic signal controller."""
        self.controller = controller
        if self.agentic_engine is not None:
            self.agentic_engine.set_controller(controller)
        elif self.controller:
            self.controller.reset()

    def start(self, use_gui: Optional[bool] = None) -> TrafficState:
        """Start simulation session and return initial state."""
        self.traci_controller.start_simulation(use_gui=use_gui)
        self.coordinator.reset()
        if self.agentic_engine is not None:
            self.agentic_engine.reset()
        elif self.controller:
            self.controller.reset()
        init_state = self.traci_controller.get_current_state()
        self.coordinator.step(init_state, step_length=self.traci_controller.step_length)
        return init_state

    def step(self) -> TrafficState:
        """Advance simulation by one second, applying active controller logic if present."""
        current_state = self.traci_controller.get_current_state()

        # Update multi-intersection coordination with current primary state
        self.coordinator.step(current_state, step_length=self.traci_controller.step_length)

        if self.agentic_engine is not None:
            self.agentic_engine.step(current_state, self.traci_controller)
        elif self.controller:
            self.controller.step(current_state, self.traci_controller)

        next_state = self.traci_controller.step_simulation()
        return next_state

    def get_coordination_state(self) -> MultiIntersectionState:
        """Query multi-intersection progression and neighbor coordination state."""
        return self.coordinator.get_state()

    def get_latest_decision(self) -> Optional[Any]:
        """Query most recent agentic decision record if engine is active."""
        if self.agentic_engine is not None:
            return self.agentic_engine.get_latest_decision()
        return None

    def get_state(self) -> TrafficState:
        """Query instantaneous state."""
        return self.traci_controller.get_current_state()

    def get_metrics(self) -> SimulationMetrics:
        """Query instantaneous step metrics."""
        return self.traci_controller.get_metrics()

    def get_aggregate_metrics(self) -> AggregateMetrics:
        """Query cumulative aggregate summary metrics."""
        return self.traci_controller.get_aggregate_metrics()

    def get_emergency_metrics(self) -> Optional[Dict[str, Any]]:
        """Query emergency vehicle green corridor metrics."""
        return self.traci_controller.get_emergency_metrics()

    def set_signal_phase(self, phase_index: int) -> None:
        """Directly set the active traffic light phase on TraCI."""
        self.traci_controller.set_tls_phase(phase_index)

    def close(self) -> None:
        """Safely close simulation session."""
        if self.agentic_engine is not None:
            self.agentic_engine.shutdown()
        self.traci_controller.close_simulation()

    def is_active(self) -> bool:
        """Check whether simulation is actively progressing."""
        return self.traci_controller.is_running()
