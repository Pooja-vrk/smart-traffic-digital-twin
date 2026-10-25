"""Tests for multi-intersection coordination, arterial progression, and adaptive optimization.

Covers:
1. MultiIntersectionCoordinator progression offsets, neighbor definitions, and corridor metrics.
2. Distinct behavior for all 4 coordination modes: ARTERY_EW, ARTERY_NS, BALANCED_ADAPTIVE, ISOLATED.
3. Offset-dependent neighbor phase determination with cycle position and progression offsets.
4. Validation of cycle length and step length.
5. Parameter validation and cycle/split budget constraints in AdaptiveSignalOptimizer.
6. Direct TraCI observations separated from heuristic progression estimates.
7. Explicit SpillbackMitigationDecision creation on critical queue conditions.
8. Coordinated Emergency Route Preemption, explicit clearance states, and safe restoration.
9. Telemetry transformation into MultiIntersectionCoordinationInfo with spillback mitigation.
10. REST API endpoints (GET /api/simulation/coordination, POST /api/simulation/coordination/mode).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.simulation_manager import sim_manager
from backend.services.telemetry_service import TelemetryService
from simulation.coordination import (
    AdaptiveSignalOptimizer,
    CoordinationMode,
    MultiIntersectionCoordinator,
    MultiIntersectionState,
    ProgressionStatus,
    SpillbackMitigationDecision,
)
from simulation.state import ApproachState, EmergencyVehicleState, TrafficState


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as test_client:
        yield test_client


def _make_dummy_traffic_state(
    simulation_time: float = 10.0,
    step: int = 10,
    current_phase: int = 0,
    q_north: int = 2,
    q_south: int = 3,
    q_east: int = 4,
    q_west: int = 2,
    emergency_active: bool = False,
    emergency_approach: str = "east",
) -> TrafficState:
    """Construct a mock TrafficState for deterministic unit testing."""
    north = ApproachState(direction="north", inflow_edge="N2C", queue_length=q_north, vehicle_count=q_north + 2, mean_speed=11.0, waiting_time=15.0)
    south = ApproachState(direction="south", inflow_edge="S2C", queue_length=q_south, vehicle_count=q_south + 2, mean_speed=10.5, waiting_time=20.0)
    east = ApproachState(direction="east", inflow_edge="E2C", queue_length=q_east, vehicle_count=q_east + 3, mean_speed=12.0, waiting_time=25.0)
    west = ApproachState(direction="west", inflow_edge="W2C", queue_length=q_west, vehicle_count=q_west + 1, mean_speed=12.5, waiting_time=12.0)

    em_state = None
    if emergency_active:
        em_state = EmergencyVehicleState(
            active=True,
            vehicle_id="EV_01",
            vehicle_type="ambulance",
            approach=emergency_approach,
            distance=150.0,
            distance_to_stopline=100.0,
            speed=14.0,
            eta_seconds=7.1,
            priority_requested=True,
            priority_approved=True,
            priority_active=True,
            lifecycle_state="PRIORITY_ACTIVE",
        )

    return TrafficState(
        simulation_time=simulation_time,
        step=step,
        current_phase=current_phase,
        current_phase_name="NORTH_SOUTH_GREEN" if current_phase == 0 else "EAST_WEST_GREEN",
        time_since_phase_change=5.0,
        north=north,
        south=south,
        east=east,
        west=west,
        emergency=em_state,
    )


# ── 1. Coordinator Basics and Neighbor Setup ─────────────────────────────

def test_coordinator_initialization():
    """Verify coordinator instantiates 4 grounded neighbors with physical link offsets."""
    coordinator = MultiIntersectionCoordinator(primary_intersection_id="INT-001", mode=CoordinationMode.ARTERY_EW)
    assert coordinator.primary_id == "INT-001"
    assert coordinator.mode == CoordinationMode.ARTERY_EW
    assert len(coordinator.neighbors) == 4

    # Check physical dimensions
    assert coordinator.APPROACH_LINK_LENGTH == 289.60
    assert coordinator.DESIGN_SPEED_MPS == 13.89
    assert coordinator.IDEAL_PROGRESSION_TRAVEL_TIME == pytest.approx(20.85, rel=1e-2)

    # Check neighbor IDs, corridors, and documented simulated intent
    assert coordinator.neighbors["north"].intersection_id == "INT-N"
    assert coordinator.neighbors["north"].corridor == "NS"
    assert coordinator.neighbors["north"].is_physical_tls is False
    assert "Simulated Arterial Intent" in coordinator.neighbors["north"].coordination_intent

    assert coordinator.neighbors["south"].intersection_id == "INT-S"
    assert coordinator.neighbors["south"].corridor == "NS"

    assert coordinator.neighbors["east"].intersection_id == "INT-E"
    assert coordinator.neighbors["east"].corridor == "EW"

    assert coordinator.neighbors["west"].intersection_id == "INT-W"
    assert coordinator.neighbors["west"].corridor == "EW"


def test_coordinator_modes_and_switching():
    """Verify switching coordination modes updates internal state and metrics."""
    coordinator = MultiIntersectionCoordinator()

    coordinator.set_mode(CoordinationMode.ARTERY_NS)
    assert coordinator.mode == CoordinationMode.ARTERY_NS
    assert coordinator.metrics.coordination_mode == "ARTERY_NS"

    coordinator.set_mode("balanced_adaptive")
    assert coordinator.mode == CoordinationMode.BALANCED_ADAPTIVE

    coordinator.set_mode("isolated")
    assert coordinator.mode == CoordinationMode.ISOLATED

    # Invalid fallback
    coordinator.set_mode("INVALID_MODE")
    assert coordinator.mode == CoordinationMode.ARTERY_EW


# ── 2. Distinct Coordination Mode Behaviors & ISOLATED Contract ──────────

def test_coordination_modes_distinct_behavior():
    """Verify distinct, documented behavior across ARTERY_EW, ARTERY_NS, BALANCED_ADAPTIVE, and ISOLATED."""
    state = _make_dummy_traffic_state(simulation_time=10.0, step=10, current_phase=2, q_north=5, q_south=5, q_east=5, q_west=5)

    # Mode 1: ARTERY_EW
    c_ew = MultiIntersectionCoordinator(mode=CoordinationMode.ARTERY_EW)
    res_ew = c_ew.step(state)
    assert res_ew.mode == "ARTERY_EW"
    assert res_ew.metrics.is_coordinated is True
    assert res_ew.metrics.arterial_ew_sync_score > res_ew.metrics.arterial_ns_sync_score
    assert res_ew.neighbors["east"].current_offset_seconds > 0.0

    # Mode 2: ARTERY_NS
    c_ns = MultiIntersectionCoordinator(mode=CoordinationMode.ARTERY_NS)
    res_ns = c_ns.step(state)
    assert res_ns.mode == "ARTERY_NS"
    assert res_ns.metrics.is_coordinated is True
    assert res_ns.metrics.arterial_ns_sync_score > res_ns.metrics.arterial_ew_sync_score
    assert res_ns.neighbors["north"].current_offset_seconds > 0.0

    # Mode 3: BALANCED_ADAPTIVE
    c_adapt = MultiIntersectionCoordinator(mode=CoordinationMode.BALANCED_ADAPTIVE)
    res_adapt = c_adapt.step(state)
    assert res_adapt.mode == "BALANCED_ADAPTIVE"
    assert res_adapt.metrics.is_coordinated is True
    assert res_adapt.metrics.overall_quality_score > 0.0

    # Mode 4: ISOLATED (Must NOT claim coordinated progression!)
    c_iso = MultiIntersectionCoordinator(mode=CoordinationMode.ISOLATED)
    res_iso = c_iso.step(state)
    assert res_iso.mode == "ISOLATED"
    assert res_iso.metrics.is_coordinated is False
    assert res_iso.metrics.arterial_ew_sync_score == 0.0
    assert res_iso.metrics.arterial_ns_sync_score == 0.0
    assert res_iso.metrics.overall_quality_score == 0.0
    assert res_iso.metrics.platoon_arrival_efficiency == 0.0

    for n in res_iso.neighbors.values():
        assert n.current_offset_seconds == 0.0
        assert n.progression_status == ProgressionStatus.ISOLATED.value
        assert n.coordination_role == "ISOLATED"


# ── 3. Offset Timing & Phase Determination ───────────────────────────────

def test_offset_dependent_phase_decisions():
    """Verify local cycle position (simulation_time + offset) % C dictates gateway signal states."""
    # Cycle length = 60s, Yellow = 3s. Available green budget = 54s.
    # In ARTERY_EW mode: g_ew = round(54.0 * 0.65, 1) = 35.1s.
    # East neighbor offset = round(20.85 % 60, 1) = 20.9s.
    coordinator = MultiIntersectionCoordinator(cycle_length=60.0, mode=CoordinationMode.ARTERY_EW)

    # 1. At t_sim = 0s: t_local = (0 + 20.9) % 60 = 20.9s < 35.1s -> GREEN
    state_0 = _make_dummy_traffic_state(simulation_time=0.0, step=0)
    res_0 = coordinator.step(state_0)
    assert res_0.neighbors["east"].signal_state == "green"
    assert res_0.neighbors["east"].progression_status == ProgressionStatus.PROGRESSION_ACTIVE.value

    # 2. At t_sim = 15s: t_local = (15 + 20.9) % 60 = 35.9s (in clearance window 35.1s to 38.1s) -> YELLOW
    state_15 = _make_dummy_traffic_state(simulation_time=15.0, step=15)
    res_15 = coordinator.step(state_15)
    assert res_15.neighbors["east"].signal_state == "yellow"
    assert res_15.neighbors["east"].progression_status == ProgressionStatus.TRANSITION_CLEARANCE.value

    # 3. At t_sim = 20s: t_local = (20 + 20.9) % 60 = 40.9s >= 38.1s -> RED
    state_20 = _make_dummy_traffic_state(simulation_time=20.0, step=20)
    res_20 = coordinator.step(state_20)
    assert res_20.neighbors["east"].signal_state == "red"


def test_cycle_and_step_length_validation():
    """Verify coordinator rejects invalid cycle lengths and step lengths."""
    # Invalid cycle lengths (< 20s or > 300s)
    with pytest.raises(ValueError, match="cycle_length.*must be between"):
        MultiIntersectionCoordinator(cycle_length=15.0)

    with pytest.raises(ValueError, match="cycle_length.*must be between"):
        MultiIntersectionCoordinator(cycle_length=350.0)

    coordinator = MultiIntersectionCoordinator(cycle_length=60.0)
    state = _make_dummy_traffic_state()

    # Invalid step length (<= 0)
    with pytest.raises(ValueError, match="step_length.*must be.*positive"):
        coordinator.step(state, step_length=0.0)

    with pytest.raises(ValueError, match="step_length.*must be.*positive"):
        coordinator.step(state, step_length=-1.0)


# ── 4. Adaptive Signal Optimizer Validations & Split Budget Constraints ──

def test_adaptive_optimizer_parameter_validation():
    """Verify AdaptiveSignalOptimizer validates all parameters at construction."""
    # Negative weight
    with pytest.raises(ValueError, match="Demand weights.*must be non-negative"):
        AdaptiveSignalOptimizer(weight_queue=-0.1)

    # Non-positive reference wait
    with pytest.raises(ValueError, match="reference_wait_seconds.*must be.*positive"):
        AdaptiveSignalOptimizer(reference_wait_seconds=0.0)

    # Non-positive min green
    with pytest.raises(ValueError, match="min_green_seconds.*must be.*positive"):
        AdaptiveSignalOptimizer(min_green_seconds=0.0)

    # Max green < min green
    with pytest.raises(ValueError, match="max_green_seconds.*cannot be less than min_green_seconds"):
        AdaptiveSignalOptimizer(min_green_seconds=25.0, max_green_seconds=20.0)

    # Cycle length too short for 2 min_greens + 2 yellows
    with pytest.raises(ValueError, match="cycle_length_seconds.*is too short"):
        AdaptiveSignalOptimizer(min_green_seconds=30.0, yellow_seconds=3.0, cycle_length_seconds=60.0)


def test_adaptive_optimizer_cycle_split_constraint():
    """Verify optimizer strictly satisfies G_ns + G_ew <= G_budget across extreme demands."""
    cycle = 60.0
    yellow = 3.0
    min_g = 10.0
    max_g = 45.0
    g_budget = cycle - 2 * yellow  # 54.0s

    optimizer = AdaptiveSignalOptimizer(
        min_green_seconds=min_g,
        max_green_seconds=max_g,
        yellow_seconds=yellow,
        cycle_length_seconds=cycle,
    )

    # Case A: Balanced Demand
    state_bal = _make_dummy_traffic_state(q_north=5, q_south=5, q_east=5, q_west=5)
    ns_b, ew_b = optimizer.evaluate_corridor_demand(state_bal)
    assert ns_b.recommended_green_seconds >= min_g
    assert ew_b.recommended_green_seconds >= min_g
    assert ns_b.recommended_green_seconds + ew_b.recommended_green_seconds <= g_budget + 1e-6

    # Case B: Extreme NS Demand (North=20, South=20, East=0, West=0)
    state_ns_heavy = _make_dummy_traffic_state(q_north=20, q_south=20, q_east=0, q_west=0)
    ns_h, ew_l = optimizer.evaluate_corridor_demand(state_ns_heavy)
    assert ns_h.recommended_green_seconds > ew_l.recommended_green_seconds
    assert ew_l.recommended_green_seconds >= min_g
    assert ns_h.recommended_green_seconds <= max_g
    assert ns_h.recommended_green_seconds + ew_l.recommended_green_seconds <= g_budget + 1e-6

    # Case C: Extreme EW Demand (North=0, South=0, East=25, West=25)
    state_ew_heavy = _make_dummy_traffic_state(q_north=0, q_south=0, q_east=25, q_west=25)
    ns_l, ew_h = optimizer.evaluate_corridor_demand(state_ew_heavy)
    assert ew_h.recommended_green_seconds > ns_l.recommended_green_seconds
    assert ns_l.recommended_green_seconds >= min_g
    assert ew_h.recommended_green_seconds <= max_g
    assert ns_l.recommended_green_seconds + ew_h.recommended_green_seconds <= g_budget + 1e-6


def test_adaptive_signal_optimizer_gap_out():
    """Verify gap-out actuates when current green queue dissipates while opposing corridor is queued."""
    optimizer = AdaptiveSignalOptimizer(min_green_seconds=10.0, max_green_seconds=50.0)

    # Case 1: Active green (NS, phase=0) has queue: do not switch/gap-out early
    state_active = _make_dummy_traffic_state(q_north=3, q_south=3, q_east=4, q_west=4)
    ns_act, ew_act = optimizer.evaluate_corridor_demand(state_active)
    should_switch, _ = optimizer.should_switch_phase(current_phase=0, elapsed_green=12.0, ns_metrics=ns_act, ew_metrics=ew_act)
    assert should_switch is False

    # Case 2: Before min_green elapsed (e.g. 5s): never switch
    state_cleared = _make_dummy_traffic_state(q_north=0, q_south=0, q_east=5, q_west=5)
    ns_clr, ew_clr = optimizer.evaluate_corridor_demand(state_cleared)
    ns_clr.queue_length = 0
    should_switch_early, _ = optimizer.should_switch_phase(current_phase=0, elapsed_green=5.0, ns_metrics=ns_clr, ew_metrics=ew_clr)
    assert should_switch_early is False

    # Case 3: After min_green elapsed (12s), active queue is 0, opposing has queued vehicles: gap-out triggers!
    should_switch_gap, reason_gap = optimizer.should_switch_phase(current_phase=0, elapsed_green=12.0, ns_metrics=ns_clr, ew_metrics=ew_clr)
    assert should_switch_gap is True
    assert "Gap-out actuated" in reason_gap


# ── 5. Separation of Observations vs Heuristics & Spillback Mitigation ───

def test_metrics_separation_observed_vs_heuristic():
    """Verify directly observed TraCI measurements are strictly separated from heuristic progression estimates."""
    coordinator = MultiIntersectionCoordinator(mode=CoordinationMode.ARTERY_EW)
    # State with specific approach queues: N=3, S=4, E=5, W=2 -> total=14, max=5
    state = _make_dummy_traffic_state(q_north=3, q_south=4, q_east=5, q_west=2)

    res = coordinator.step(state)

    # 1. Directly observed measurements (ground truth)
    assert res.metrics.observed_total_queue == 14
    assert res.metrics.observed_max_queue == 5
    assert res.metrics.observed_mean_speed_mps > 0.0

    # 2. Heuristic progression estimates (clearly modeled indices)
    assert isinstance(res.metrics.arterial_ew_sync_score, float)
    assert isinstance(res.metrics.arterial_ns_sync_score, float)
    assert isinstance(res.metrics.overall_quality_score, float)
    assert isinstance(res.metrics.platoon_arrival_efficiency, float)
    assert res.metrics.spillback_risk in ("LOW", "MODERATE", "HIGH")


def test_spillback_explicit_mitigation_decision():
    """Verify queue >= 14 produces an explicit SpillbackMitigationDecision with concrete actions."""
    coordinator = MultiIntersectionCoordinator(mode=CoordinationMode.ARTERY_EW)

    # 1. Non-critical state (queue = 6 < 14)
    normal_state = _make_dummy_traffic_state(q_north=2, q_south=2, q_east=6, q_west=3)
    res_normal = coordinator.step(normal_state)
    assert res_normal.metrics.spillback_mitigation.active is False
    assert res_normal.metrics.spillback_risk == "LOW"

    # 2. Critical spillback state (queue = 15 on East approach >= 14)
    critical_state = _make_dummy_traffic_state(q_north=2, q_south=2, q_east=15, q_west=3)
    res_crit = coordinator.step(critical_state)

    mitigation: SpillbackMitigationDecision = res_crit.metrics.spillback_mitigation
    assert mitigation.active is True
    assert mitigation.approach == "east"
    assert mitigation.queue_length == 15
    assert mitigation.threshold == 14
    assert mitigation.action == "METER_UPSTREAM_ENTRY_AND_FLUSH"
    assert mitigation.metering_rate_factor == 0.70  # Throttled inflow
    assert mitigation.green_extension_seconds == 7.5
    assert "METER_UPSTREAM_ENTRY_AND_FLUSH" in mitigation.explanation
    assert res_crit.metrics.spillback_risk == "HIGH"
    assert res_crit.neighbors["east"].progression_status == ProgressionStatus.SPILLBACK_MITIGATION.value


# ── 6. Emergency Route Preemption, Clearance & Restoration ───────────────

def test_coordinated_emergency_route_preemption_and_restoration():
    """Verify emergency vehicle activates preemption across corridor and safely restores to normal."""
    coordinator = MultiIntersectionCoordinator(mode=CoordinationMode.ARTERY_EW)

    # 1. Emergency active on East approach
    ev_state = _make_dummy_traffic_state(emergency_active=True, emergency_approach="east")
    res_ev = coordinator.step(ev_state)

    assert res_ev.emergency_active is True
    assert res_ev.emergency_approach == "east"

    # Upstream entrance: INT-E gets METERING_HOLD corridor green
    upstream = res_ev.neighbors["east"]
    assert upstream.coordination_role == "UPSTREAM"
    assert upstream.preemption_active is True
    assert upstream.progression_status == ProgressionStatus.METERING_HOLD.value
    assert upstream.signal_state == "green"

    # Downstream exit: INT-W gets ADVANCE_PREEMPTION green
    downstream = res_ev.neighbors["west"]
    assert downstream.coordination_role == "DOWNSTREAM"
    assert downstream.preemption_active is True
    assert downstream.progression_status == ProgressionStatus.ADVANCE_PREEMPTION.value
    assert downstream.signal_state == "green"

    # Conflicting cross approaches held in red
    assert res_ev.neighbors["north"].signal_state == "red"
    assert res_ev.neighbors["north"].progression_status == ProgressionStatus.METERING_HOLD.value
    assert res_ev.neighbors["south"].signal_state == "red"
    assert res_ev.neighbors["south"].progression_status == ProgressionStatus.METERING_HOLD.value

    # 2. Emergency vehicle passes / clears: safe restoration occurs
    normal_state = _make_dummy_traffic_state(emergency_active=False)
    res_restored = coordinator.step(normal_state)

    assert res_restored.emergency_active is False
    assert res_restored.emergency_approach is None
    for n in res_restored.neighbors.values():
        assert n.preemption_active is False
        assert n.coordination_role == "PEER"


# ── 7. Telemetry & Snapshot Serialization ────────────────────────────────

def test_telemetry_snapshot_with_coordination():
    """Verify TelemetryService serializes coordination state into MultiIntersectionCoordinationInfo with spillback mitigation."""
    coordinator = MultiIntersectionCoordinator(mode=CoordinationMode.ARTERY_EW)
    state = _make_dummy_traffic_state(q_east=16)  # triggers spillback
    coord_state = coordinator.step(state)

    snapshot = TelemetryService.create_snapshot(
        state=state,
        metrics=None,
        controller=None,
        coordination_state=coord_state,
    )

    assert snapshot.coordination is not None
    assert snapshot.coordination.mode == "ARTERY_EW"
    assert snapshot.coordination.primary_intersection_id == "INT-001"
    assert len(snapshot.coordination.neighbors) == 4
    assert snapshot.coordination.metrics.arterial_ew_sync_score > 0
    assert snapshot.coordination.metrics.observed_total_queue == coord_state.metrics.observed_total_queue

    # Verify embedded spillback mitigation in telemetry
    assert snapshot.coordination.spillback_mitigation is not None
    assert snapshot.coordination.spillback_mitigation.active is True
    assert snapshot.coordination.spillback_mitigation.action == "METER_UPSTREAM_ENTRY_AND_FLUSH"

    # Ensure model_dump serializes cleanly
    dump = snapshot.model_dump()
    assert "coordination" in dump
    assert dump["coordination"]["mode"] == "ARTERY_EW"
    assert dump["coordination"]["spillback_mitigation"]["active"] is True


def test_telemetry_snapshot_backward_compatibility():
    """Verify TelemetryService without coordination_state parameter maintains backward compatibility."""
    state = _make_dummy_traffic_state()
    snapshot = TelemetryService.create_snapshot(
        state=state,
        metrics=None,
        controller=None,
    )
    assert snapshot.coordination is None


# ── 8. REST API Endpoints ────────────────────────────────────────────────

def test_api_get_coordination_status(client: TestClient):
    """Verify GET /api/simulation/coordination returns valid coordination status."""
    response = client.get("/api/simulation/coordination")
    assert response.status_code == 200
    data = response.json()
    assert "coordination" in data
    assert "running" in data
    coord = data["coordination"]
    assert "mode" in coord
    assert "neighbors" in coord
    assert len(coord["neighbors"]) == 4


def test_api_set_coordination_mode_success(client: TestClient):
    """Verify POST /api/simulation/coordination/mode updates mode."""
    response = client.post(
        "/api/simulation/coordination/mode",
        json={"mode": "ARTERY_NS"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["mode"] == "ARTERY_NS"
    assert "switched to 'artery_ns'" in data["message"].lower()
    assert data["coordination"]["mode"] == "ARTERY_NS"


def test_api_set_coordination_mode_isolated(client: TestClient):
    """Verify POST /api/simulation/coordination/mode supports ISOLATED mode."""
    response = client.post(
        "/api/simulation/coordination/mode",
        json={"mode": "ISOLATED"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["mode"] == "ISOLATED"
    assert data["coordination"]["mode"] == "ISOLATED"
    assert data["coordination"]["metrics"]["is_coordinated"] is False


def test_api_set_coordination_mode_invalid(client: TestClient):
    """Verify POST /api/simulation/coordination/mode rejects invalid modes with 422."""
    response = client.post(
        "/api/simulation/coordination/mode",
        json={"mode": "NON_EXISTENT_MODE"},
    )
    assert response.status_code == 422


def test_environment_coordination_integration():
    """Verify TrafficSimulationEnvironment initializes coordinator and returns state."""
    from simulation.environment import TrafficSimulationEnvironment
    env = TrafficSimulationEnvironment(step_length=1.0, seed=42)
    assert hasattr(env, "coordinator")
    assert isinstance(env.coordinator, MultiIntersectionCoordinator)
    coord_state = env.get_coordination_state()
    assert isinstance(coord_state, MultiIntersectionState)
    assert len(coord_state.neighbors) == 4
