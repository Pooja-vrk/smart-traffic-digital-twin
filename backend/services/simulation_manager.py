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
    EmergencyVehicleRequest,
    EmergencyVehicleResponse,
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
from prediction.predictor import predictor
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


class SimulationNotRunningError(Exception):
    """Raised when attempting an emergency action when no simulation is active."""
    pass


class EmergencyAlreadyActiveError(Exception):
    """Raised when an emergency vehicle is already scheduled or active."""
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
        self._lock = threading.RLock()
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

        # Emergency vehicle scheduling
        self._scheduled_emergency: Optional[Dict[str, Any]] = None
        self._emergency_counter: int = 0

        # Multi-intersection coordination settings
        self._coordination_mode: str = "ARTERY_EW"
        self._env: Optional[Any] = None

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

            from backend.services.scenario_manager import scenario_manager
            if scenario_manager.is_running():
                raise SimulationAlreadyRunningError(
                    "A Scenario Lab experiment is currently running. Stop the active scenario before starting a new simulation."
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

            # Configure initial emergency vehicle if requested
            if getattr(request, "emergency_vehicle", False):
                self._emergency_counter = 1
                self._scheduled_emergency = {
                    "vehicle_id": "EV_01",
                    "vehicle_type": getattr(request, "emergency_vehicle_type", "ambulance") or "ambulance",
                    "approach": getattr(request, "emergency_approach", "east") or "east",
                    "spawn_step": getattr(request, "emergency_step", 5) if getattr(request, "emergency_step", None) is not None else 5,
                    "injected": False,
                }
            else:
                self._scheduled_emergency = None
                self._emergency_counter = 0

            # Reset predictive live evaluation tracker for new run
            predictor.reset_live_tracker(sim_id)

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

    def trigger_emergency_vehicle(self, request: EmergencyVehicleRequest) -> EmergencyVehicleResponse:
        """Dynamically schedule or inject an emergency vehicle into the active simulation."""
        with self._lock:
            if self._status not in {"starting", "running"}:
                raise SimulationNotRunningError(
                    f"Cannot activate emergency vehicle: simulation is not running (current status: '{self._status}')."
                )

            # Prevent duplicate emergency requests if one is currently pending injection
            if self._scheduled_emergency is not None and not self._scheduled_emergency.get("injected", False):
                raise EmergencyAlreadyActiveError(
                    f"An emergency vehicle ({self._scheduled_emergency.get('vehicle_id')}) is already scheduled for step {self._scheduled_emergency.get('spawn_step')}."
                )

            # Prevent duplicate if an emergency vehicle is currently active in the simulation corridor
            if (
                self._latest_snapshot is not None
                and self._latest_snapshot.emergency is not None
                and (
                    self._latest_snapshot.emergency.active
                    or (
                        self._latest_snapshot.emergency.lifecycle_state
                        and self._latest_snapshot.emergency.lifecycle_state not in {"IDLE", "None", "", None}
                    )
                )
            ):
                raise EmergencyAlreadyActiveError(
                    f"An emergency vehicle is already actively preempting corridor (state: {self._latest_snapshot.emergency.lifecycle_state})."
                )

            if request.spawn_step is not None and request.spawn_step > self._total_steps:
                raise ValueError(
                    f"Requested spawn step {request.spawn_step} exceeds total simulation steps ({self._total_steps})."
                )

            # Target step calculation: if None or <= current step, target current step (injected on next loop tick)
            target_step = (
                max(self._current_step, request.spawn_step)
                if request.spawn_step is not None
                else self._current_step
            )

            self._emergency_counter += 1
            vehicle_id = f"EV_{self._emergency_counter:02d}"

            self._scheduled_emergency = {
                "vehicle_id": vehicle_id,
                "vehicle_type": request.vehicle_type,
                "approach": request.approach.lower(),
                "spawn_step": target_step,
                "injected": False,
            }

            status_str = "scheduled" if target_step > self._current_step else "activating"
            sim_id = self._simulation_id or ""
            msg = f"Emergency {request.vehicle_type} ({vehicle_id}) {status_str} for approach '{request.approach}' at step {target_step}."
            logger.info("Simulation %s: %s", sim_id, msg)

            # Broadcast WebSocket notification
            if self._main_loop:
                ws_msg = TelemetryService.create_websocket_message(
                    msg_type="emergency_scheduled",
                    simulation_id=sim_id,
                    data={
                        "vehicle_id": vehicle_id,
                        "vehicle_type": request.vehicle_type,
                        "approach": request.approach.lower(),
                        "spawn_step": target_step,
                        "status": status_str,
                    },
                )
                ws_manager.broadcast_from_thread(ws_msg, self._main_loop)

            return EmergencyVehicleResponse(
                status=status_str,
                simulation_id=sim_id,
                vehicle_id=vehicle_id,
                vehicle_type=request.vehicle_type,
                approach=request.approach.lower(),
                spawn_step=target_step,
                message=msg,
            )

    def get_emergency_status(self) -> Dict[str, Any]:
        """Return current status of scheduled and active emergency vehicle state."""
        with self._lock:
            sched = dict(self._scheduled_emergency) if self._scheduled_emergency else None
            emer = (
                self._latest_snapshot.emergency.model_dump()
                if (self._latest_snapshot and self._latest_snapshot.emergency)
                else None
            )
            return {
                "simulation_id": self._simulation_id,
                "running": self.is_running(),
                "scheduled": sched,
                "emergency": emer,
            }

    def get_coordination_status(self) -> Dict[str, Any]:
        """Return instantaneous multi-intersection coordination status and metrics."""
        with self._lock:
            if self._latest_snapshot is not None and self._latest_snapshot.coordination is not None:
                return {
                    "simulation_id": self._simulation_id,
                    "running": self.is_running(),
                    "coordination": self._latest_snapshot.coordination.model_dump(),
                }

            if self._env is not None and hasattr(self._env, "get_coordination_state"):
                c_state = self._env.get_coordination_state()
                return {
                    "simulation_id": self._simulation_id,
                    "running": self.is_running(),
                    "coordination": c_state.to_dict() if hasattr(c_state, "to_dict") else vars(c_state),
                }

            from simulation.coordination import MultiIntersectionCoordinator
            dummy_coord = MultiIntersectionCoordinator(mode=self._coordination_mode)
            return {
                "simulation_id": self._simulation_id,
                "running": self.is_running(),
                "coordination": dummy_coord.get_state().to_dict(),
            }

    def set_coordination_mode(self, mode: str) -> Dict[str, Any]:
        """Dynamically update multi-intersection coordination policy mode."""
        valid_modes = {"ARTERY_EW", "ARTERY_NS", "BALANCED_ADAPTIVE", "ISOLATED"}
        mode_upper = mode.upper().strip()
        if mode_upper not in valid_modes:
            raise ValueError(f"Invalid coordination mode '{mode}'. Valid modes: {sorted(list(valid_modes))}")

        with self._lock:
            self._coordination_mode = mode_upper
            if self._env is not None and hasattr(self._env, "coordinator"):
                self._env.coordinator.set_mode(mode_upper)
                c_state = self._env.get_coordination_state()
                data_dict = c_state.to_dict() if hasattr(c_state, "to_dict") else vars(c_state)
            else:
                from simulation.coordination import MultiIntersectionCoordinator
                dummy_coord = MultiIntersectionCoordinator(mode=mode_upper)
                data_dict = dummy_coord.get_state().to_dict()

            sim_id = self._simulation_id or ""
            if self._main_loop and self.is_running():
                ws_msg = TelemetryService.create_websocket_message(
                    msg_type="coordination_update",
                    simulation_id=sim_id,
                    data=data_dict,
                )
                ws_manager.broadcast_from_thread(ws_msg, self._main_loop)

            return {
                "status": "success",
                "simulation_id": sim_id,
                "mode": mode_upper,
                "message": f"Multi-intersection coordination mode switched to '{mode_upper}'.",
                "coordination": data_dict,
            }

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
                simulation_id=sim_id,
            )
            with self._lock:
                self._env = env
                if hasattr(env, "coordinator"):
                    env.coordinator.set_mode(self._coordination_mode)

            initial_state = env.start()
            prev_phase = initial_state.current_phase

            with self._lock:
                self._status = "running"
                self._simulation_time = initial_state.simulation_time
                self._current_step = initial_state.step
                self._peak_queue = initial_state.total_queue
                coord_init = env.get_coordination_state() if hasattr(env, "get_coordination_state") else None
                self._latest_snapshot = TelemetryService.create_snapshot(
                    state=initial_state,
                    metrics=None,
                    controller=controller,
                    simulation_id=sim_id,
                    peak_queue=self._peak_queue,
                    agentic_decision=env.get_latest_decision(),
                    coordination_state=coord_init,
                )

            # Persist initial traffic snapshot
            PersistenceService.save_traffic_snapshot(self._latest_snapshot.model_dump())

            # Step simulation loop
            for step_num in range(1, total_steps + 1):
                if self._stop_event.is_set():
                    logger.info("Worker detected stop event at step %d for simulation %s", step_num, sim_id)
                    final_status = "stopped"
                    break

                # Check dynamic or scheduled emergency injection
                inject_data: Optional[Dict[str, Any]] = None
                with self._lock:
                    if (
                        self._scheduled_emergency is not None
                        and not self._scheduled_emergency.get("injected", False)
                        and step_num >= self._scheduled_emergency.get("spawn_step", 0)
                    ):
                        self._scheduled_emergency["injected"] = True
                        inject_data = dict(self._scheduled_emergency)

                if inject_data and env and env.traci_controller:
                    try:
                        logger.info(
                            "Injecting dynamic emergency vehicle %s (%s) on approach '%s' at step %d",
                            inject_data["vehicle_id"],
                            inject_data["vehicle_type"],
                            inject_data["approach"],
                            step_num,
                        )
                        env.traci_controller.inject_emergency_vehicle(
                            vehicle_id=inject_data["vehicle_id"],
                            vehicle_type=inject_data["vehicle_type"],
                            approach=inject_data["approach"],
                        )
                    except Exception as inject_err:
                        logger.error("Failed to inject emergency vehicle in TraCI: %s", inject_err, exc_info=True)

                next_state = env.step()
                step_metrics = env.get_metrics()
                decision = env.get_latest_decision()
                coord_state = env.get_coordination_state() if hasattr(env, "get_coordination_state") else None

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
                        agentic_decision=decision,
                        coordination_state=coord_state,
                    )
                    self._latest_snapshot = snapshot

                    # If emergency vehicle was injected and has finished corridor passage and restored to IDLE, reset slot
                    if (
                        self._scheduled_emergency is not None
                        and self._scheduled_emergency.get("injected", False)
                        and snapshot.emergency is not None
                        and not snapshot.emergency.active
                        and snapshot.emergency.lifecycle_state in {"IDLE", "None", "", None}
                    ):
                        self._scheduled_emergency = None

                # Persist periodic snapshot to database
                PersistenceService.save_traffic_snapshot(snapshot.model_dump())

                # Persist controller signal decisions
                if decision is not None:
                    if snapshot.prediction and snapshot.prediction.model_available:
                        decision.prediction = snapshot.prediction.model_dump()
                    PersistenceService.save_agentic_decision(decision.to_dict())
                    PersistenceService.save_signal_decision(
                        simulation_id=sim_id,
                        simulation_time=next_state.simulation_time,
                        controller=controller_name,
                        action_id=snapshot.ai.action_id if snapshot.ai else decision.validated_phase,
                        action_name=decision.requested_action,
                        requested_phase=decision.requested_phase,
                        approved=(decision.validated_action == "APPROVED"),
                        reason=decision.decision_reason,
                        current_phase=next_state.current_phase,
                        elapsed_green=next_state.time_since_phase_change,
                    )
                elif snapshot.ai is not None:
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

            # Retrieve verified live prediction metrics
            pred_metrics = predictor.get_live_tracker_metrics()

            # Record in-memory final results
            with self._lock:
                self._status = final_status
                self._env = None
                self._scheduled_emergency = None
                if final_status == "completed" and aggregate_metrics is not None:
                    self._last_result = SimulationResultResponse(
                        simulation_id=sim_id,
                        controller=controller_name,
                        seed=seed,
                        steps=self._current_step,
                        status="completed",
                        metrics=final_metrics_dict,
                        prediction_metrics=pred_metrics,
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
                    "prediction_metrics": pred_metrics,
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
