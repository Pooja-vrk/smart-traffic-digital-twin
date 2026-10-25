"""Unit and integration tests for AgenticTrafficEngine and standardized models.

Covers:
1. Valid observations and missing measurements.
2. Decision record validation and JSON serialization.
3. Fixed-Time decision explanation and phase cycling.
4. Adaptive decision explanation and queue pressure differentials.
5. DQN decision explanation and un-hallucinated Q-values.
6. Safety manager approval, minimum green restriction, and yellow clearance.
7. Separation of requested, validated, and executed actions.
8. Evaluation when post-action metrics are pending/unavailable.
9. Controller exceptions and safe shutdown handling.
10. Prevention of duplicate or concurrent decisions.
11. Controller switching and emergency vehicle priority.
12. Headless integration with TrafficSimulationEnvironment.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from simulation.agentic.engine import AgenticTrafficEngine
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
from simulation.config import AdaptiveConfig, FixedTimeConfig
from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.base_controller import (
    BaseController,
    EmergencyPriorityEvaluator,
    SignalSafetyManager,
)
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.environment import TrafficSimulationEnvironment
from simulation.state import ApproachState, EmergencyVehicleState, TrafficState


class DummyTraCI:
    """Mock TraCI controller for isolated unit testing."""

    def __init__(self, step_length: float = 1.0) -> None:
        self.step_length = step_length
        self.applied_phases: List[int] = []
        self._running = True

    def set_tls_phase(self, phase: int) -> None:
        self.applied_phases.append(phase)

    def is_running(self) -> bool:
        return self._running


# ── 1. OBSERVATION TESTS ─────────────────────────────────────────────────────

def test_observation_valid_full_state():
    """Verify TrafficObservation builds correctly with complete TrafficState telemetry."""
    state = TrafficState(
        simulation_time=12.5,
        step=12,
        total_vehicles=8,
        total_queue=5,
        total_waiting_time=24.0,
        average_speed=7.2,
        current_phase=0,
        current_phase_name="NS_GREEN",
        time_since_phase_change=12.5,
    )
    state.north.queue_length = 3
    state.north.waiting_time = 15.0
    state.south.queue_length = 2
    state.south.waiting_time = 9.0
    state.east.queue_length = 0
    state.west.queue_length = 0

    obs = TrafficObservation.from_traffic_state(state, controller_name="Fixed-Time", simulation_id="sim-001")
    assert obs.simulation_time == 12.5
    assert obs.step == 12
    assert obs.simulation_id == "sim-001"
    assert obs.controller == "Fixed-Time"
    assert obs.queue_length_by_approach["north"] == 3
    assert obs.queue_length_by_approach["south"] == 2
    assert obs.queue_length_by_approach["total"] == 5
    assert obs.waiting_time_by_approach["north"] == 15.0
    assert obs.vehicle_counts["total"] == 8
    assert obs.measurements_available is True
    assert len(obs.unavailable_fields) == 0


def test_observation_missing_and_partial_measurements():
    """Verify TrafficObservation handles missing or None fields gracefully without raising exceptions."""
    # TrafficState with missing approach attributes
    state = MagicMock(spec=TrafficState)
    state.simulation_time = 5.0
    state.step = 5
    state.total_vehicles = 0
    state.total_queue = 0
    state.total_waiting_time = 0.0
    state.average_speed = 0.0
    state.current_phase = 0
    state.current_phase_name = "NS_GREEN"
    state.time_since_phase_change = 5.0
    state.north = None
    state.south = None
    state.east = None
    state.west = None
    state.emergency = None

    obs = TrafficObservation.from_traffic_state(state, controller_name="Adaptive")
    assert obs.measurements_available is False
    assert "queue_north" in obs.unavailable_fields
    assert obs.queue_length_by_approach["north"] == 0
    assert obs.queue_length_by_approach["total"] == 0
    assert obs.emergency_vehicle["active"] is False


# ── 2. DECISION RECORD SERIALIZATION TESTS ───────────────────────────────────

def test_decision_record_validation_and_serialization():
    """Verify AgenticDecisionRecord contains all required attributes and serializes cleanly to JSON."""
    obs = TrafficObservation(simulation_time=10.0, step=10, controller="Fixed-Time")
    conds = DetectedConditions(ns_pressure=4, ew_pressure=1, congestion_level=CongestionLevel.LOW.value)

    record = AgenticDecisionRecord(
        simulation_id="sim-test-123",
        simulation_time=10.0,
        step=10,
        controller="Fixed-Time",
        observation=obs,
        detected_conditions=conds,
        requested_action=ActionName.KEEP.value,
        requested_phase=0,
        validated_action=SafetyValidationStatus.APPROVED.value,
        validated_phase=0,
        safety_status="SAFE",
        safety_reason="Approved: minimum green satisfied.",
        decision_reason="Holding North-South green corridor.",
        execution_status=ExecutionStatus.EXECUTED.value,
        q_values=None,
        reward=None,
        post_action_metrics={"queue_delta": -1},
    )

    doc = record.to_dict()
    assert isinstance(doc, dict)
    assert doc["simulation_id"] == "sim-test-123"
    assert doc["requested_action"] == "KEEP"
    assert doc["validated_action"] == "APPROVED"
    assert doc["safety_status"] == "SAFE"
    assert doc["execution_status"] == "EXECUTED"

    # Verify JSON serialization does not error
    json_str = json.dumps(doc)
    assert "sim-test-123" in json_str
    assert "Holding North-South green corridor." in json_str


# ── 3. FIXED-TIME DECISION EXPLANATIONS ──────────────────────────────────────

def test_fixed_time_decision_explanation():
    """Verify FixedTimeController produces grounded explanations for green hold and scheduled phase cycling."""
    controller = FixedTimeController(
        config=FixedTimeConfig(ns_green_seconds=20.0, ew_green_seconds=20.0, ns_yellow_seconds=3.0, ew_yellow_seconds=3.0)
    )
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    state = TrafficState(simulation_time=5.0, step=5, current_phase=0, time_since_phase_change=5.0)

    # 1. During green interval: holding explanation
    phase, decision = engine.step(state, traci)
    assert phase == SignalSafetyManager.NS_GREEN
    assert decision.requested_action == ActionName.KEEP.value
    assert "Fixed-Time cyclical schedule: holding North-South green corridor" in decision.decision_reason
    assert decision.validated_action == SafetyValidationStatus.APPROVED.value

    # 2. Advance controller timer until cycle threshold (20s)
    controller._elapsed_in_green = 20.0
    state.time_since_phase_change = 20.0
    state.step = 20
    state.simulation_time = 20.0

    phase, decision_cycle = engine.step(state, traci)
    assert decision_cycle.requested_action == ActionName.CYCLE_PHASE.value
    assert decision_cycle.requested_phase == SignalSafetyManager.EW_GREEN
    assert "green window completed" in decision_cycle.decision_reason
    assert "initiating scheduled cycle transition to East-West corridor" in decision_cycle.decision_reason


# ── 4. ADAPTIVE DECISION EXPLANATIONS ────────────────────────────────────────

def test_adaptive_decision_explanation_pressure_imbalance():
    """Verify AdaptiveController explains queue differential triggers grounded in observed counts."""
    controller = AdaptiveController(
        config=AdaptiveConfig(min_green_seconds=10.0, max_green_seconds=30.0, pressure_difference_threshold=3)
    )
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    # Step past min green with heavy East-West traffic
    state = TrafficState(simulation_time=12.0, step=12, current_phase=0, time_since_phase_change=12.0)
    state.north.queue_length = 1
    state.south.queue_length = 1
    state.east.queue_length = 8
    state.west.queue_length = 4
    state.total_queue = 14

    # Satisfy elapsed green time in safety manager
    engine.safety_manager.time_in_current_phase = 12.0

    phase, decision = engine.step(state, traci)
    assert decision.requested_action == ActionName.REQUEST_EAST_WEST.value
    assert decision.requested_phase == SignalSafetyManager.EW_GREEN
    assert "East-West queue pressure (12) exceeds North-South (2) by 10 vehicles" in decision.decision_reason
    assert "threshold: 3" in decision.decision_reason


def test_adaptive_decision_explanation_max_green():
    """Verify AdaptiveController explains maximum green ceiling enforcement."""
    controller = AdaptiveController(
        config=AdaptiveConfig(min_green_seconds=10.0, max_green_seconds=30.0, pressure_difference_threshold=5)
    )
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    # Balanced traffic, but elapsed time reached 30s
    state = TrafficState(simulation_time=30.0, step=30, current_phase=0, time_since_phase_change=30.0)
    state.north.queue_length = 5
    state.south.queue_length = 5
    state.east.queue_length = 5
    state.west.queue_length = 5
    engine.safety_manager.time_in_current_phase = 30.0

    phase, decision = engine.step(state, traci)
    assert decision.requested_action == ActionName.REQUEST_EAST_WEST.value
    assert "reached maximum ceiling (30.0s)" in decision.decision_reason


# ── 5. DQN DECISION EXPLANATIONS & Q-VALUES ──────────────────────────────────

def test_dqn_decision_explanation_and_q_values():
    """Verify DQN controller explanations include un-hallucinated Q-values without probability claims."""
    mock_dqn = MagicMock(spec=BaseController)
    mock_dqn.name = "DQN-ReinforcementLearning"
    mock_dqn._last_applied_phase = None
    mock_dqn.phase_change_count = 0
    mock_dqn.decide_target_phase.return_value = SignalSafetyManager.EW_GREEN
    mock_dqn.get_stats.return_value = {
        "last_action_name": "SWITCH_EW",
        "last_selected_action": 2,
        "q_values": [-1.25, -2.10, 3.45],
        "reward": -0.85,
    }

    safety_mgr = SignalSafetyManager(min_green_seconds=5.0)
    safety_mgr.time_in_current_phase = 6.0  # Min green met
    engine = AgenticTrafficEngine(controller=mock_dqn, safety_manager=safety_mgr)
    traci = DummyTraCI()

    state = TrafficState(simulation_time=8.0, step=8, current_phase=0, time_since_phase_change=6.0)
    state.north.queue_length = 2
    state.south.queue_length = 1
    state.east.queue_length = 6
    state.west.queue_length = 4
    state.total_queue = 13

    phase, decision = engine.step(state, traci)
    assert decision.requested_action == ActionName.REQUEST_EAST_WEST.value
    assert decision.q_values == [-1.25, -2.10, 3.45]
    assert decision.reward == -0.85
    assert "DQN policy network selected action REQUEST_EAST_WEST" in decision.decision_reason
    assert "Evaluated Q-values (expected cumulative return): [KEEP=-1.25, REQ_NS=-2.10, REQ_EW=3.45]" in decision.decision_reason
    assert "probability" not in decision.decision_reason.lower()


# ── 6. SAFETY VALIDATION APPROVAL AND RESTRICTION ────────────────────────────

def test_safety_restriction_before_minimum_green():
    """Verify SignalSafetyManager defers phase change requests before minimum green expires."""
    controller = FixedTimeController(
        config=FixedTimeConfig(ns_green_seconds=15.0, ew_green_seconds=15.0)
    )
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    engine.safety_manager.current_phase = SignalSafetyManager.NS_GREEN
    engine.safety_manager.time_in_current_phase = 4.0  # Only 4s elapsed out of 15s

    state = TrafficState(simulation_time=4.0, step=4, current_phase=0, time_since_phase_change=4.0)

    # Force controller to want EW_GREEN prematurely
    controller._active_green = SignalSafetyManager.EW_GREEN

    phase, decision = engine.step(state, traci)

    # Controller wanted EW_GREEN, but Safety Manager restricted it to maintain NS_GREEN
    assert decision.requested_phase == SignalSafetyManager.EW_GREEN
    assert decision.validated_phase == SignalSafetyManager.NS_GREEN
    assert decision.validated_action == SafetyValidationStatus.RESTRICTED_MIN_GREEN.value
    assert decision.safety_status == "HOLD_MIN_GREEN"
    assert "phase change deferred" in decision.safety_reason
    assert "minimum green" in decision.safety_reason
    assert phase == SignalSafetyManager.NS_GREEN


def test_safety_enforcement_during_yellow_clearance():
    """Verify SignalSafetyManager guarantees yellow transition completion before granting conflicting green."""
    controller = FixedTimeController()
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    # Place safety manager in active transition
    engine.safety_manager.current_phase = SignalSafetyManager.NS_YELLOW
    engine.safety_manager.is_in_transition = True
    engine.safety_manager.target_green_phase = SignalSafetyManager.EW_GREEN
    engine.safety_manager.transition_time_remaining = 2.0

    state = TrafficState(simulation_time=22.0, step=22, current_phase=1, time_since_phase_change=1.0)

    phase, decision = engine.step(state, traci)
    assert decision.validated_action == SafetyValidationStatus.IN_YELLOW_CLEARANCE.value
    assert decision.safety_status == "IN_YELLOW_CLEARANCE"
    assert "mandatory yellow clearance" in decision.safety_reason
    assert phase == SignalSafetyManager.NS_YELLOW


# ── 7. SEPARATION OF REQUESTED, VALIDATED, AND EXECUTED ACTIONS ──────────────

def test_separation_of_actions_under_safety_override():
    """Verify controller request, safety validation, and execution status are clearly distinguished."""
    controller = AdaptiveController()
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    # Pre-condition: only 2s elapsed, min green is 10s
    engine.safety_manager.time_in_current_phase = 2.0
    state = TrafficState(simulation_time=2.0, step=2, current_phase=0, time_since_phase_change=2.0)
    # Huge EW surge
    state.east.queue_length = 15
    state.west.queue_length = 10

    phase, decision = engine.step(state, traci)

    # 1. Requested: What controller desired
    assert decision.requested_action == ActionName.REQUEST_EAST_WEST.value
    assert decision.requested_phase == SignalSafetyManager.EW_GREEN

    # 2. Validated: What safety manager allowed
    assert decision.validated_action == SafetyValidationStatus.RESTRICTED_MIN_GREEN.value
    assert decision.validated_phase == SignalSafetyManager.NS_GREEN

    # 3. Executed: What was applied to simulator
    assert decision.execution_status == ExecutionStatus.EXECUTED.value
    assert traci.applied_phases[-1] == SignalSafetyManager.NS_GREEN


# ── 8. POST-ACTION METRIC EVALUATION ─────────────────────────────────────────

def test_evaluation_when_metrics_available_and_pending():
    """Verify evaluation delta computation and initial-step pending status."""
    controller = FixedTimeController()
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    # Step 1: Initial step -> status should be INITIAL_STEP
    s1 = TrafficState(simulation_time=1.0, step=1, total_queue=6, total_waiting_time=10.0)
    _, d1 = engine.step(s1, traci)
    assert d1.post_action_metrics is not None
    assert d1.post_action_metrics["status"] == "INITIAL_STEP"

    # Step 2: Queue grows to 9, waiting time grows to 18.0
    s2 = TrafficState(simulation_time=2.0, step=2, total_queue=9, total_waiting_time=18.0)
    _, d2 = engine.step(s2, traci)
    assert d2.post_action_metrics["status"] == "EVALUATED"
    assert d2.post_action_metrics["queue_delta"] == 3  # 9 - 6
    assert d2.post_action_metrics["waiting_time_delta"] == 8.0  # 18.0 - 10.0


# ── 9. CONTROLLER EXCEPTIONS AND SAFE SHUTDOWN ───────────────────────────────

def test_controller_exception_triggers_safe_fallback():
    """Verify engine catches controller exceptions and falls back safely without leaving unsafe signals."""
    faulty_controller = MagicMock(spec=BaseController)
    faulty_controller.name = "FaultyController"
    faulty_controller._last_applied_phase = None
    faulty_controller.phase_change_count = 0
    faulty_controller.decide_target_phase.side_effect = RuntimeError("Inference tensor shape mismatch")

    safety_mgr = SignalSafetyManager()
    engine = AgenticTrafficEngine(controller=faulty_controller, safety_manager=safety_mgr)
    traci = DummyTraCI()

    state = TrafficState(simulation_time=10.0, step=10, current_phase=0)

    # Should not raise exception
    phase, decision = engine.step(state, traci)
    assert phase in SignalSafetyManager.GREEN_PHASES
    assert "falling back safely" in decision.decision_reason
    assert traci.applied_phases[-1] == phase


def test_closed_traci_marked_safe_shutdown():
    """Verify closed TraCI simulation marks execution as SAFE_SHUTDOWN gracefully."""
    controller = FixedTimeController()
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()
    traci._running = False  # Simulation closed

    state = TrafficState(simulation_time=10.0, step=10, current_phase=0)
    phase, decision = engine.step(state, traci)
    assert decision.execution_status == ExecutionStatus.SAFE_SHUTDOWN.value


# ── 10. PREVENTION OF DUPLICATE / CONCURRENT DECISIONS ───────────────────────

def test_duplicate_decision_prevention():
    """Verify calling engine.step with identical step/time returns cached decision without double execution."""
    controller = FixedTimeController()
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    state = TrafficState(simulation_time=15.0, step=15, current_phase=0)

    phase1, d1 = engine.step(state, traci)
    initial_call_count = len(traci.applied_phases)

    # Call again with exact same step and time
    phase2, d2 = engine.step(state, traci)

    assert phase1 == phase2
    assert d1.decision_id == d2.decision_id
    assert len(traci.applied_phases) == initial_call_count  # Did not actuate again


def test_concurrent_threads_decision_safety():
    """Verify engine lock serializes concurrent callers without corrupted internal state."""
    controller = FixedTimeController()
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    results = []

    def worker(step_idx: int):
        s = TrafficState(simulation_time=float(step_idx), step=step_idx, current_phase=0)
        p, d = engine.step(s, traci)
        results.append((step_idx, p, d.decision_id))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 11)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    history = engine.get_decision_history()
    assert len(history) == 10


# ── 11. CONTROLLER SWITCHING AND EMERGENCY PRIORITY ──────────────────────────

def test_controller_switching_preserves_safety_manager_state():
    """Verify switching controller mid-simulation preserves elapsed time and active phase."""
    c1 = FixedTimeController(config=FixedTimeConfig(ns_green_seconds=20.0))
    engine = AgenticTrafficEngine(controller=c1)
    traci = DummyTraCI()

    # Advance 8s in c1
    for step in range(1, 9):
        state = TrafficState(simulation_time=float(step), step=step, current_phase=0)
        engine.step(state, traci)

    assert engine.safety_manager.time_in_current_phase == 8.0

    # Switch to Adaptive controller
    c2 = AdaptiveController(config=AdaptiveConfig(min_green_seconds=10.0))
    engine.set_controller(c2)

    # Verify safety manager was NOT reset to 0
    assert engine.safety_manager.time_in_current_phase == 8.0
    assert engine.controller.name == "Rule-Based Adaptive"

    # Step at step 9
    state9 = TrafficState(simulation_time=9.0, step=9, current_phase=0)
    engine.step(state9, traci)
    assert engine.safety_manager.time_in_current_phase == 9.0


def test_emergency_vehicle_priority_request_and_preemption():
    """Verify approaching emergency vehicle requests corridor green priority safely."""
    controller = FixedTimeController(config=FixedTimeConfig(ns_green_seconds=10.0, ns_yellow_seconds=3.0))
    engine = AgenticTrafficEngine(controller=controller)
    traci = DummyTraCI()

    # Pre-condition: East approach has emergency vehicle approaching, min green satisfied (15s >= 10s)
    engine.safety_manager.current_phase = SignalSafetyManager.NS_GREEN
    engine.safety_manager.time_in_current_phase = 15.0

    ev = EmergencyVehicleState(
        active=True,
        vehicle_id="EV_01",
        vehicle_type="emergency",
        approach="east",
        state="APPROACHING",
        distance=120.0,
        speed=16.5,
    )
    state = TrafficState(simulation_time=15.0, step=15, current_phase=0, emergency=ev)

    phase, decision = engine.step(state, traci)

    assert decision.requested_action == ActionName.REQUEST_EMERGENCY_PRIORITY.value
    assert decision.requested_phase == SignalSafetyManager.EW_GREEN
    assert "Emergency vehicle" in decision.decision_reason
    # Safety manager initiates safe yellow transition to EW_GREEN
    assert decision.validated_phase == SignalSafetyManager.NS_YELLOW
    assert decision.validated_action == SafetyValidationStatus.APPROVED.value


# ── 12. HEADLESS INTEGRATION WITH SIMULATION ENVIRONMENT ─────────────────────

def test_headless_engine_integration_with_environment():
    """Verify TrafficSimulationEnvironment coordinates with AgenticTrafficEngine seamlessly in SUMO."""
    controller = FixedTimeController(
        config=FixedTimeConfig(ns_green_seconds=10.0, ns_yellow_seconds=3.0, ew_green_seconds=10.0, ew_yellow_seconds=3.0)
    )
    env = TrafficSimulationEnvironment(
        use_gui=False,
        seed=42,
        controller=controller,
        simulation_id="test-agentic-env",
        enable_agentic_engine=True,
    )

    try:
        initial_state = env.start()
        assert env.agentic_engine is not None

        for step in range(1, 16):
            state = env.step()
            decision = env.get_latest_decision()
            assert decision is not None
            assert decision.step == step - 1
            assert decision.simulation_id == "test-agentic-env"
            assert decision.execution_status == ExecutionStatus.EXECUTED.value

        history = env.agentic_engine.get_decision_history()
        assert len(history) == 15
    finally:
        env.close()
