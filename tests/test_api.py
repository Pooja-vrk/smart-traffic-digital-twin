"""Unit and integration tests for FastAPI backend, simulation manager, REST APIs, and WebSocket."""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.simulation_manager import sim_manager


@pytest.fixture(autouse=True)
def clean_simulation_state():
    """Ensure simulation manager is stopped and in idle state before and after each test."""
    if sim_manager.is_running():
        sim_manager.stop_simulation()
        time.sleep(0.5)
    sim_manager._status = "idle"
    sim_manager._simulation_id = None
    sim_manager._latest_snapshot = None
    sim_manager._last_result = None
    yield
    if sim_manager.is_running():
        sim_manager.stop_simulation()
        time.sleep(0.5)


@pytest.fixture
def client():
    """FastAPI TestClient fixture with lifespan context."""
    with TestClient(app) as test_client:
        yield test_client


def test_root_endpoint(client: TestClient):
    """Test root endpoint returns service metadata and discovery links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert data["docs"] == "/docs"
    assert data["health"] == "/api/health"


def test_health_endpoint(client: TestClient):
    """Test health check endpoint reports status, SUMO availability, and MongoDB status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["service"] == "smart-traffic-digital-twin"
    assert data["version"] == "1.0.0"
    assert "sumo_available" in data
    assert "mongodb_available" in data


def test_cors_headers_for_dev_origins(client: TestClient):
    """Test CORS headers are properly returned for local dev origins including port 5174."""
    for origin in ["http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:5173", "http://127.0.0.1:5173"]:
        response = client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == origin
        assert response.headers.get("access-control-allow-credentials") == "true"

        get_resp = client.get("/api/health", headers={"Origin": origin})
        assert get_resp.status_code == 200
        assert get_resp.headers.get("access-control-allow-origin") == origin


