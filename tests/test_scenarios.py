"""Unit and integration tests for Scenario / What-If Lab.

Tests parameter validation, deterministic SUMO demand generation,
lifecycle state transitions, conflict prevention, controller comparisons,
and REST API endpoints.
"""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from backend.database.repositories.scenario_repository import ScenarioRepository
from backend.main import app
from backend.schemas.scenario import DirectionBiasSchema, ScenarioRunRequest
from backend.services.scenario_manager import (
    SCENARIO_PRESETS,
    scenario_manager,
)
from backend.services.simulation_manager import (
    SimulationAlreadyRunningError,
    sim_manager,
)
from simulation.scenario_generator import (
    DirectionBias,
    ScenarioConfig,
    ScenarioDemandGenerator,
)


@pytest.fixture(autouse=True)
def clean_scenario_state():
    """Ensure scenario and simulation managers are stopped and in clean state before/after tests."""
    if scenario_manager.is_running():
        scenario_manager.stop_scenario()
        time.sleep(0.3)
    if sim_manager.is_running():
        sim_manager.stop_simulation()
        time.sleep(0.3)

    scenario_manager._status = "idle"
    scenario_manager._scenario_id = None
    scenario_manager._latest_result = None
    scenario_manager._error_message = None

    sim_manager._status = "idle"
    sim_manager._simulation_id = None
    sim_manager._latest_snapshot = None
    sim_manager._last_result = None

    yield

    if scenario_manager.is_running():
        scenario_manager.stop_scenario()
        time.sleep(0.3)
    if sim_manager.is_running():
        sim_manager.stop_simulation()
        time.sleep(0.3)


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as test_client:
        yield test_client


# ── 1. PARAMETER & SCHEMA VALIDATION TESTS ───────────────────────────────────

def test_direction_bias_valid():
    """Test valid directional bias summing to 100%."""
    bias = DirectionBias(north=25.0, south=25.0, east=25.0, west=25.0)
    bias.validate()
    assert bias.north == 25.0

    asymmetric = DirectionBias(north=15.0, south=15.0, east=55.0, west=15.0)
    asymmetric.validate()
    assert asymmetric.east == 55.0


def test_direction_bias_invalid_sum():
    """Test direction bias failing when sum is not 100%."""
    bias = DirectionBias(north=30.0, south=30.0, east=30.0, west=30.0)
    with pytest.raises(ValueError, match="must sum to 100%"):
        bias.validate()


def test_direction_bias_negative_value():
    """Test direction bias rejecting negative percentages."""
    bias = DirectionBias(north=-10.0, south=50.0, east=30.0, west=30.0)
    with pytest.raises(ValueError):
        bias.validate()


def test_scenario_run_request_schema_validation():
    """Test Pydantic validation of ScenarioRunRequest."""
    req = ScenarioRunRequest(
        name="East Heavy Peak",
        density="high",
        direction_bias=DirectionBiasSchema(north=15.0, south=15.0, east=55.0, west=15.0),
        controller="dqn",
        duration=300,
        seed=42,
    )
    assert req.name == "East Heavy Peak"
    assert req.density == "high"
    assert req.duration == 300
    assert req.seed == 42


def test_scenario_run_request_invalid_direction_sum():
    """Test Pydantic schema rejects invalid direction sums."""
    with pytest.raises(ValueError):
        ScenarioRunRequest(
            name="Invalid Sum",
            direction_bias=DirectionBiasSchema(north=50.0, south=50.0, east=50.0, west=50.0),
        )


# ── 2. SUMO DEMAND GENERATION & DETERMINISM TESTS ─────────────────────────────

def test_scenario_demand_generator_creates_valid_files():
    """Test ScenarioDemandGenerator creates valid route and sumocfg XML files."""
    cfg = ScenarioConfig(
        name="North-South Corridor Rush",
        density="high",
        direction_bias=DirectionBias(north=40.0, south=40.0, east=10.0, west=10.0),
        duration=300,
        seed=42,
    )
    r_path, s_path = ScenarioDemandGenerator.generate_scenario_files(cfg)

    assert r_path.is_file()
    assert s_path.is_file()

    # Verify content in route file
    route_content = r_path.read_text(encoding="utf-8")
    assert "<routes" in route_content
    assert "flow_NS" in route_content
    assert "flow_EW" in route_content
    assert "standard_car" in route_content
    assert "heavy_vehicle" in route_content

    # Verify content in sumocfg file
    sumocfg_content = s_path.read_text(encoding="utf-8")
    assert "<configuration" in sumocfg_content
    assert "intersection.net.xml" in sumocfg_content
    assert r_path.name in sumocfg_content


