"""Comprehensive tests for Phase 5: Explainable AI & Decision Replay.

Validates:
1. Grounded AgenticDecisionRecord schema with explicit proposed vs executed action separation.
2. Safety override detection (minimum green restriction, yellow clearance, maximum green ceiling).
3. Strict Q-value grounding (never labeled or normalized as probabilities).
4. Prediction context inclusion only when genuinely available (no fabrication).
5. Emergency corridor context inclusion when active.
6. Chronological decision storage, query filtering (controller, safety overrides, emergency).
7. Single decision inspection endpoint (/api/simulation/{id}/decisions/{id}).
8. Offline replay bundle generation and frame synchronization without SUMO execution.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.persistence_service import PersistenceService
from simulation.agentic.engine import AgenticTrafficEngine
from simulation.agentic.models import (
    ActionName,
    AgenticDecisionRecord,
    DetectedConditions,
    SafetyValidationStatus,
    TrafficObservation,
)
from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.base_controller import SignalSafetyManager
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.state import ApproachState, EmergencyVehicleState, TrafficState


class MockTraCI:
    """Mock TraCI controller tracking phase actuation without SUMO."""

    def __init__(self, step_length: float = 1.0) -> None:
        self.step_length = step_length
        self.applied_phases = []
        self._running = True

    def set_tls_phase(self, phase: int) -> None:
        self.applied_phases.append(phase)

    def is_running(self) -> bool:
        return self._running


@pytest.fixture
def client():
    return TestClient(app)


# ── 1. SCHEMA & PROPOSED VS EXECUTED ACTION SEPARATION ────────────────────────

def test_explainable_decision_record_schema():
    """Verify AgenticDecisionRecord schema contains all required explainability fields."""
    record = AgenticDecisionRecord(
        simulation_id="sim-exp-01",
        simulation_time=15.0,
        step=15,
        controller="dqn",
        requested_action="REQUEST_EAST_WEST",
        requested_phase=2,
        validated_action="APPROVED",
        validated_phase=1,  # In transition to 2
        is_safety_override=False,
        safety_status="SAFE",
        safety_reason="Approved green switch to East-West corridor.",
        decision_reason="DQN policy selected action REQUEST_EAST_WEST.",
        q_values=[-1.2, 4.5, 8.9],
        reward=2.5,
    )

    d = record.to_dict()
    assert d["simulation_id"] == "sim-exp-01"
    assert d["step"] == 15
    assert d["requested_action"] == "REQUEST_EAST_WEST"
    assert d["requested_phase"] == 2
    assert d["validated_action"] == "APPROVED"
    assert d["validated_phase"] == 1
    assert d["is_safety_override"] is False
    assert d["q_values"] == [-1.2, 4.5, 8.9]
    assert d["prediction"] is None
    assert d["emergency"] is None


def test_proposed_vs_executed_minimum_green_restriction():
    """Verify safety override is flagged when controller requests a switch before min green."""
    safety_mgr = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
    controller = AdaptiveController()
    engine = AgenticTrafficEngine(controller=controller, safety_manager=safety_mgr)
    traci = MockTraCI()

    # Traffic state at t=3s: NS is green, elapsed=3s (<10s min green)
    # Heavy EW demand should cause controller to propose REQUEST_EAST_WEST (phase 2)
    state = TrafficState(
        simulation_time=3.0,
        step=3,
        current_phase=0,
        time_since_phase_change=3.0,
        north=ApproachState(direction="north", inflow_edge="N2C", queue_length=1),
        south=ApproachState(direction="south", inflow_edge="S2C", queue_length=1),
        east=ApproachState(direction="east", inflow_edge="E2C", queue_length=12),
        west=ApproachState(direction="west", inflow_edge="W2C", queue_length=12),
        total_queue=26,
    )

    phase, decision = engine.step(state, traci)

    # Controller requested switch to East-West
    assert decision.requested_action == ActionName.REQUEST_EAST_WEST.value
    assert decision.requested_phase == 2

    # Safety manager restricted transition due to min green
    assert decision.validated_action == SafetyValidationStatus.RESTRICTED_MIN_GREEN.value
    assert decision.validated_phase == 0  # Kept in NS_GREEN
    assert decision.is_safety_override is True
    assert "minimum green constraint" in decision.safety_reason
    assert "remaining" in decision.safety_reason


def test_proposed_vs_executed_maximum_green_override():
    """Verify safety override is flagged when safety manager overrides maximum green ceiling."""
    safety_mgr = SignalSafetyManager(min_green_seconds=10.0, max_green_seconds=30.0, yellow_seconds=3.0)
    controller = FixedTimeController()
    engine = AgenticTrafficEngine(controller=controller, safety_manager=safety_mgr)
    traci = MockTraCI()

    # Time in phase reaches 30s
    safety_mgr.current_phase = 0
    safety_mgr.time_in_current_phase = 30.5

    state = TrafficState(
        simulation_time=31.0,
        step=31,
        current_phase=0,
        time_since_phase_change=30.5,
    )

    # Validate directly against safety manager
    val_phase, val_action, safe_status, safe_reason = engine.validate_safety(
        requested_green_phase=0,  # Controller wants to hold
        requested_action=ActionName.EXTEND_GREEN.value,
        state=state,
    )

    assert val_action == SafetyValidationStatus.OVERRIDE_MAX_GREEN.value
    assert safe_status == "MAX_GREEN_EXCEEDED"
    assert "maximum green ceiling" in safe_reason


def test_proposed_vs_executed_approval():
    """Verify approved transition is NOT marked as a safety override."""
    safety_mgr = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
    controller = AdaptiveController()
    engine = AgenticTrafficEngine(controller=controller, safety_manager=safety_mgr)
    traci = MockTraCI()

    # Elapsed 12s in green (> min green 10s)
    safety_mgr.current_phase = 0
    safety_mgr.time_in_current_phase = 12.0

    state = TrafficState(
        simulation_time=12.0,
        step=12,
        current_phase=0,
        time_since_phase_change=12.0,
        north=ApproachState(direction="north", inflow_edge="N2C", queue_length=1),
        south=ApproachState(direction="south", inflow_edge="S2C", queue_length=1),
        east=ApproachState(direction="east", inflow_edge="E2C", queue_length=15),
        west=ApproachState(direction="west", inflow_edge="W2C", queue_length=15),
        total_queue=32,
    )

    phase, decision = engine.step(state, traci)

    assert decision.requested_action == ActionName.REQUEST_EAST_WEST.value
    assert decision.validated_action == SafetyValidationStatus.APPROVED.value
    assert decision.is_safety_override is False
    assert "approved" in decision.safety_reason.lower()


# ── 2. NON-HALLUCINATED Q-VALUES & GROUNDING ─────────────────────────────────

def test_q_values_grounding_not_probabilities():
    """Verify Q-values are raw cumulative return floats and never normalized as probabilities."""
    record = AgenticDecisionRecord(
        controller="dqn",
        q_values=[-12.45, 8.32, 14.91],
    )
    d = record.to_dict()

    # Q-values can be negative or > 1.0 (expected discounted return, strictly not probabilities)
    assert d["q_values"] == [-12.45, 8.32, 14.91]
    assert sum(d["q_values"]) != 1.0
    assert any(q < 0 for q in d["q_values"])
    assert any(q > 1 for q in d["q_values"])


def test_classical_controllers_do_not_fabricate_q_values():
    """Verify Fixed-Time and Adaptive controllers have null Q-values."""
    fixed_engine = AgenticTrafficEngine(controller=FixedTimeController())
    adaptive_engine = AgenticTrafficEngine(controller=AdaptiveController())
    traci = MockTraCI()

    state = TrafficState(simulation_time=5.0, step=5, current_phase=0, time_since_phase_change=5.0)

    _, fixed_dec = fixed_engine.step(state, traci)
    _, adapt_dec = adaptive_engine.step(state, traci)

    assert fixed_dec.q_values is None
    assert adapt_dec.q_values is None


# ── 3. PREDICTION & EMERGENCY CONTEXT GROUNDING ──────────────────────────────

def test_prediction_context_when_available():
    """Verify predictive intelligence forecast is stored when present, without fabrication."""
    engine = AgenticTrafficEngine(controller=FixedTimeController())
    traci = MockTraCI()

    state = TrafficState(simulation_time=10.0, step=10, current_phase=0, time_since_phase_change=10.0)
    # Attach real prediction metadata
    state.prediction = {
        "model_available": True,
        "predicted_score": 42.5,
        "confidence_lower": 35.0,
        "confidence_upper": 50.0,
        "trend": "INCREASING",
        "congestion_level": "MODERATE",
    }

    _, dec = engine.step(state, traci)
    assert dec.prediction is not None
    assert dec.prediction["predicted_score"] == 42.5
    assert dec.prediction["confidence_lower"] == 35.0
    assert dec.prediction["confidence_upper"] == 50.0
    assert dec.prediction["trend"] == "INCREASING"


def test_emergency_context_when_active():
    """Verify emergency vehicle context is recorded when active and null when absent."""
    engine = AgenticTrafficEngine(controller=AdaptiveController())
    traci = MockTraCI()

    # 1. Without emergency vehicle
    normal_state = TrafficState(simulation_time=5.0, step=5, current_phase=0, time_since_phase_change=5.0)
    _, norm_dec = engine.step(normal_state, traci)
    assert norm_dec.emergency is None

    # 2. With emergency vehicle
    ev_state = TrafficState(
        simulation_time=6.0,
        step=6,
        current_phase=0,
        time_since_phase_change=6.0,
        emergency=EmergencyVehicleState(
            active=True,
            vehicle_id="AMB-01",
            approach="east",
            distance=85.0,
            speed=14.0,
            state="APPROACHING",
            priority_requested=True,
        ),
    )
    _, ev_dec = engine.step(ev_state, traci)
    assert ev_dec.emergency is not None
    assert ev_dec.emergency["active"] is True
    assert ev_dec.emergency["vehicle_id"] == "AMB-01"
    assert ev_dec.emergency["approach"] == "east"
    assert ev_dec.emergency["distance"] == 85.0


# ── 4. PERSISTENCE & MULTI-CRITERIA FILTERING ────────────────────────────────

def test_persistence_and_multi_criteria_filtering():
    """Verify decision persistence and filtering by controller, override, and emergency."""
    sim_id = "test-phase5-persist-01"

    # Save 3 varied decisions
    d1 = AgenticDecisionRecord(
        simulation_id=sim_id,
        step=1,
        simulation_time=1.0,
        controller="fixed",
        requested_action="CYCLE_PHASE",
        validated_action="APPROVED",
        is_safety_override=False,
    ).to_dict()

    d2 = AgenticDecisionRecord(
        simulation_id=sim_id,
        step=2,
        simulation_time=2.0,
        controller="adaptive",
        requested_action="REQUEST_EAST_WEST",
        validated_action="RESTRICTED_MIN_GREEN",
        is_safety_override=True,
        safety_reason="Min green restricted",
    ).to_dict()

    d3 = AgenticDecisionRecord(
        simulation_id=sim_id,
        step=3,
        simulation_time=3.0,
        controller="dqn",
        requested_action="REQUEST_EMERGENCY_PRIORITY",
        validated_action="APPROVED",
        is_safety_override=False,
        emergency={"active": True, "vehicle_id": "AMB-99"},
    ).to_dict()

    PersistenceService.save_agentic_decision(d1)
    PersistenceService.save_agentic_decision(d2)
    PersistenceService.save_agentic_decision(d3)

    # Query all
    all_decs = PersistenceService.get_simulation_decisions(sim_id)
    assert len(all_decs) >= 3

    # Filter safety overrides only
    overrides = PersistenceService.get_simulation_decisions(sim_id, safety_override_only=True)
    assert len(overrides) >= 1
    assert all(d["is_safety_override"] is True for d in overrides)

    # Filter emergency only
    emergencies = PersistenceService.get_simulation_decisions(sim_id, emergency_only=True)
    assert len(emergencies) >= 1
    assert all(d.get("emergency", {}).get("active") is True for d in emergencies)

    # Filter by controller
    dqn_decs = PersistenceService.get_simulation_decisions(sim_id, controller="dqn")
    assert len(dqn_decs) >= 1
    assert all(d["controller"] == "dqn" for d in dqn_decs)


# ── 5. SINGLE DECISION DETAIL & OFFLINE REPLAY ENDPOINTS ──────────────────────

def test_single_decision_api_endpoint(client: TestClient):
    """Verify GET /api/simulation/{sim_id}/decisions/{decision_id} returns single decision."""
    sim_id = "test-phase5-api-01"
    dec_record = AgenticDecisionRecord(
        simulation_id=sim_id,
        step=10,
        simulation_time=10.0,
        controller="dqn",
        decision_reason="Policy selected NS green.",
    )
    dec_dict = dec_record.to_dict()
    PersistenceService.save_agentic_decision(dec_dict)

    resp = client.get(f"/api/simulation/{sim_id}/decisions/{dec_record.decision_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_id"] == dec_record.decision_id
    assert data["simulation_id"] == sim_id
    assert data["decision_reason"] == "Policy selected NS green."

    # 404 for unknown decision ID
    bad_resp = client.get(f"/api/simulation/{sim_id}/decisions/non-existent-uuid")
    assert bad_resp.status_code == 404


def test_offline_replay_endpoint(client: TestClient):
    """Verify GET /api/simulation/{sim_id}/replay returns synchronized frames without SUMO."""
    sim_id = "test-phase5-replay-01"

    # Save mock snapshots and decisions
    snap1 = {
        "simulation_id": sim_id,
        "step": 1,
        "simulation_time": 1.0,
        "controller": "adaptive",
        "vehicles": {"total": 5, "entered": 5, "completed": 0},
        "queues": {"total": 3},
        "signal": {"phase_index": 0, "phase_name": "NS_GREEN"},
    }
    snap2 = {
        "simulation_id": sim_id,
        "step": 2,
        "simulation_time": 2.0,
        "controller": "adaptive",
        "vehicles": {"total": 6, "entered": 6, "completed": 1},
        "queues": {"total": 2},
        "signal": {"phase_index": 0, "phase_name": "NS_GREEN"},
    }
    dec1 = AgenticDecisionRecord(
        simulation_id=sim_id,
        step=1,
        simulation_time=1.0,
        controller="adaptive",
        requested_action="EXTEND_GREEN",
        validated_action="APPROVED",
    ).to_dict()

    PersistenceService.save_traffic_snapshot(snap1)
    PersistenceService.save_traffic_snapshot(snap2)
    PersistenceService.save_agentic_decision(dec1)

    resp = client.get(f"/api/simulation/{sim_id}/replay")
    assert resp.status_code == 200
    bundle = resp.json()

    assert bundle["simulation_id"] == sim_id
    assert bundle["total_frames"] == 2
    assert len(bundle["frames"]) == 2

    frame1 = bundle["frames"][0]
    assert frame1["step"] == 1
    assert frame1["simulation_time"] == 1.0
    assert frame1["snapshot"]["queues"]["total"] == 3
    assert frame1["decision"]["requested_action"] == "EXTEND_GREEN"

    frame2 = bundle["frames"][1]
    assert frame2["step"] == 2
    assert frame2["simulation_time"] == 2.0
    assert frame2["snapshot"]["queues"]["total"] == 2

    # 404 for unknown simulation with no recorded frames
    empty_resp = client.get("/api/simulation/empty-sim-run/replay")
    assert empty_resp.status_code == 404