def test_simulation_history_endpoint(client: TestClient):
    """Test simulation history listing endpoint."""
    response = client.get("/api/simulation/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_simulation_detail_not_found(client: TestClient):
    """Test simulation detail endpoint returns 404 for unknown simulation ID."""
    response = client.get("/api/simulation/unknown-uuid-12345")
    assert response.status_code == 404


def test_simulation_snapshots_endpoint(client: TestClient):
    """Test simulation snapshots retrieval endpoint."""
    response = client.get("/api/simulation/any-id/snapshots?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_simulation_decisions_endpoint(client: TestClient):
    """Test simulation decisions retrieval endpoint."""
    response = client.get("/api/simulation/any-id/decisions?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_analytics_summary_endpoint(client: TestClient):
    """Test platform analytics summary endpoint."""
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_simulations" in data
    assert "controllers" in data


def test_controller_comparison_endpoint(client: TestClient):
    """Test controller comparison endpoint returns structured data for charting."""
    response = client.get("/api/analytics/controller-comparison")
    assert response.status_code == 200
    data = response.json()
    assert "controllers" in data
    assert "sample_count" in data


def test_real_sumo_simulation_dqn_integration(client: TestClient):
    """Integration test: Run real SUMO simulation with DQN controller to completion, check AI telemetry and DB persistence."""
    start_resp = client.post(
        "/api/simulation/start",
        json={"controller": "dqn", "steps": 10, "seed": 42},
    )
    assert start_resp.status_code == 200
    sim_id = start_resp.json()["simulation_id"]

    # Poll status until completed (timeout 15s)
    start_time = time.time()
    completed = False
    while time.time() - start_time < 15.0:
        status_resp = client.get("/api/simulation/status")
        assert status_resp.status_code == 200
        s_data = status_resp.json()
        if s_data["status"] == "completed":
            completed = True
            break
        time.sleep(0.3)

    assert completed, "DQN simulation did not complete in expected time window"

    # Verify latest traffic snapshot includes AI decision object
    traffic_resp = client.get("/api/traffic/current")
    assert traffic_resp.status_code == 200
    traffic_data = traffic_resp.json()
    assert traffic_data["simulation_id"] == sim_id
    assert traffic_data["controller"] == "DQN-ReinforcementLearning"
    assert traffic_data["ai"] is not None
    assert "action" in traffic_data["ai"]
    assert "action_id" in traffic_data["ai"]
    assert "approved" in traffic_data["ai"]

    # Verify final aggregate result
    result_resp = client.get("/api/simulation/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["status"] == "completed"
    assert result_data["controller"] == "dqn"
    assert "metrics" in result_data

    # Verify persistent MongoDB records
    detail_resp = client.get(f"/api/simulation/{sim_id}")
    if detail_resp.status_code == 200:
        detail_data = detail_resp.json()
        assert detail_data["simulation_id"] == sim_id
        assert detail_data["status"] == "completed"
        assert detail_data["controller"] == "dqn"

    snaps_resp = client.get(f"/api/simulation/{sim_id}/snapshots")
    assert snaps_resp.status_code == 200
    assert isinstance(snaps_resp.json(), list)

    decisions_resp = client.get(f"/api/simulation/{sim_id}/decisions")
    assert decisions_resp.status_code == 200
    assert isinstance(decisions_resp.json(), list)



def test_controllers_endpoint(client: TestClient):
    """Test controllers listing returns fixed, adaptive, and dqn controllers."""
    response = client.get("/api/controllers")
    assert response.status_code == 200
    controllers = response.json()
    assert len(controllers) == 3
    controller_ids = [c["id"] for c in controllers]
    assert "fixed" in controller_ids
    assert "adaptive" in controller_ids
    assert "dqn" in controller_ids

    # DQN should report available since model checkpoints exist
    dqn_info = next(c for c in controllers if c["id"] == "dqn")
    assert dqn_info["available"] is True
    assert dqn_info["type"] == "reinforcement_learning"


def test_simulation_status_idle(client: TestClient):
    """Test status endpoint reports idle when no simulation is active."""
    response = client.get("/api/simulation/status")
    assert response.status_code == 200
    data = response.json()
    assert data["running"] is False
    assert data["status"] == "idle"
    assert data["simulation_id"] is None


def test_traffic_current_when_idle(client: TestClient):
    """Test traffic current endpoint returns 404 when no snapshot exists."""
    response = client.get("/api/traffic/current")
    assert response.status_code == 404


def test_simulation_result_when_idle(client: TestClient):
    """Test simulation result endpoint returns 404 when no completed run exists."""
    response = client.get("/api/simulation/result")
    assert response.status_code == 404


def test_invalid_controller_validation(client: TestClient):
    """Test starting a simulation with an unknown controller returns 422."""
    response = client.post(
        "/api/simulation/start",
        json={"controller": "invalid_controller", "steps": 30, "seed": 42},
    )
    assert response.status_code == 422


def test_invalid_steps_validation(client: TestClient):
    """Test starting a simulation with non-positive steps returns 422."""
    response = client.post(
        "/api/simulation/start",
        json={"controller": "fixed", "steps": 0, "seed": 42},
    )
    assert response.status_code == 422

    response_large = client.post(
        "/api/simulation/start",
        json={"controller": "fixed", "steps": 10000, "seed": 42},
    )
    assert response_large.status_code == 422


def test_stop_when_idle(client: TestClient):
    """Test stopping when idle returns clean status='idle' without error."""
    response = client.post("/api/simulation/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "idle"


def test_concurrency_rejection_and_stop(client: TestClient):
    """Test starting a simulation, rejecting concurrent second start with 409, and stopping cleanly."""
    start_resp = client.post(
        "/api/simulation/start",
        json={"controller": "fixed", "steps": 100, "seed": 42},
    )
    assert start_resp.status_code == 200
    sim_data = start_resp.json()
    assert sim_data["status"] == "started"
    assert sim_data["controller"] == "fixed"
    sim_id = sim_data["simulation_id"]

    # Immediate second start attempt must be rejected with 409 Conflict
    conflict_resp = client.post(
        "/api/simulation/start",
        json={"controller": "adaptive", "steps": 50, "seed": 42},
    )
    assert conflict_resp.status_code == 409

    # Stop simulation — returns "stopping" immediately (worker finishes asynchronously)
    stop_resp = client.post("/api/simulation/stop")
    assert stop_resp.status_code == 200
    stop_data = stop_resp.json()
    assert stop_data["status"] in ("stopping", "stopped", "idle")
    assert stop_data["simulation_id"] == sim_id


def test_websocket_lifecycle(client: TestClient):
    """Test WebSocket connection establishment, initial status broadcast, and ping/pong."""
    with client.websocket_connect("/ws/traffic") as websocket:
        initial_msg = websocket.receive_json()
        assert initial_msg["type"] == "status_update"
        assert "data" in initial_msg
        assert initial_msg["data"]["status"] == "idle"

        # Send ping
        websocket.send_json({"type": "ping"})
        pong_msg = websocket.receive_json()
        assert pong_msg["type"] == "pong"


def test_real_sumo_simulation_adaptive_integration(client: TestClient):
    """Integration test: Run real SUMO simulation with Adaptive controller to completion."""
    start_resp = client.post(
        "/api/simulation/start",
        json={"controller": "adaptive", "steps": 10, "seed": 42},
    )
    assert start_resp.status_code == 200
    sim_id = start_resp.json()["simulation_id"]

    # Poll status until completed (timeout 15s)
    start_time = time.time()
    completed = False
    while time.time() - start_time < 15.0:
        status_resp = client.get("/api/simulation/status")
        assert status_resp.status_code == 200
        s_data = status_resp.json()
        if s_data["status"] == "completed":
            completed = True
            break
        time.sleep(0.3)

    assert completed, "Simulation did not complete in expected time window"

    # Verify latest traffic snapshot
    traffic_resp = client.get("/api/traffic/current")
    assert traffic_resp.status_code == 200
    traffic_data = traffic_resp.json()
    assert traffic_data["simulation_id"] == sim_id
    assert traffic_data["controller"] == "Rule-Based Adaptive"
    assert "vehicles" in traffic_data

    assert "queues" in traffic_data
    assert "speed" in traffic_data
    assert "signal" in traffic_data
    assert traffic_data["signal"]["state"] in {"green", "yellow", "red"}

    # Verify final aggregate result
    result_resp = client.get("/api/simulation/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["simulation_id"] == sim_id
    assert result_data["status"] == "completed"
    assert "metrics" in result_data
    metrics = result_data["metrics"]
    assert "total_vehicles_served" in metrics
    assert "average_queue" in metrics
    assert "average_waiting_time" in metrics
    assert "phase_changes" in metrics



def test_real_sumo_simulation_dqn_integration(client: TestClient):
    """Integration test: Run real SUMO simulation with DQN controller to completion and check AI telemetry."""
    start_resp = client.post(
        "/api/simulation/start",
        json={"controller": "dqn", "steps": 10, "seed": 42},
    )
    assert start_resp.status_code == 200
    sim_id = start_resp.json()["simulation_id"]

    # Poll status until completed (timeout 15s)
    start_time = time.time()
    completed = False
    while time.time() - start_time < 15.0:
        status_resp = client.get("/api/simulation/status")
        assert status_resp.status_code == 200
        s_data = status_resp.json()
        if s_data["status"] == "completed":
            completed = True
            break
        time.sleep(0.3)

    assert completed, "DQN simulation did not complete in expected time window"

    # Verify latest traffic snapshot includes AI decision object
    traffic_resp = client.get("/api/traffic/current")
    assert traffic_resp.status_code == 200
    traffic_data = traffic_resp.json()
    assert traffic_data["simulation_id"] == sim_id
    assert traffic_data["controller"] == "DQN-ReinforcementLearning"
    assert traffic_data["ai"] is not None
    assert "action" in traffic_data["ai"]
    assert "action_id" in traffic_data["ai"]
    assert "approved" in traffic_data["ai"]

    # Verify final aggregate result
    result_resp = client.get("/api/simulation/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["status"] == "completed"
    assert result_data["controller"] == "dqn"
    assert "metrics" in result_data