def test_deterministic_seed_and_hash():
    """Test identical scenario parameters produce the exact same hash and content."""
    cfg1 = ScenarioConfig(
        name="East Influx",
        density="medium",
        direction_bias=DirectionBias(north=15.0, south=15.0, east=55.0, west=15.0),
        duration=300,
        seed=42,
    )
    cfg2 = ScenarioConfig(
        name="East Influx",
        density="medium",
        direction_bias=DirectionBias(north=15.0, south=15.0, east=55.0, west=15.0),
        duration=300,
        seed=42,
    )

    assert cfg1.compute_hash() == cfg2.compute_hash()

    # Different seed gives different hash
    cfg3 = ScenarioConfig(
        name="East Influx",
        density="medium",
        direction_bias=DirectionBias(north=15.0, south=15.0, east=55.0, west=15.0),
        duration=300,
        seed=99,
    )
    assert cfg1.compute_hash() != cfg3.compute_hash()


# ── 3. PRESETS & REPOSITORY TESTS ─────────────────────────────────────────────

def test_scenario_presets_list():
    """Test standard pre-configured scenario presets exist and validate."""
    presets = scenario_manager.get_presets()
    assert len(presets) >= 5

    preset_ids = [p.id for p in presets]
    assert "balanced" in preset_ids
    assert "high_traffic" in preset_ids
    assert "east_heavy" in preset_ids
    assert "north_south_corridor" in preset_ids
    assert "west_heavy" in preset_ids

    for p in presets:
        tot = p.direction_bias.north + p.direction_bias.south + p.direction_bias.east + p.direction_bias.west
        assert abs(tot - 100.0) < 0.1


