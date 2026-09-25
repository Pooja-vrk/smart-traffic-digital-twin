"""Simulation manager service coordinating SUMO execution, controllers, and background lifecycle."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from backend.config.settings import settings
from backend.schemas.simulation import (
    ControllerInfo,
    SimulationResultResponse,
    SimulationStartRequest,
    SimulationStartResponse,
    SimulationStatusResponse,
    SimulationStopResponse,
)
from backend.schemas.traffic import TrafficSnapshotResponse
from backend.services.persistence_service import PersistenceService
from backend.services.telemetry_service import TelemetryService
from backend.websocket.manager import ws_manager
from simulation.config import AdaptiveConfig, FixedTimeConfig

from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.base_controller import BaseController
from simulation.controllers.dqn_controller import DQNController
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.environment import TrafficSimulationEnvironment
from simulation.metrics import AggregateMetrics


logger = logging.getLogger(__name__)


class SimulationAlreadyRunningError(Exception):
    """Raised when attempting to start a simulation while another is active."""
    pass


class ControllerNotFoundError(Exception):
    """Raised when an invalid controller type is requested."""
    pass


class ModelNotFoundError(Exception):
    """Raised when the DQN model checkpoint file is missing."""
    pass


class SimulationManager:
    """Coordinates execution of SUMO simulations in non-blocking background threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Lifecycle state
        self._status: str = "idle"  # idle, starting, running, stopping, completed, stopped, error
        self._simulation_id: Optional[str] = None
        self._active_controller_type: Optional[str] = None
        self._active_controller: Optional[BaseController] = None
        self._seed: Optional[int] = None
        self._current_step: int = 0
        self._total_steps: int = 0
        self._simulation_time: float = 0.0
        self._error_message: Optional[str] = None

        # Data snapshots
        self._latest_snapshot: Optional[TrafficSnapshotResponse] = None
        self._last_result: Optional[SimulationResultResponse] = None
        self._peak_queue: int = 0

        # Event loop reference for WebSocket dispatching from worker thread
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store main async event loop reference for cross-thread WebSocket broadcasts."""
        self._main_loop = loop

    def is_running(self) -> bool:
        """Check whether a simulation is currently active."""
        with self._lock:
            return self._status in {"starting", "running", "stopping"}

    def get_status(self) -> SimulationStatusResponse:
        """Return instantaneous lifecycle state of the simulation manager."""
        with self._lock:
            return SimulationStatusResponse(
                running=self._status in {"starting", "running", "stopping"},
                status=self._status,
                simulation_id=self._simulation_id,
                controller=self._active_controller_type,
                seed=self._seed,
                current_step=self._current_step if self._status != "idle" else None,
                total_steps=self._total_steps if self._status != "idle" else None,
                simulation_time=self._simulation_time if self._status != "idle" else None,
                error=self._error_message,
            )

    def get_available_controllers(self) -> list[ControllerInfo]:
        """Return list of available traffic controllers and DQN model availability."""
        model_exists = Path(settings.DQN_MODEL_PATH).is_file()
        return [
            ControllerInfo(
                id="fixed",
                name="Fixed-Time",
                type="baseline",
                available=True,
            ),
            ControllerInfo(
                id="adaptive",
                name="Rule-Based Adaptive",
                type="adaptive",
                available=True,
            ),
            ControllerInfo(
                id="dqn",
                name="Deep Q-Network",
                type="reinforcement_learning",
                available=model_exists,
                model_path=settings.DQN_MODEL_PATH if model_exists else None,
            ),
        ]

    def _create_controller(self, controller_type: str) -> BaseController:
        """Instantiate selected controller."""
        c_type = controller_type.lower().strip()
        if c_type == "fixed":
            return FixedTimeController(config=FixedTimeConfig())
        elif c_type == "adaptive":
            return AdaptiveController(config=AdaptiveConfig())
        elif c_type == "dqn":
            model_path = Path(settings.DQN_MODEL_PATH)
            if not model_path.is_file():
                # Check fallback best model
                best_path = Path(settings.DQN_BEST_MODEL_PATH)
                if best_path.is_file():
                    model_path = best_path
                else:
                    raise ModelNotFoundError(
                        f"DQN model checkpoint not found at: {model_path.resolve()}. "
                        f"Please train the model first using 'python -m ai.train'."
                    )
            return DQNController(model_path=model_path)
        else:
            raise ControllerNotFoundError(f"Unknown controller type: '{controller_type}'")


    def start_simulation(self, request: SimulationStartRequest) -> SimulationStartResponse:
        """Initiate background simulation execution."""
        with self._lock:
            if self._status in {"starting", "running", "stopping"}:
                raise SimulationAlreadyRunningError(
                    f"Simulation {self._simulation_id} is currently running in status '{self._status}'."
                )

            # Validate controller & instantiate before launching thread
            controller = self._create_controller(request.controller)

            sim_id = str(uuid.uuid4())[:8]
            self._simulation_id = sim_id
            self._active_controller_type = request.controller
            self._active_controller = controller
            self._seed = request.seed
            self._current_step = 0
            self._total_steps = request.steps
            self._simulation_time = 0.0
            self._error_message = None
            self._peak_queue = 0
            self._latest_snapshot = None
            self._status = "starting"
            self._stop_event.clear()

            # Launch background worker
            self._thread = threading.Thread(
                target=self._run_simulation_worker,
                args=(sim_id, request.controller, controller, request.steps, request.seed, request.gui),
                name=f"sim-worker-{sim_id}",
                daemon=True,
            )
            self._thread.start()

            # Persist initial run record to database
            PersistenceService.start_simulation_run(
                simulation_id=sim_id,
                controller=request.controller,
                seed=request.seed,
                steps=request.steps,
                gui=request.gui,
            )

            logger.info("Simulation %s started with controller=%s, steps=%d, seed=%d",
                        sim_id, request.controller, request.steps, request.seed)

            # Broadcast simulation_started event
            if self._main_loop:
                start_msg = TelemetryService.create_websocket_message(
                    msg_type="simulation_started",
                    simulation_id=sim_id,
                    data={
                        "controller": request.controller,
                        "steps": request.steps,
                        "seed": request.seed,
                    },
                )
                ws_manager.broadcast_from_thread(start_msg, self._main_loop)

            return SimulationStartResponse(
                status="started",
                simulation_id=sim_id,
                controller=request.controller,
                steps=request.steps,
                seed=request.seed,
            )

    def stop_simulation(self) -> SimulationStopResponse:
        """Request graceful termination of active simulation."""
        with self._lock:
            if self._status not in {"starting", "running", "stopping"}:
                return SimulationStopResponse(
                    status="idle",
                    simulation_id=self._simulation_id,
                )
            # If already stopping, just re-assert the event (idempotent) and return
            if self._status == "stopping":
                self._stop_event.set()
                return SimulationStopResponse(
                    status="stopping",
                    simulation_id=self._simulation_id,
                )
            self._status = "stopping"
            self._stop_event.set()
            sim_id = self._simulation_id

        logger.info("Stop requested for simulation %s", sim_id)
        return SimulationStopResponse(
            status="stopping",
            simulation_id=sim_id,
        )

    def get_current_traffic(self) -> Optional[TrafficSnapshotResponse]:
        """Return the latest instantaneous traffic state snapshot."""
        with self._lock:
            return self._latest_snapshot

    def get_latest_result(self) -> Optional[SimulationResultResponse]:
        """Return aggregated result of the most recent completed simulation run."""
        with self._lock:
            return self._last_result

    def _run_simulation_worker(
        self,
        sim_id: str,
        controller_name: str,
        controller: BaseController,
        total_steps: int,
        seed: int,
        gui: bool,
    ) -> None:
        """Worker thread executing the SUMO simulation loop."""
        env: Optional[TrafficSimulationEnvironment] = None
        final_status = "completed"
        aggregate_metrics: Optional[AggregateMetrics] = None
        prev_phase: int = 0

        try:
            env = TrafficSimulationEnvironment(
                step_length=1.0,
                seed=seed,
                use_gui=gui,
                controller=controller,
            )

            initial_state = env.start()
            prev_phase = initial_state.current_phase

            with self._lock:
                self._status = "running"
                self._simulation_time = initial_state.simulation_time
                self._current_step = initial_state.step
                self._peak_queue = initial_state.total_queue
                self._latest_snapshot = TelemetryService.create_snapshot(
                    state=initial_state,
                    metrics=None,
                    controller=controller,
                    simulation_id=sim_id,
                    peak_queue=self._peak_queue,
                )

            # Persist initial traffic snapshot
            PersistenceService.save_traffic_snapshot(self._latest_snapshot.model_dump())

            # Step simulation loop
            for step_num in range(1, total_steps + 1):
                if self._stop_event.is_set():
                    logger.info("Worker detected stop event at step %d for simulation %s", step_num, sim_id)
                    final_status = "stopped"
                    break

                next_state = env.step()
                step_metrics = env.get_metrics()

                with self._lock:
                    self._current_step = step_num
                    self._simulation_time = next_state.simulation_time
                    self._peak_queue = max(self._peak_queue, next_state.total_queue)
                    snapshot = TelemetryService.create_snapshot(
                        state=next_state,
                        metrics=step_metrics,
                        controller=controller,
                        simulation_id=sim_id,
                        peak_queue=self._peak_queue,
                    )
                    self._latest_snapshot = snapshot

                # Persist periodic snapshot to database
                PersistenceService.save_traffic_snapshot(snapshot.model_dump())

                # Persist controller signal decisions
                if snapshot.ai is not None:
                    # DQN Decision logging
                    PersistenceService.save_signal_decision(
                        simulation_id=sim_id,
                        simulation_time=next_state.simulation_time,
                        controller=controller_name,
                        action_id=snapshot.ai.action_id,
                        action_name=snapshot.ai.action,
                        requested_phase=snapshot.ai.requested_phase,
                        approved=snapshot.ai.approved,
                        reason=snapshot.ai.reason,
                        current_phase=next_state.current_phase,
                        elapsed_green=next_state.time_since_phase_change,
                    )
                elif next_state.current_phase != prev_phase:
                    # Classical controller phase change logging
                    PersistenceService.save_signal_decision(
                        simulation_id=sim_id,
                        simulation_time=next_state.simulation_time,
                        controller=controller_name,
                        action_id=next_state.current_phase,
                        action_name=snapshot.signal.phase_name,
                        requested_phase=next_state.current_phase,
                        approved=True,
                        reason=f"{controller_name} transition to {snapshot.signal.phase_name}",
                        current_phase=next_state.current_phase,
                        elapsed_green=next_state.time_since_phase_change,
                    )
                prev_phase = next_state.current_phase

                # Broadcast live traffic update
                if self._main_loop:
                    telemetry_msg = TelemetryService.create_websocket_message(
                        msg_type="traffic_update",
                        simulation_id=sim_id,
                        data=snapshot.model_dump(),
                    )
                    ws_manager.broadcast_from_thread(telemetry_msg, self._main_loop)

            # Query final aggregate performance metrics
            aggregate_metrics = env.get_aggregate_metrics()

        except Exception as exc:
            logger.error("Simulation %s encountered runtime exception: %s", sim_id, exc, exc_info=True)
            final_status = "error"
            with self._lock:
                self._error_message = str(exc)

        finally:
            # Safely close TraCI
            if env is not None:
                try:
                    env.close()
                except Exception as close_exc:
                    logger.warning("Error closing TraCI connection: %s", close_exc)

            final_metrics_dict = aggregate_metrics.to_dict() if aggregate_metrics is not None else None

            # Persist completed simulation run record with final metrics
            PersistenceService.complete_simulation_run(
                simulation_id=sim_id,
                status=final_status,
                final_step=self._current_step,
                metrics=final_metrics_dict,
            )

            # Record in-memory final results
            with self._lock:
                self._status = final_status
                if final_status == "completed" and aggregate_metrics is not None:
                    self._last_result = SimulationResultResponse(
                        simulation_id=sim_id,
                        controller=controller_name,
                        seed=seed,
                        steps=self._current_step,
                        status="completed",
                        metrics=final_metrics_dict,
                    )

            logger.info("Simulation %s finished with final_status='%s'", sim_id, final_status)

            # Broadcast terminal WebSocket event
            if self._main_loop:
                event_type = (
                    "simulation_completed"
                    if final_status == "completed"
                    else ("simulation_stopped" if final_status == "stopped" else "simulation_error")
                )
                event_data: Dict[str, Any] = {
                    "controller": controller_name,
                    "seed": seed,
                    "final_step": self._current_step,
                }
                if aggregate_metrics is not None:
                    event_data["metrics"] = final_metrics_dict
                if final_status == "error":
                    event_data["error"] = self._error_message

                final_msg = TelemetryService.create_websocket_message(
                    msg_type=event_type,
                    simulation_id=sim_id,
                    data=event_data,
                )
                ws_manager.broadcast_from_thread(final_msg, self._main_loop)

                # ── FIX: also push a status_update so the frontend simulationStatus
                # state reflects the terminal lifecycle change immediately.
                # Without this the frontend never learns the simulation has stopped
                # because it only updates simulationStatus from status_update events.
                status_msg = TelemetryService.create_websocket_message(
                    msg_type="status_update",
                    simulation_id=sim_id,
                    data={
                        "running": False,
                        "status": final_status,
                        "simulation_id": sim_id,
                        "controller": controller_name,
                        "seed": seed,
                        "current_step": self._current_step,
                        "total_steps": total_steps,
                        "simulation_time": self._simulation_time,
                        "error": self._error_message,
                    },
                )
                ws_manager.broadcast_from_thread(status_msg, self._main_loop)


    def shutdown(self) -> None:
        """Gracefully terminate any active worker on application shutdown."""
        if self.is_running():
            logger.info("Shutting down active simulation...")
            self.stop_simulation()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3.0)


# Global SimulationManager singleton
sim_manager = SimulationManager()
