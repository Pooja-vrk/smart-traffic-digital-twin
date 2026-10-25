"""Scenario / What-If Lab Manager coordinating real SUMO traffic demand scenarios."""

from __future__ import annotations

import asyncio
import datetime
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config.settings import settings
from backend.database.repositories.scenario_repository import ScenarioRepository
from backend.schemas.scenario import (
    DirectionBiasSchema,
    ScenarioHistoryItem,
    ScenarioPresetInfo,
    ScenarioResultResponse,
    ScenarioRunRequest,
    ScenarioStatusResponse,
)
from backend.services.persistence_service import PersistenceService
from backend.services.simulation_manager import (
    ControllerNotFoundError,
    ModelNotFoundError,
    SimulationAlreadyRunningError,
    sim_manager,
)
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
from simulation.scenario_generator import (
    DirectionBias,
    ScenarioConfig,
    ScenarioDemandGenerator,
)

logger = logging.getLogger(__name__)


# Standard Pre-Configured Traffic Scenarios
SCENARIO_PRESETS: List[ScenarioPresetInfo] = [
    ScenarioPresetInfo(
        id="balanced",
        name="Balanced / Normal Traffic",
        description="Even 25% traffic distribution across all approaches with moderate baseline density.",
        density="medium",
        multiplier=1.0,
        direction_bias=DirectionBiasSchema(north=25.0, south=25.0, east=25.0, west=25.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="high_traffic",
        name="High Traffic Congestion",
        description="1.5x higher traffic volume symmetrically across all corridors to evaluate saturation limits.",
        density="high",
        multiplier=1.5,
        direction_bias=DirectionBiasSchema(north=25.0, south=25.0, east=25.0, west=25.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="east_heavy",
        name="East Corridor Inflow Surge",
        description="Major arterial influx from the East (55%) with lighter cross traffic.",
        density="high",
        multiplier=1.5,
        direction_bias=DirectionBiasSchema(north=15.0, south=15.0, east=55.0, west=15.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="north_south_corridor",
        name="North-South Main Corridor",
        description="Dominant North-South corridor traffic (80% combined) simulating peak hour commuter rush.",
        density="high",
        multiplier=1.5,
        direction_bias=DirectionBiasSchema(north=40.0, south=40.0, east=10.0, west=10.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="west_heavy",
        name="West Corridor Inflow Surge",
        description="Heavy directional traffic originating from the West approach (55%).",
        density="high",
        multiplier=1.5,
        direction_bias=DirectionBiasSchema(north=15.0, south=15.0, east=15.0, west=55.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="south_heavy",
        name="South Approach Influx",
        description="Heavy directional traffic originating from the South approach (55%).",
        density="high",
        multiplier=1.5,
        direction_bias=DirectionBiasSchema(north=15.0, south=55.0, east=15.0, west=15.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="north_heavy",
        name="North Approach Influx",
        description="Heavy directional traffic originating from the North approach (55%).",
        density="high",
        multiplier=1.5,
        direction_bias=DirectionBiasSchema(north=55.0, south=15.0, east=15.0, west=15.0),
        recommended_duration=300,
    ),
    ScenarioPresetInfo(
        id="emergency_east",
        name="Emergency Priority (East - E2C)",
        description="High-priority emergency ambulance approaching from the East corridor at step 15, testing safety-constrained signal preemption.",
        density="medium",
        multiplier=1.0,
        direction_bias=DirectionBiasSchema(north=25.0, south=25.0, east=25.0, west=25.0),
        recommended_duration=120,
        emergency_vehicle=True,
        emergency_approach="east",
        emergency_step=15,
        emergency_vehicle_type="ambulance",
    ),
    ScenarioPresetInfo(
        id="emergency_west",
        name="Emergency Priority (West - W2C)",
        description="High-priority emergency ambulance approaching from the West corridor at step 15, testing safety-constrained signal preemption.",
        density="medium",
        multiplier=1.0,
        direction_bias=DirectionBiasSchema(north=25.0, south=25.0, east=25.0, west=25.0),
        recommended_duration=120,
        emergency_vehicle=True,
        emergency_approach="west",
        emergency_step=15,
        emergency_vehicle_type="ambulance",
    ),
    ScenarioPresetInfo(
        id="emergency_north",
        name="Emergency Priority (North - N2C)",
        description="High-priority emergency fire engine approaching from the North corridor at step 15, testing safety-constrained signal preemption.",
        density="medium",
        multiplier=1.0,
        direction_bias=DirectionBiasSchema(north=25.0, south=25.0, east=25.0, west=25.0),
        recommended_duration=120,
        emergency_vehicle=True,
        emergency_approach="north",
        emergency_step=15,
        emergency_vehicle_type="fire_engine",
    ),
    ScenarioPresetInfo(
        id="emergency_south",
        name="Emergency Priority (South - S2C)",
        description="High-priority emergency ambulance approaching from the South corridor at step 15, testing safety-constrained signal preemption.",
        density="medium",
        multiplier=1.0,
        direction_bias=DirectionBiasSchema(north=25.0, south=25.0, east=25.0, west=25.0),
        recommended_duration=120,
        emergency_vehicle=True,
        emergency_approach="south",
        emergency_step=15,
        emergency_vehicle_type="ambulance",
    ),
]


class ScenarioManager:
    """Coordinates execution of real SUMO scenario simulations and multi-controller benchmarks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Lifecycle state
        self._status: str = "idle"  # idle, configuring, queued, starting, running, completed, stopping, stopped, failed
        self._scenario_id: Optional[str] = None
        self._scenario_name: Optional[str] = None
        self._active_controller: Optional[str] = None
        self._seed: Optional[int] = None
        self._duration: Optional[int] = None
        self._current_step: int = 0
        self._total_steps: int = 0
        self._simulation_time: float = 0.0
        self._is_comparison: bool = False
        self._current_stage: Optional[str] = None
        self._stage_index: Optional[int] = None
        self._total_stages: Optional[int] = None
        self._error_message: Optional[str] = None

        self._latest_result: Optional[ScenarioResultResponse] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store main async event loop reference for cross-thread WebSocket broadcasts."""
        self._main_loop = loop

    def is_running(self) -> bool:
        """Check whether a scenario experiment is currently running."""
        with self._lock:
            return self._status in {"configuring", "queued", "starting", "running", "stopping"}

    def get_status(self) -> ScenarioStatusResponse:
        """Return instantaneous lifecycle state of the Scenario Lab runner."""
        with self._lock:
            running = self._status in {"configuring", "queued", "starting", "running", "stopping"}
            pct: Optional[float] = None
            if self._total_steps > 0:
                if self._is_comparison and self._total_stages and self._stage_index:
                    overall_steps = (self._stage_index - 1) * self._duration + self._current_step
                    total_all = self._total_stages * self._duration
                    pct = round((overall_steps / total_all) * 100, 1)
                else:
                    pct = round((self._current_step / self._total_steps) * 100, 1)

            return ScenarioStatusResponse(
                running=running,
                status=self._status,
                scenario_id=self._scenario_id,
                scenario_name=self._scenario_name,
                controller=self._active_controller,
                seed=self._seed,
                current_step=self._current_step if self._status != "idle" else None,
                total_steps=self._total_steps if self._status != "idle" else None,
                simulation_time=self._simulation_time if self._status != "idle" else None,
                is_comparison=self._is_comparison,
                current_stage=self._current_stage,
                stage_index=self._stage_index,
                total_stages=self._total_stages,
                progress_pct=pct,
                error=self._error_message,
            )

    def get_presets(self) -> List[ScenarioPresetInfo]:
        """Return available traffic scenario presets."""
        return SCENARIO_PRESETS

    def get_latest_result(self) -> Optional[ScenarioResultResponse]:
        """Return results of the most recent completed scenario."""
        with self._lock:
            return self._latest_result

    def get_scenario_result(self, scenario_id: str) -> Optional[ScenarioResultResponse]:
        """Query persistent storage for specific completed scenario result."""
        doc = ScenarioRepository.get_scenario(scenario_id)
        if not doc:
            return None
        return ScenarioResultResponse(**doc)

    def get_scenario_history(self, limit: int = 50) -> List[ScenarioHistoryItem]:
        """Retrieve recent scenario execution history."""
        records = ScenarioRepository.list_scenarios(limit=limit)
        items = []
        for r in records:
            cfg = r.get("configuration", {})
            items.append(
                ScenarioHistoryItem(
                    scenario_id=r.get("scenario_id", ""),
                    scenario_name=r.get("scenario_name", "Scenario"),
                    controller=r.get("controller", ""),
                    density=cfg.get("density", "custom"),
                    multiplier=float(cfg.get("multiplier", 1.0)),
                    seed=int(r.get("seed", 42)),
                    duration=int(r.get("duration", 300)),
                    status=r.get("status", "completed"),
                    metrics=r.get("metrics"),
                    is_comparison=bool(r.get("comparison")),
                    comparison=r.get("comparison"),
                    created_at=r.get("created_at"),
                )
            )
        return items

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

    def run_scenario(self, request: ScenarioRunRequest) -> ScenarioStatusResponse:
        """Start running a traffic scenario through real SUMO simulation."""
        with self._lock:
            if self._status in {"configuring", "queued", "starting", "running", "stopping"}:
                raise SimulationAlreadyRunningError(
                    f"Scenario {self._scenario_id} is currently running in status '{self._status}'. "
                    f"Please stop the current scenario before starting a new one."
                )

            # Check if general simulation is running
            if sim_manager.is_running():
                raise SimulationAlreadyRunningError(
                    "Simulation already running. Stop the current simulation before starting a new scenario."
                )

            # Validate controller if single run
            if not request.compare_all_controllers:
                self._create_controller(request.controller)

            scenario_id = f"scen_{uuid.uuid4().hex[:8]}"
            self._scenario_id = scenario_id
            self._scenario_name = request.name
            self._active_controller = "multi-controller" if request.compare_all_controllers else request.controller
            self._seed = request.seed
            self._duration = request.duration
            self._current_step = 0
            self._total_steps = request.duration
            self._simulation_time = 0.0
            self._is_comparison = request.compare_all_controllers
            self._current_stage = None
            self._stage_index = 1 if request.compare_all_controllers else 1
            self._total_stages = 3 if request.compare_all_controllers else 1
            self._error_message = None
            self._status = "starting"
            self._stop_event.clear()

            # Launch background worker
            self._thread = threading.Thread(
                target=self._run_scenario_worker,
                args=(scenario_id, request),
                name=f"scenario-worker-{scenario_id}",
                daemon=True,
            )
            self._thread.start()

            logger.info(
                "Scenario %s started: '%s' (density=%s, mult=%.2f, controller=%s, compare=%s)",
                scenario_id,
                request.name,
                request.density,
                request.multiplier or 1.0,
                request.controller,
                request.compare_all_controllers,
            )

            return self.get_status()

    def stop_scenario(self) -> ScenarioStatusResponse:
        """Request graceful halt of running scenario."""
        with self._lock:
            if self._status not in {"configuring", "queued", "starting", "running", "stopping"}:
                return self.get_status()
            self._status = "stopping"
            self._stop_event.set()
            scen_id = self._scenario_id

        logger.info("Stop requested for scenario %s", scen_id)
        return self.get_status()

    def _broadcast_ws(self, msg_type: str, data: Dict[str, Any]) -> None:
        """Helper to broadcast WebSocket messages to active clients."""
        loop = self._main_loop or sim_manager._main_loop
        if loop:
            msg = TelemetryService.create_websocket_message(
                msg_type=msg_type,
                simulation_id=self._scenario_id,
                data=data,
            )
            ws_manager.broadcast_from_thread(msg, loop)

    def _run_scenario_worker(self, scenario_id: str, request: ScenarioRunRequest) -> None:
        """Worker thread executing the real SUMO scenario runs."""
        final_status = "completed"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Build ScenarioConfig
        bias = DirectionBias(
            north=request.direction_bias.north,
            south=request.direction_bias.south,
            east=request.direction_bias.east,
            west=request.direction_bias.west,
        )
        scen_cfg = ScenarioConfig(
            name=request.name,
            density=request.density,
            multiplier=request.multiplier or 1.0,
            direction_bias=bias,
            duration=request.duration,
            seed=request.seed,
            emergency_vehicle=request.emergency_vehicle,
            emergency_approach=request.emergency_approach,
            emergency_step=request.emergency_step,
            emergency_vehicle_type=getattr(request, "emergency_vehicle_type", "ambulance"),
        )

        try:
            # 1. Generate real SUMO traffic demand files deterministically
            with self._lock:
                self._status = "configuring"
            _, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(scen_cfg)

            # Persist initial scenario entry
            init_doc = {
                "scenario_id": scenario_id,
                "scenario_name": request.name,
                "configuration": scen_cfg.to_dict(),
                "controller": "multi-controller" if request.compare_all_controllers else request.controller,
                "seed": request.seed,
                "duration": request.duration,
                "status": "running",
                "metrics": None,
                "comparison": None,
                "ai_stats": None,
                "emergency_metrics": None,
                "created_at": now_iso,
            }
            ScenarioRepository.create_scenario(init_doc)

            if request.compare_all_controllers:
                # ── MULTI-CONTROLLER BENCHMARK MODE ────────────────────────────
                controllers_to_test = [
                    ("Fixed-Time", "fixed"),
                    ("Rule-Based Adaptive", "adaptive"),
                    ("DQN Reinforcement Learning", "dqn"),
                ]
                comparison_results: Dict[str, Any] = {}
                primary_metrics: Optional[Dict[str, Any]] = None
                ai_stats: Optional[Dict[str, Any]] = None
                primary_ev_metrics: Optional[Dict[str, Any]] = None

                for idx, (c_label, c_id) in enumerate(controllers_to_test, 1):
                    if self._stop_event.is_set():
                        final_status = "stopped"
                        break

                    with self._lock:
                        self._stage_index = idx
                        self._total_stages = 3
                        self._current_stage = f"{c_label} ({idx}/3)"
                        self._active_controller = c_id
                        self._status = "running"
                        self._current_step = 0

                    self._broadcast_ws(
                        "scenario_stage_update",
                        {
                            "stage": self._current_stage,
                            "stage_index": idx,
                            "total_stages": 3,
                            "controller": c_id,
                        },
                    )

                    # Instantiate controller
                    controller_inst = self._create_controller(c_id)

                    # Run single controller pass on the generated scenario
                    agg_metrics, last_stats, ev_metrics = self._execute_sumo_pass(
                        sumocfg_path=sumocfg_path,
                        controller_name=c_label,
                        controller_inst=controller_inst,
                        duration=request.duration,
                        seed=request.seed,
                        gui=request.gui,
                    )

                    metrics_dict = agg_metrics.to_dict() if agg_metrics else {}
                    comparison_results[c_id] = {
                        "label": c_label,
                        "controller": c_id,
                        "metrics": metrics_dict,
                        "stats": last_stats,
                        "emergency_metrics": ev_metrics,
                    }

                    if c_id == "dqn":
                        primary_metrics = metrics_dict
                        ai_stats = last_stats
                        primary_ev_metrics = ev_metrics
                    elif primary_metrics is None:
                        primary_metrics = metrics_dict
                        primary_ev_metrics = ev_metrics

                if self._stop_event.is_set():
                    final_status = "stopped"

                # Compile final result
                pred_metrics = predictor.get_live_tracker_metrics()
                result_payload = ScenarioResultResponse(
                    scenario_id=scenario_id,
                    scenario_name=request.name,
                    configuration=scen_cfg.to_dict(),
                    controller="multi-controller",
                    seed=request.seed,
                    duration=request.duration,
                    status=final_status,
                    metrics=primary_metrics or {},
                    comparison=comparison_results,
                    ai_stats=ai_stats,
                    prediction_metrics=pred_metrics,
                    emergency_metrics=primary_ev_metrics,
                    created_at=now_iso,
                )

            else:
                # ── SINGLE CONTROLLER SCENARIO MODE ────────────────────────────
                controller_inst = self._create_controller(request.controller)
                with self._lock:
                    self._status = "running"
                    self._active_controller = request.controller
                    self._current_stage = f"{request.controller.upper()}"
                    self._stage_index = 1
                    self._total_stages = 1

                agg_metrics, last_stats, ev_metrics = self._execute_sumo_pass(
                    sumocfg_path=sumocfg_path,
                    controller_name=request.controller,
                    controller_inst=controller_inst,
                    duration=request.duration,
                    seed=request.seed,
                    gui=request.gui,
                    enable_emergency_priority=True,
                    broadcast_telemetry=True,
                )

                # Grounded baseline comparison for emergency vehicle scenarios
                if request.emergency_vehicle and ev_metrics and not self._stop_event.is_set():
                    try:
                        base_c = self._create_controller(request.controller)
                        base_agg, _, base_ev = self._execute_sumo_pass(
                            sumocfg_path=sumocfg_path,
                            controller_name=f"{request.controller}_baseline_no_priority",
                            controller_inst=base_c,
                            duration=request.duration,
                            seed=request.seed,
                            gui=False,
                            enable_emergency_priority=False,
                            broadcast_telemetry=False,
                        )
                        if base_ev and ev_metrics:
                            base_tt = base_ev.get("travel_time", 0.0)
                            prio_tt = ev_metrics.get("travel_time", 0.0)
                            saved_sec = max(0.0, round(base_tt - prio_tt, 2))
                            saved_pct = round((saved_sec / base_tt) * 100, 1) if base_tt > 0 else 0.0
                            base_delay = base_ev.get("intersection_delay", 0.0)
                            prio_delay = ev_metrics.get("intersection_delay", 0.0)
                            delay_red = round(((base_delay - prio_delay) / max(0.1, base_delay)) * 100, 1) if base_delay > 0 else 0.0
                            ord_impact = (
                                round(agg_metrics.average_delay - base_agg.average_delay, 2)
                                if (agg_metrics and base_agg)
                                else 0.0
                            )
                            ev_metrics["baseline_comparison"] = {
                                "baseline_travel_time": base_tt,
                                "priority_travel_time": prio_tt,
                                "time_saved_seconds": saved_sec,
                                "time_saved_pct": saved_pct,
                                "baseline_delay": base_delay,
                                "priority_delay": prio_delay,
                                "delay_reduction_pct": delay_red,
                                "baseline_stopped_waiting": base_ev.get("stopped_waiting_time", 0.0),
                                "priority_stopped_waiting": ev_metrics.get("stopped_waiting_time", 0.0),
                                "ordinary_traffic_delay_impact_sec": ord_impact,
                            }
                    except Exception as base_err:
                        logger.warning("Baseline emergency comparison pass error: %s", base_err)

                if self._stop_event.is_set():
                    final_status = "stopped"

                metrics_dict = agg_metrics.to_dict() if agg_metrics else {}
                pred_metrics = predictor.get_live_tracker_metrics()
                result_payload = ScenarioResultResponse(
                    scenario_id=scenario_id,
                    scenario_name=request.name,
                    configuration=scen_cfg.to_dict(),
                    controller=request.controller,
                    seed=request.seed,
                    duration=request.duration,
                    status=final_status,
                    metrics=metrics_dict,
                    comparison=None,
                    ai_stats=last_stats if request.controller == "dqn" else None,
                    prediction_metrics=pred_metrics,
                    emergency_metrics=ev_metrics,
                    created_at=now_iso,
                )

            # Persist finished scenario
            ScenarioRepository.update_scenario(
                scenario_id=scenario_id,
                update_data={
                    "status": final_status,
                    "metrics": result_payload.metrics,
                    "comparison": result_payload.comparison,
                    "ai_stats": result_payload.ai_stats,
                    "prediction_metrics": result_payload.prediction_metrics,
                    "emergency_metrics": result_payload.emergency_metrics,
                    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
            )

            with self._lock:
                self._status = final_status
                self._latest_result = result_payload

        except Exception as exc:
            logger.error("Scenario execution error: %s", exc, exc_info=True)
            final_status = "failed"
            with self._lock:
                self._status = "failed"
                self._error_message = str(exc)

            ScenarioRepository.update_scenario(
                scenario_id=scenario_id,
                update_data={
                    "status": "failed",
                    "error": str(exc),
                },
            )

        finally:
            logger.info("Scenario %s ended with status '%s'", scenario_id, final_status)
            self._broadcast_ws(
                "scenario_completed" if final_status == "completed" else "scenario_stopped",
                {
                    "scenario_id": scenario_id,
                    "status": final_status,
                    "prediction_metrics": predictor.get_live_tracker_metrics(),
                    "error": self._error_message,
                },
            )
            # Update status update
            status_data = self.get_status().model_dump()
            self._broadcast_ws("scenario_status_update", status_data)

    def _execute_sumo_pass(
        self,
        sumocfg_path: Path,
        controller_name: str,
        controller_inst: BaseController,
        duration: int,
        seed: int,
        gui: bool,
        enable_emergency_priority: bool = True,
        broadcast_telemetry: bool = True,
    ) -> Tuple[Optional[AggregateMetrics], Dict[str, Any], Optional[Dict[str, Any]]]:
        """Run a single SUMO simulation pass under the given controller."""
        env: Optional[TrafficSimulationEnvironment] = None
        agg_metrics: Optional[AggregateMetrics] = None
        ev_metrics: Optional[Dict[str, Any]] = None
        peak_q = 0
        prev_phase = 0

        try:
            if broadcast_telemetry:
                predictor.reset_live_tracker(self._scenario_id or "scenario")
            env = TrafficSimulationEnvironment(
                sumocfg_path=sumocfg_path,
                use_gui=gui,
                step_length=1.0,
                seed=seed,
                controller=controller_inst,
                simulation_id=self._scenario_id or "scenario",
                enable_emergency_priority=enable_emergency_priority,
            )

            init_state = env.start()
            prev_phase = init_state.current_phase
            peak_q = init_state.total_queue

            if broadcast_telemetry:
                with self._lock:
                    self._current_step = 0
                    self._simulation_time = init_state.simulation_time

            # Step simulation loop
            for step_num in range(1, duration + 1):
                if self._stop_event.is_set():
                    logger.info("Scenario stop event acknowledged at step %d", step_num)
                    break

                next_state = env.step()
                step_metrics = env.get_metrics()
                decision = env.get_latest_decision()
                peak_q = max(peak_q, next_state.total_queue)

                if broadcast_telemetry:
                    with self._lock:
                        self._current_step = step_num
                        self._simulation_time = next_state.simulation_time

                    snapshot = TelemetryService.create_snapshot(
                        state=next_state,
                        metrics=step_metrics,
                        controller=controller_inst,
                        simulation_id=self._scenario_id or "scenario",
                        peak_queue=peak_q,
                        agentic_decision=decision,
                    )

                    # Persist live snapshots & signal decisions
                    PersistenceService.save_traffic_snapshot(snapshot.model_dump())
                    if decision is not None:
                        if snapshot.prediction and snapshot.prediction.model_available:
                            decision.prediction = snapshot.prediction.model_dump()
                        PersistenceService.save_agentic_decision(decision.to_dict())
                    if snapshot.ai is not None:
                        PersistenceService.save_signal_decision(
                            simulation_id=self._scenario_id or "scenario",
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

                    # Broadcast live traffic update
                    self._broadcast_ws("traffic_update", snapshot.model_dump())

            agg_metrics = env.get_aggregate_metrics()
            ev_metrics = env.get_emergency_metrics()

        finally:
            if env is not None:
                try:
                    env.close()
                except Exception as c_err:
                    logger.warning("Error closing SUMO in scenario pass: %s", c_err)

        stats = controller_inst.get_stats()
        return agg_metrics, stats, ev_metrics


# Global ScenarioManager singleton
scenario_manager = ScenarioManager()