def test_scenario_repository_crud():
    """Test ScenarioRepository creates, updates, and retrieves scenario records."""
    scen_id = "test_scen_repo_123"
    import datetime

    doc = {
        "scenario_id": scen_id,
        "scenario_name": "Test Balanced",
        "controller": "dqn",
        "seed": 42,
        "duration": 60,
        "status": "running",
        "metrics": None,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    assert ScenarioRepository.create_scenario(doc) is True

    # Retrieve
    fetched = ScenarioRepository.get_scenario(scen_id)
    assert fetched is not None
    assert fetched["scenario_name"] == "Test Balanced"

    # Update
    update_data = {
        "status": "completed",
        "metrics": {"total_vehicles_served": 45, "average_queue": 3.2},
    }
    assert ScenarioRepository.update_scenario(scen_id, update_data) is True

    updated = ScenarioRepository.get_scenario(scen_id)
    assert updated["status"] == "completed"
    assert updated["metrics"]["total_vehicles_served"] == 45

    # List
    items = ScenarioRepository.list_scenarios(limit=10)
    assert len(items) >= 1
    assert any(i["scenario_id"] == scen_id for i in items)


# ── 4. CONFLICT PREVENTION TESTS ──────────────────────────────────────────────

def test_prevent_scenario_when_simulation_running():
    """Test starting a scenario is safely rejected when a simulation is running."""
    sim_manager._status = "running"
    sim_manager._simulation_id = "sim-running-test"

    req = ScenarioRunRequest(
        name="Blocked Scenario",
        density="medium",
        controller="dqn",
        duration=60,
        seed=42,
    )

    with pytest.raises(SimulationAlreadyRunningError, match="Simulation already running"):
        scenario_manager.run_scenario(req)


def test_prevent_simulation_when_scenario_running():
    """Test starting a simulation is safely rejected when a scenario is running."""
    scenario_manager._status = "running"
    scenario_manager._scenario_id = "scen-running-test"

    from backend.schemas.simulation import SimulationStartRequest
    sim_req = SimulationStartRequest(controller="fixed", steps=60, seed=42)

    with pytest.raises(SimulationAlreadyRunningError, match="Scenario Lab experiment is currently running"):
        sim_manager.start_simulation(sim_req)


def test_prevent_duplicate_scenario_execution():
    """Test starting a second scenario is rejected when one is already active."""
    scenario_manager._status = "running"
    scenario_manager._scenario_id = "scen-active-1"

    req = ScenarioRunRequest(
        name="Second Scenario",
        density="medium",
        controller="dqn",
        duration=60,
        seed=42,
    )

    with pytest.raises(SimulationAlreadyRunningError, match="currently running"):
        scenario_manager.run_scenario(req)


# ── 5. REST API ENDPOINTS TESTS ───────────────────────────────────────────────

def test_api_scenario_presets_endpoint(client: TestClient):
    """Test GET /api/scenarios/presets returns available presets."""
    response = client.get("/api/scenarios/presets")
    assert response.status_code == 200
    presets = response.json()
    assert isinstance(presets, list)
    assert len(presets) >= 5
    assert presets[0]["id"] == "balanced"


def test_api_scenario_status_idle(client: TestClient):
    """Test GET /api/scenarios/status returns idle when nothing is running."""
    response = client.get("/api/scenarios/status")
    assert response.status_code == 200
    data = response.json()
    assert data["running"] is False
    assert data["status"] == "idle"


def test_api_scenario_history_endpoint(client: TestClient):
    """Test GET /api/scenarios/history returns list of historical runs."""
    response = client.get("/api/scenarios/history")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_scenario_invalid_request_validation(client: TestClient):
    """Test POST /api/scenarios/run validates input and returns 422 for invalid parameters."""
    # Invalid duration (< 30)
    response = client.post(
        "/api/scenarios/run",
        json={
            "name": "Invalid Duration",
            "duration": 5,
            "controller": "dqn",
            "seed": 42,
        },
    )
    assert response.status_code == 422

    # Invalid direction sum
    response_sum = client.post(
        "/api/scenarios/run",
        json={
            "name": "Invalid Sum",
            "direction_bias": {"north": 50, "south": 50, "east": 50, "west": 50},
            "controller": "dqn",
            "duration": 100,
            "seed": 42,
        },
    )
    assert response_sum.status_code == 422


# ── 6. REAL SUMO SCENARIO INTEGRATION TESTS ───────────────────────────────────

def test_real_sumo_scenario_execution_dqn(client: TestClient):
    """Integration test: Execute real SUMO traffic scenario with DQN controller and verify metrics."""
    req_payload = {
        "name": "East Heavy Influx Test",
        "density": "high",
        "direction_bias": {"north": 15.0, "south": 15.0, "east": 55.0, "west": 15.0},
        "controller": "dqn",
        "duration": 30,
        "seed": 42,
        "compare_all_controllers": False,
    }

    start_resp = client.post("/api/scenarios/run", json=req_payload)
    assert start_resp.status_code == 200
    scen_id = start_resp.json()["scenario_id"]
    assert scen_id is not None

    # Wait for scenario to complete (timeout 60s)
    start_time = time.time()
    completed = False
    while time.time() - start_time < 60.0:
        st_resp = client.get("/api/scenarios/status")
        assert st_resp.status_code == 200
        data = st_resp.json()
        if data["status"] == "completed":
            completed = True
            break
        time.sleep(0.3)

    assert completed, "Real SUMO scenario did not complete within expected time"

    # Query result endpoint
    result_resp = client.get(f"/api/scenarios/{scen_id}/result")
    assert result_resp.status_code == 200
    res_data = result_resp.json()

    assert res_data["scenario_id"] == scen_id
    assert res_data["scenario_name"] == "East Heavy Influx Test"
    assert res_data["controller"] == "dqn"
    assert res_data["status"] == "completed"
    assert "metrics" in res_data
    assert "total_vehicles_served" in res_data["metrics"]
    assert "average_queue" in res_data["metrics"]
    assert "average_speed" in res_data["metrics"]
    assert "total_co2_emission_kg" in res_data["metrics"]


def test_scenario_stop_and_restart(client: TestClient):
    """Integration test: Start a scenario, stop it mid-run, and verify clean restart."""
    req_payload = {
        "name": "Long Scenario to Stop",
        "density": "medium",
        "controller": "fixed",
        "duration": 100,
        "seed": 42,
    }

    start_resp = client.post("/api/scenarios/run", json=req_payload)
    assert start_resp.status_code == 200

    # Wait briefly then trigger stop
    time.sleep(1.0)
    stop_resp = client.post("/api/scenarios/stop")
    assert stop_resp.status_code == 200

    # Wait for status to become stopped
    start_time = time.time()
    stopped = False
    while time.time() - start_time < 10.0:
        st_resp = client.get("/api/scenarios/status")
        if st_resp.json()["status"] in ["stopped", "idle"]:
            stopped = True
            break
        time.sleep(0.2)

    assert stopped, "Scenario failed to stop cleanly"

    # Verify we can immediately start another scenario
    req_payload2 = {
        "name": "Clean Restart Scenario",
        "density": "low",
        "controller": "adaptive",
        "duration": 30,
        "seed": 123,
    }
    start_resp2 = client.post("/api/scenarios/run", json=req_payload2)
    assert start_resp2.status_code == 200
    assert start_resp2.json()["status"] in ["starting", "running", "completed"]

    # Cleanly stop the restart scenario so future tests start in idle state
    time.sleep(0.5)
    client.post("/api/scenarios/stop")
    time.sleep(0.5)


# ── 7. EMERGENCY VEHICLE INTELLIGENCE TESTS ──────────────────────────────────

def test_emergency_scenario_preset_and_config():
    """Verify emergency vehicle scenario preset exists and ScenarioConfig hashes deterministically."""
    ev_preset = next((p for p in SCENARIO_PRESETS if p.id == "emergency_east"), None)
    assert ev_preset is not None
    assert ev_preset.emergency_vehicle is True
    assert ev_preset.emergency_approach == "east"
    assert ev_preset.emergency_step == 15

    cfg = ScenarioConfig(
        name="Emergency Test",
        emergency_vehicle=True,
        emergency_approach="east",
        emergency_step=15,
        duration=120,
        seed=42,
    )
    h1 = cfg.compute_hash()
    h2 = cfg.compute_hash()
    assert h1 == h2
    assert len(h1) == 10

    cfg_no_ev = ScenarioConfig(
        name="Emergency Test",
        emergency_vehicle=False,
        duration=120,
        seed=42,
    )
    assert cfg_no_ev.compute_hash() != h1


def test_emergency_vehicle_demand_generation():
    """Verify ScenarioDemandGenerator produces valid XML with emergency_vehicle entity."""
    cfg = ScenarioConfig(
        name="EV Generation Test",
        density="medium",
        emergency_vehicle=True,
        emergency_approach="east",
        emergency_step=10,
        duration=60,
        seed=99,
    )
    route_path, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(cfg)
    assert route_path.is_file()
    assert sumocfg_path.is_file()

    content = route_path.read_text(encoding="utf-8")
    assert 'id="emergency_vehicle"' in content
    assert 'vClass="emergency"' in content
    assert 'id="EV_01"' in content
    assert 'depart="10.0"' in content
    assert 'route="r_EW"' in content


def test_emergency_priority_evaluator_safety_constraints():
    """Unit test: Verify EmergencyPriorityEvaluator and SignalSafetyManager constraint enforcement."""
    from simulation.controllers.base_controller import (
        EmergencyPriorityEvaluator,
        SignalSafetyManager,
    )
    from simulation.state import EmergencyVehicleState, TrafficState

    safety_mgr = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
    safety_mgr.reset(initial_phase=SignalSafetyManager.NS_GREEN)
    safety_mgr.time_in_current_phase = 2.0  # 2s in NS_GREEN (< 10s min green)

    # Approaching East vehicle needs EW_GREEN (phase 2)
    ev_state = EmergencyVehicleState(
        active=True,
        vehicle_id="EV_01",
        vehicle_type="emergency_vehicle",
        approach="east",
        state="APPROACHING",
        distance=120.0,
        speed=15.0,
    )
    state = TrafficState(emergency=ev_state)

    target_phase, decision = EmergencyPriorityEvaluator.evaluate(state, safety_mgr)
    assert target_phase == SignalSafetyManager.EW_GREEN
    assert decision["priority_requested"] is True
    assert decision["priority_approved"] is False  # Cannot approve yet due to min green
    assert decision["safety_status"] == "MIN_GREEN_HOLD"
    assert "minimum green" in decision["reason"]

    # Advance safety manager past min_green
    safety_mgr.time_in_current_phase = 10.0
    target_phase2, decision2 = EmergencyPriorityEvaluator.evaluate(state, safety_mgr)
    assert decision2["safety_status"] == "INITIATING_TRANSITION"

    # Step safety manager into transition
    safe_phase = safety_mgr.step(target_phase2, step_length=1.0)
    assert safe_phase == SignalSafetyManager.NS_YELLOW
    assert safety_mgr.is_in_transition is True

    # During transition
    target_phase3, decision3 = EmergencyPriorityEvaluator.evaluate(state, safety_mgr)
    assert decision3["safety_status"] == "TRANSITIONING"
    assert decision3["priority_active"] is False

    # Step through yellow transition (3s total)
    safety_mgr.step(target_phase2, step_length=1.0)
    safety_mgr.step(target_phase2, step_length=1.0)

    # Now in target green phase (EW_GREEN)
    assert safety_mgr.current_phase == SignalSafetyManager.EW_GREEN
    assert safety_mgr.is_in_transition is False

    target_phase4, decision4 = EmergencyPriorityEvaluator.evaluate(state, safety_mgr)
    assert decision4["safety_status"] == "PRIORITY_GRANTED"
    assert decision4["priority_active"] is True
    assert decision4["priority_approved"] is True


def test_emergency_telemetry_snapshot_serialization():
    """Verify TelemetryService serializes EmergencyLiveInfo into TrafficSnapshotResponse."""
    from backend.services.telemetry_service import TelemetryService
    from simulation.state import EmergencyVehicleState, TrafficState

    ev_state = EmergencyVehicleState(
        active=True,
        vehicle_id="EV_01",
        vehicle_type="emergency_vehicle",
        approach="east",
        state="APPROACHING",
        distance=85.5,
        speed=16.2,
        priority_requested=True,
        priority_approved=True,
        priority_active=True,
        safety_status="PRIORITY_GRANTED",
        current_action="PRIORITY_EAST_WEST_GREEN",
        reason="Priority green active for East approach",
    )
    state = TrafficState(simulation_time=25.0, step=25, emergency=ev_state)

    snapshot = TelemetryService.create_snapshot(
        state=state,
        metrics=None,
        controller=None,
        simulation_id="test_sim_ev",
    )

    assert snapshot.emergency is not None
    assert snapshot.emergency.active is True
    assert snapshot.emergency.vehicle_id == "EV_01"
    assert snapshot.emergency.approach == "east"
    assert snapshot.emergency.distance == 85.5
    assert snapshot.emergency.safety_status == "PRIORITY_GRANTED"
    assert snapshot.emergency.priority_active is True


def test_emergency_scenario_api_execution(client: TestClient):
    """Integration test: Launch real SUMO emergency scenario via REST API and verify clean lifecycle."""
    req_payload = {
        "name": "API Emergency Vehicle Run",
        "density": "medium",
        "controller": "adaptive",
        "duration": 30,
        "seed": 42,
        "emergency_vehicle": True,
        "emergency_approach": "east",
        "emergency_step": 5,
    }

    start_resp = client.post("/api/scenarios/run", json=req_payload)
    assert start_resp.status_code == 200
    data = start_resp.json()
    scen_id = data["scenario_id"]
    assert scen_id is not None

    # Wait for completion (timeout 50s)
    start_time = time.time()
    completed = False
    while time.time() - start_time < 50.0:
        st_resp = client.get("/api/scenarios/status")
        assert st_resp.status_code == 200
        st_data = st_resp.json()
        if st_data["status"] == "completed":
            completed = True
            break
        time.sleep(0.3)

    assert completed, "Emergency scenario did not complete within expected time"

    res_resp = client.get(f"/api/scenarios/{scen_id}/result")
    assert res_resp.status_code == 200
    res_data = res_resp.json()
    assert res_data["status"] == "completed"
    assert "metrics" in res_data
