"""Agentic Traffic Decision Engine.

Coordinates the complete 7-stage agentic workflow:
OBSERVE -> ANALYZE -> SELECT ACTION -> SAFETY VALIDATION -> EXECUTE -> EVALUATE -> RECORD.

Ensures grounded explainability across all controllers (Fixed-Time, Adaptive, DQN)
and guarantees strict signal transition safety enforcement via SignalSafetyManager.
"""

from __future__ import annotations

import collections
import logging
import threading
from typing import Any, Deque, Dict, List, Optional, Tuple

from simulation.agentic.models import (
    ActionName,
    AgenticDecisionRecord,
    CongestionLevel,
    ControllerType,
    DetectedConditions,
    ExecutionStatus,
    SafetyValidationStatus,
    TrafficObservation,
)
from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.base_controller import (
    BaseController,
    EmergencyPriorityEvaluator,
    SignalSafetyManager,
)
from simulation.controllers.dqn_controller import DQNController
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.state import TrafficState

logger = logging.getLogger(__name__)


class AgenticTrafficEngine:
    """Agentic decision engine governing traffic signal actuations and explainability.

    Executes the standard agentic loop:
    1. OBSERVE: Extract standardized observations from instantaneous traffic state.
    2. ANALYZE: Evaluate queue pressures, directional imbalance, and congestion levels.
    3. SELECT ACTION: Execute configured controller policy to determine desired green corridor.
    4. SAFETY VALIDATION: Enforce SignalSafetyManager state machine (min green, yellow clearance, max green).
    5. EXECUTE: Actuate the validated phase on TraCI without leaving intersection in an unsafe state.
    6. EVALUATE: Measure step performance deltas (queue change, delay change).
    7. RECORD: Store immutable decision record with grounded explanation for transparency.
    """

    MAX_HISTORY_ENTRIES = 500

    def __init__(
        self,
        controller: BaseController,
        safety_manager: Optional[SignalSafetyManager] = None,
        simulation_id: Optional[str] = None,
        enable_emergency_priority: bool = True,
    ) -> None:
        self.controller = controller
        self.safety_manager = safety_manager or controller.safety_manager or SignalSafetyManager()
        self.simulation_id = simulation_id
        self.enable_emergency_priority = enable_emergency_priority

        # Ensure controller references the unified safety manager
        self.controller.safety_manager = self.safety_manager

        self._lock = threading.RLock()
        self._last_decision: Optional[AgenticDecisionRecord] = None
        self._decision_history: Deque[AgenticDecisionRecord] = collections.deque(maxlen=self.MAX_HISTORY_ENTRIES)

        # Duplicate / re-entrancy tracking
        self._last_step_executed: Optional[int] = None
        self._last_time_executed: Optional[float] = None

    def set_controller(self, new_controller: BaseController) -> None:
        """Switch active controller while preserving the existing safety state machine."""
        with self._lock:
            # Preserve existing safety manager state across controller switch
            new_controller.safety_manager = self.safety_manager
            new_controller._last_applied_phase = self.controller._last_applied_phase
            new_controller.phase_change_count = self.controller.phase_change_count
            self.controller = new_controller
            logger.info("AgenticTrafficEngine switched controller to: %s", new_controller.name)

    def set_simulation_id(self, simulation_id: str) -> None:
        """Update active simulation ID reference."""
        with self._lock:
            self.simulation_id = simulation_id

    def reset(self) -> None:
        """Reset internal engine state and history."""
        with self._lock:
            self.safety_manager.reset()
            self.controller.reset()
            self.controller.safety_manager = self.safety_manager
            self._last_decision = None
            self._decision_history.clear()
            self._last_step_executed = None
            self._last_time_executed = None

    # ── STAGE 1: OBSERVE ─────────────────────────────────────────────────────

    def observe(
        self,
        state: TrafficState,
        metrics: Optional[Any] = None,
    ) -> TrafficObservation:
        """Stage 1: Construct standardized observation from current simulator state."""
        return TrafficObservation.from_traffic_state(
            state=state,
            controller_name=self.controller.name,
            simulation_id=self.simulation_id,
            safety_manager=self.safety_manager,
            metrics=metrics,
        )

    # ── STAGE 2: ANALYZE ─────────────────────────────────────────────────────

    def analyze(self, observation: TrafficObservation) -> DetectedConditions:
        """Stage 2: Evaluate directional pressures, congestion level, and constraints."""
        queues = observation.queue_length_by_approach
        ns_pressure = queues.get("north", 0) + queues.get("south", 0)
        ew_pressure = queues.get("east", 0) + queues.get("west", 0)
        imbalance = abs(ns_pressure - ew_pressure)

        if ns_pressure > ew_pressure:
            dominant = "NORTH_SOUTH"
        elif ew_pressure > ns_pressure:
            dominant = "EAST_WEST"
        else:
            dominant = "BALANCED"

        total_q = queues.get("total", ns_pressure + ew_pressure)
        if total_q == 0:
            congestion = CongestionLevel.FREE_FLOW.value
        elif total_q <= 5:
            congestion = CongestionLevel.LOW.value
        elif total_q <= 12:
            congestion = CongestionLevel.MODERATE.value
        elif total_q <= 24:
            congestion = CongestionLevel.HIGH.value
        else:
            congestion = CongestionLevel.SEVERE.value

        time_in_phase = observation.time_in_current_phase
        min_green_ok = time_in_phase >= self.safety_manager.min_green_seconds
        max_green_exceeded = time_in_phase >= self.safety_manager.max_green_seconds

        ev = observation.emergency_vehicle
        ev_detected = bool(
            ev.get("active")
            and ev.get("state") in {
                "APPROACHING",
                "INSIDE_JUNCTION",
                "DETECTED",
                "PRIORITY_REQUESTED",
                "PRIORITY_ACTIVE",
            }
        )
        ev_approach = ev.get("approach") if ev_detected else None

        in_yellow = (
            observation.is_in_transition
            or observation.current_signal_phase in {SignalSafetyManager.NS_YELLOW, SignalSafetyManager.EW_YELLOW}
        )

        return DetectedConditions(
            ns_pressure=ns_pressure,
            ew_pressure=ew_pressure,
            pressure_imbalance=imbalance,
            dominant_corridor=dominant,
            congestion_level=congestion,
            total_queue=total_q,
            average_speed=observation.mean_speed_by_approach.get("average", 0.0),
            total_waiting_time=observation.waiting_time_by_approach.get("total", 0.0),
            min_green_satisfied=min_green_ok,
            max_green_exceeded=max_green_exceeded,
            emergency_detected=ev_detected,
            emergency_approach=ev_approach,
            in_yellow_transition=in_yellow,
        )

    # ── STAGE 3: SELECT ACTION ───────────────────────────────────────────────

    def select_action(
        self,
        state: TrafficState,
        observation: TrafficObservation,
        conditions: DetectedConditions,
    ) -> Tuple[int, str, str, Optional[List[float]], Optional[float]]:
        """Stage 3: Query active controller policy and construct grounded explanation.

        Returns:
            Tuple: (requested_green_phase, requested_action, decision_reason, q_values, reward)
        """
        # 1. Emergency Vehicle Priority Override Check
        if self.enable_emergency_priority:
            ev_target_green, ev_decision = EmergencyPriorityEvaluator.evaluate(state, self.safety_manager)
            if ev_target_green is not None:
                action_name = ActionName.REQUEST_EMERGENCY_PRIORITY.value
                reason = ev_decision.get(
                    "reason",
                    f"Emergency vehicle {observation.emergency_vehicle.get('vehicle_id')} requested green corridor priority on {conditions.emergency_approach}."
                )
                return ev_target_green, action_name, reason, None, None

        # 2. Controller-Specific Decision & Grounded Rationale
        try:
            if isinstance(self.controller, FixedTimeController):
                return self._select_fixed_time_action(state, observation, conditions)
            elif isinstance(self.controller, AdaptiveController):
                return self._select_adaptive_action(state, observation, conditions)
            elif isinstance(self.controller, DQNController) or "dqn" in self.controller.name.lower():
                return self._select_dqn_action(state, observation, conditions)
            else:
                # Generic fallback for any other BaseController
                target_phase = self.controller.decide_target_phase(state)
                action_name = ActionName.KEEP.value if target_phase == self.safety_manager.current_phase else (
                    ActionName.REQUEST_NORTH_SOUTH.value if target_phase == SignalSafetyManager.NS_GREEN else ActionName.REQUEST_EAST_WEST.value
                )
                reason = f"Controller '{self.controller.name}' selected phase {target_phase} under its configured policy."
                return target_phase, action_name, reason, None, None

        except Exception as exc:
            logger.error("Error during controller action selection (%s): %s", self.controller.name, exc, exc_info=True)
            # Safe fallback: Maintain current green phase or current target
            safe_fallback = (
                self.safety_manager.current_phase
                if self.safety_manager.current_phase in SignalSafetyManager.GREEN_PHASES
                else self.safety_manager.target_green_phase
            )
            reason = f"Controller execution encountered exception ({exc}); falling back safely to current phase hold."
            return safe_fallback, ActionName.KEEP.value, reason, None, None

    def _select_fixed_time_action(
        self,
        state: TrafficState,
        observation: TrafficObservation,
        conditions: DetectedConditions,
    ) -> Tuple[int, str, str, Optional[List[float]], Optional[float]]:
        """Compute Fixed-Time cyclical timing decision and grounded explanation."""
        cfg = getattr(self.controller, "config", None)
        ns_duration = getattr(cfg, "ns_green_seconds", 30.0) if cfg else 30.0
        ew_duration = getattr(cfg, "ew_green_seconds", 30.0) if cfg else 30.0

        current_active = getattr(self.controller, "_active_green", SignalSafetyManager.NS_GREEN)
        target_duration = ns_duration if current_active == SignalSafetyManager.NS_GREEN else ew_duration

        # Advance controller timer
        target_phase = self.controller.decide_target_phase(state)
        elapsed = getattr(self.controller, "_elapsed_in_green", observation.time_in_current_phase)

        if target_phase != current_active:
            target_name = "North-South" if target_phase == SignalSafetyManager.NS_GREEN else "East-West"
            current_name = "North-South" if current_active == SignalSafetyManager.NS_GREEN else "East-West"
            action_name = ActionName.CYCLE_PHASE.value
            reason = (
                f"Fixed-Time cyclical schedule: {current_name} green window completed ({round(target_duration, 1)}s elapsed); "
                f"initiating scheduled cycle transition to {target_name} corridor."
            )
        else:
            corridor_name = "North-South" if target_phase == SignalSafetyManager.NS_GREEN else "East-West"
            action_name = ActionName.KEEP.value
            reason = (
                f"Fixed-Time cyclical schedule: holding {corridor_name} green corridor "
                f"({round(elapsed, 1)}s of {round(target_duration, 1)}s scheduled green elapsed)."
            )

        return target_phase, action_name, reason, None, None

    def _select_adaptive_action(
        self,
        state: TrafficState,
        observation: TrafficObservation,
        conditions: DetectedConditions,
    ) -> Tuple[int, str, str, Optional[List[float]], Optional[float]]:
        """Compute Rule-Based Adaptive decision based on queue pressure differentials."""
        cfg = getattr(self.controller, "config", None)
        threshold = getattr(cfg, "pressure_difference_threshold", 3) if cfg else 3
        max_green = getattr(cfg, "max_green_seconds", 60.0) if cfg else 60.0
        min_green = getattr(cfg, "min_green_seconds", 10.0) if cfg else 10.0

        current_phase = self.safety_manager.current_phase
        elapsed = self.safety_manager.time_in_current_phase

        ns_q = conditions.ns_pressure
        ew_q = conditions.ew_pressure
        ew_demand_dominant = (ew_q - ns_q) >= threshold
        ns_demand_dominant = (ns_q - ew_q) >= threshold
        max_green_reached = elapsed >= max_green

        if current_phase == SignalSafetyManager.NS_GREEN:
            if ew_demand_dominant or max_green_reached:
                target_phase = SignalSafetyManager.EW_GREEN
                action_name = ActionName.REQUEST_EAST_WEST.value
                if max_green_reached:
                    reason = (
                        f"Adaptive rule: North-South green duration reached maximum ceiling ({round(max_green, 1)}s); "
                        f"requesting switch to East-West corridor to prevent starvation."
                    )
                else:
                    diff = ew_q - ns_q
                    reason = (
                        f"Adaptive rule: East-West queue pressure ({ew_q}) exceeds North-South ({ns_q}) "
                        f"by {diff} vehicles (threshold: {threshold}); requesting transition to East-West corridor."
                    )
            else:
                target_phase = SignalSafetyManager.NS_GREEN
                action_name = ActionName.EXTEND_GREEN.value
                if elapsed < min_green:
                    time_left = min_green - elapsed
                    reason = f"Adaptive rule holding North-South green corridor: minimum green interval in progress ({round(time_left, 1)}s remaining)."
                else:
                    reason = (
                        f"Adaptive rule extending North-South green corridor: queue pressure balanced or favoring active green "
                        f"(NS_Q={ns_q}, EW_Q={ew_q}, differential < threshold {threshold})."
                    )

        elif current_phase == SignalSafetyManager.EW_GREEN:
            if ns_demand_dominant or max_green_reached:
                target_phase = SignalSafetyManager.NS_GREEN
                action_name = ActionName.REQUEST_NORTH_SOUTH.value
                if max_green_reached:
                    reason = (
                        f"Adaptive rule: East-West green duration reached maximum ceiling ({round(max_green, 1)}s); "
                        f"requesting switch to North-South corridor to prevent starvation."
                    )
                else:
                    diff = ns_q - ew_q
                    reason = (
                        f"Adaptive rule: North-South queue pressure ({ns_q}) exceeds East-West ({ew_q}) "
                        f"by {diff} vehicles (threshold: {threshold}); requesting transition to North-South corridor."
                    )
            else:
                target_phase = SignalSafetyManager.EW_GREEN
                action_name = ActionName.EXTEND_GREEN.value
                if elapsed < min_green:
                    time_left = min_green - elapsed
                    reason = f"Adaptive rule holding East-West green corridor: minimum green interval in progress ({round(time_left, 1)}s remaining)."
                else:
                    reason = (
                        f"Adaptive rule extending East-West green corridor: queue pressure balanced or favoring active green "
                        f"(NS_Q={ns_q}, EW_Q={ew_q}, differential < threshold {threshold})."
                    )

        else:
            # During transition phase
            target_phase = self.safety_manager.target_green_phase
            action_name = ActionName.KEEP.value
            reason = "Adaptive controller awaiting yellow clearance completion before evaluating next green interval."

        # Keep internal controller state synchronized
        self.controller._active_green = target_phase
        self.controller._last_ns_pressure = ns_q
        self.controller._last_ew_pressure = ew_q

        return target_phase, action_name, reason, None, None

    def _select_dqn_action(
        self,
        state: TrafficState,
        observation: TrafficObservation,
        conditions: DetectedConditions,
    ) -> Tuple[int, str, str, Optional[List[float]], Optional[float]]:
        """Compute DQN greedy policy inference and include observed Q-values as supporting context."""
        target_phase = self.controller.decide_target_phase(state)
        stats = self.controller.get_stats()

        action_name = stats.get("last_action_name", "KEEP")
        q_values: List[float] = stats.get("q_values", [])
        reward = stats.get("reward")

        # Map to standardized action name
        if action_name == "REQUEST_NS" or action_name == "SWITCH_NS":
            std_action = ActionName.REQUEST_NORTH_SOUTH.value
        elif action_name == "REQUEST_EW" or action_name == "SWITCH_EW":
            std_action = ActionName.REQUEST_EAST_WEST.value
        else:
            std_action = ActionName.KEEP.value

        reason = (
            f"DQN policy network selected action {std_action} under observed traffic state "
            f"(NS_Q={conditions.ns_pressure}, EW_Q={conditions.ew_pressure}, total_queue={conditions.total_queue})."
        )

        if isinstance(q_values, (list, tuple)) and len(q_values) == 3:
            q_formatted = f"[KEEP={q_values[0]:.2f}, REQ_NS={q_values[1]:.2f}, REQ_EW={q_values[2]:.2f}]"
            reason += f" Evaluated Q-values (expected cumulative return): {q_formatted}."

        return target_phase, std_action, reason, q_values, reward

    # ── STAGE 4: SAFETY VALIDATION ───────────────────────────────────────────

    def validate_safety(
        self,
        requested_green_phase: int,
        requested_action: str,
        state: TrafficState,
        step_length: float = 1.0,
    ) -> Tuple[int, str, str, str]:
        """Stage 4: Route requested green phase through SignalSafetyManager.

        Returns:
            Tuple: (validated_phase, validated_action, safety_status, safety_reason)
        """
        curr_phase = self.safety_manager.current_phase
        time_in_phase = self.safety_manager.time_in_current_phase
        min_green = self.safety_manager.min_green_seconds
        max_green = self.safety_manager.max_green_seconds

        is_emergency = (requested_action == ActionName.REQUEST_EMERGENCY_PRIORITY.value)

        # 1. Already in mandatory yellow clearance
        if self.safety_manager.is_in_transition:
            validated_phase = self.safety_manager.step(requested_green_phase, step_length=step_length, is_emergency=is_emergency)
            remaining = max(0.0, self.safety_manager.transition_time_remaining)
            validated_action = SafetyValidationStatus.IN_YELLOW_CLEARANCE.value
            safety_status = "IN_YELLOW_CLEARANCE"
            safety_reason = (
                f"Safety Manager enforcing mandatory yellow clearance interval "
                f"({round(remaining, 1)}s remaining before green transition). Conflicting green switch deferred."
            )
            return validated_phase, validated_action, safety_status, safety_reason

        # 2. Controller requests conflicting green corridor change
        wants_change = (requested_green_phase != curr_phase)
        if wants_change:
            if time_in_phase < min_green:
                # Minimum green violated: Defer transition
                time_left = min_green - time_in_phase
                validated_phase = self.safety_manager.step(requested_green_phase, step_length=step_length, is_emergency=is_emergency)
                validated_action = SafetyValidationStatus.RESTRICTED_MIN_GREEN.value
                safety_status = "HOLD_MIN_GREEN"
                safety_reason = (
                    f"Safety Manager enforcing minimum green constraint: phase change deferred "
                    f"({round(time_left, 1)}s remaining of {round(min_green, 1)}s minimum green)."
                )
                return validated_phase, validated_action, safety_status, safety_reason
            else:
                # Safe to transition
                validated_phase = self.safety_manager.step(requested_green_phase, step_length=step_length, is_emergency=is_emergency)
                validated_action = SafetyValidationStatus.APPROVED.value
                safety_status = "SAFE"
                safety_reason = (
                    "Safety Manager approved requested green corridor switch: "
                    "minimum green satisfied; initiating safe yellow clearance."
                )
                return validated_phase, validated_action, safety_status, safety_reason

        # 3. Controller requests holding active green
        if time_in_phase >= max_green and not is_emergency:
            # Maximum green ceiling exceeded: force safe yellow transition to prevent starvation
            validated_phase = self.safety_manager.step(requested_green_phase, step_length=step_length, is_emergency=is_emergency)
            validated_action = SafetyValidationStatus.OVERRIDE_MAX_GREEN.value
            safety_status = "MAX_GREEN_EXCEEDED"
            safety_reason = (
                f"Safety Manager enforcing maximum green ceiling ({round(max_green, 1)}s); "
                f"initiated phase transition to prevent conflicting corridor starvation."
            )
            return validated_phase, validated_action, safety_status, safety_reason
        else:
            # Steady green corridor hold approved
            validated_phase = self.safety_manager.step(requested_green_phase, step_length=step_length, is_emergency=is_emergency)
            validated_action = SafetyValidationStatus.APPROVED.value
            safety_status = "PRIORITY_GRANTED" if is_emergency else "SAFE"
            safety_reason = (
                "Safety Manager approved priority hold: active emergency green corridor maintained."
                if is_emergency
                else "Safety Manager approved action: active green corridor maintained within safety parameters."
            )
            return validated_phase, validated_action, safety_status, safety_reason

    # ── STAGE 5: EXECUTE ─────────────────────────────────────────────────────

    def execute(self, validated_phase: int, traci_controller: Any) -> str:
        """Stage 5: Actuate validated phase on TraCI and record phase tracking.

        Returns:
            str: ExecutionStatus string.
        """
        try:
            # Check if simulation is running
            if hasattr(traci_controller, "is_running") and not traci_controller.is_running():
                logger.debug("TraCI is closed; execution marked SAFE_SHUTDOWN.")
                return ExecutionStatus.SAFE_SHUTDOWN.value

            # Track controller phase changes
            if (
                self.controller._last_applied_phase is not None
                and validated_phase != self.controller._last_applied_phase
            ):
                self.controller.phase_change_count += 1

            self.controller._last_applied_phase = validated_phase

            # Actuate phase directly on TraCI
            traci_controller.set_tls_phase(validated_phase)
            return ExecutionStatus.EXECUTED.value

        except Exception as exc:
            logger.warning("TraCI phase actuation failed or simulation closing: %s", exc)
            return ExecutionStatus.FAILED.value

    # ── STAGE 6: EVALUATE ────────────────────────────────────────────────────

    def evaluate(
        self,
        prev_decision: Optional[AgenticDecisionRecord],
        current_state: TrafficState,
        step_metrics: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Stage 6: Compute measured outcome deltas from the previous control step."""
        if prev_decision is None:
            return {
                "status": "INITIAL_STEP",
                "queue_delta": 0,
                "waiting_time_delta": 0.0,
                "current_total_queue": getattr(current_state, "total_queue", 0),
            }

        prev_q = prev_decision.observation.queue_length_by_approach.get("total", 0)
        curr_q = getattr(current_state, "total_queue", 0)
        q_delta = curr_q - prev_q

        prev_wait = prev_decision.observation.waiting_time_by_approach.get("total", 0.0)
        curr_wait = getattr(current_state, "total_waiting_time", 0.0)
        wait_delta = round(curr_wait - prev_wait, 2)

        throughput = getattr(step_metrics, "throughput", None) if step_metrics else None

        return {
            "status": "EVALUATED",
            "queue_delta": q_delta,
            "waiting_time_delta": wait_delta,
            "step_throughput": throughput,
            "current_total_queue": curr_q,
            "current_avg_speed": round(float(getattr(current_state, "average_speed", 0.0)), 2),
        }

    # ── STAGE 7: RECORD ──────────────────────────────────────────────────────

    def record(self, decision: AgenticDecisionRecord) -> None:
        """Stage 7: Store immutable decision record in memory and persistence service."""
        with self._lock:
            self._last_decision = decision
            self._decision_history.append(decision)

    # ── UNIFIED ORCHESTRATION ────────────────────────────────────────────────

    def step(
        self,
        state: TrafficState,
        traci_controller: Any,
        step_metrics: Optional[Any] = None,
    ) -> Tuple[int, AgenticDecisionRecord]:
        """Execute the complete 7-stage agentic workflow synchronously with failure isolation.

        Returns:
            Tuple[int, AgenticDecisionRecord]: (actuated_safe_phase, decision_record)
        """
        with self._lock:
            curr_step = getattr(state, "step", 0)
            curr_time = getattr(state, "simulation_time", 0.0)

            # Prevent duplicate / concurrent decisions for the same simulation step
            if (
                self._last_step_executed is not None
                and self._last_step_executed == curr_step
                and self._last_time_executed == curr_time
                and self._last_decision is not None
            ):
                return self._last_decision.validated_phase, self._last_decision

            # 1. OBSERVE
            observation = self.observe(state, metrics=step_metrics)

            # 2. ANALYZE
            conditions = self.analyze(observation)

            # 3. SELECT ACTION
            req_phase, req_action, dec_reason, q_vals, reward = self.select_action(
                state=state,
                observation=observation,
                conditions=conditions,
            )

            # Propagate emergency priority attributes back to state if applicable
            if state.emergency and state.emergency.active:
                state.emergency.priority_requested = (req_action == ActionName.REQUEST_EMERGENCY_PRIORITY.value)

            # 4. SAFETY VALIDATION
            step_len = getattr(traci_controller, "step_length", 1.0)
            val_phase, val_action, safe_status, safe_reason = self.validate_safety(
                requested_green_phase=req_phase,
                requested_action=req_action,
                state=state,
                step_length=step_len,
            )

            # 5. EXECUTE
            exec_status = self.execute(val_phase, traci_controller)

            # Inform emergency tracker of priority status
            if req_action == ActionName.REQUEST_EMERGENCY_PRIORITY.value:
                if val_phase == req_phase and not self.safety_manager.is_in_transition:
                    if hasattr(traci_controller, "notify_emergency_priority_active"):
                        traci_controller.notify_emergency_priority_active(curr_time)
                else:
                    if hasattr(traci_controller, "notify_emergency_priority_requested"):
                        traci_controller.notify_emergency_priority_requested(curr_time)

            # 6. EVALUATE
            post_metrics = self.evaluate(
                prev_decision=self._last_decision,
                current_state=state,
                step_metrics=step_metrics,
            )

            # Determine whether SignalSafetyManager overrode or restricted the proposed action
            is_override = (
                val_action in {
                    SafetyValidationStatus.RESTRICTED_MIN_GREEN.value,
                    SafetyValidationStatus.OVERRIDE_MAX_GREEN.value,
                    SafetyValidationStatus.IN_YELLOW_CLEARANCE.value,
                }
                or (val_phase != req_phase and val_action != SafetyValidationStatus.APPROVED.value)
                or (safe_status in {"HOLD_MIN_GREEN", "MAX_GREEN_EXCEEDED", "IN_YELLOW_CLEARANCE"})
            )

            # Grounded emergency vehicle context
            ev_data: Optional[Dict[str, Any]] = None
            if state.emergency and getattr(state.emergency, "active", False):
                ev_data = {
                    "active": True,
                    "vehicle_id": getattr(state.emergency, "vehicle_id", None),
                    "vehicle_type": getattr(state.emergency, "vehicle_type", "emergency"),
                    "approach": getattr(state.emergency, "approach", None),
                    "state": getattr(state.emergency, "state", "IDLE"),
                    "distance": getattr(state.emergency, "distance", None),
                    "speed": getattr(state.emergency, "speed", None),
                    "priority_requested": getattr(state.emergency, "priority_requested", False),
                    "priority_approved": getattr(state.emergency, "priority_approved", False),
                    "priority_active": getattr(state.emergency, "priority_active", False),
                    "safety_status": getattr(state.emergency, "safety_status", "NORMAL"),
                }

            # Grounded predictive intelligence context
            pred_data: Optional[Dict[str, Any]] = None
            if hasattr(state, "prediction") and state.prediction:
                pred_data = state.prediction if isinstance(state.prediction, dict) else (
                    state.prediction.to_dict() if hasattr(state.prediction, "to_dict") else None
                )

            # 7. RECORD
            decision = AgenticDecisionRecord(
                simulation_id=self.simulation_id,
                simulation_time=curr_time,
                step=curr_step,
                controller=self.controller.name,
                observation=observation,
                detected_conditions=conditions,
                requested_action=req_action,
                requested_phase=req_phase,
                validated_action=val_action,
                validated_phase=val_phase,
                is_safety_override=is_override,
                safety_status=safe_status,
                safety_reason=safe_reason,
                decision_reason=dec_reason,
                execution_status=exec_status,
                q_values=q_vals,
                reward=reward,
                prediction=pred_data,
                emergency=ev_data,
                post_action_metrics=post_metrics,
            )

            self.record(decision)
            self._last_step_executed = curr_step
            self._last_time_executed = curr_time

            return val_phase, decision

    def attach_prediction(self, prediction_dict: Optional[Dict[str, Any]]) -> None:
        """Attach verified prediction metrics or live forecast to the latest decision record."""
        with self._lock:
            if self._last_decision is not None and prediction_dict is not None:
                self._last_decision.prediction = prediction_dict

    def get_latest_decision(self) -> Optional[AgenticDecisionRecord]:
        """Retrieve most recently computed decision record."""
        with self._lock:
            return self._last_decision

    def get_decision_history(self, limit: int = 50) -> List[AgenticDecisionRecord]:
        """Retrieve recent decision records in chronological order."""
        with self._lock:
            history_list = list(self._decision_history)
            return history_list[-limit:] if limit > 0 else history_list

    def shutdown(self) -> None:
        """Gracefully release resources on simulation termination."""
        with self._lock:
            logger.debug("AgenticTrafficEngine shutdown requested.")
