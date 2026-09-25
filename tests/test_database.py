"""Unit and integration tests for MongoDB database connection, repositories, and persistence service."""

from __future__ import annotations

from datetime import datetime
import pytest
from backend.database.connection import DatabaseManager, db_manager
from backend.database.repositories.intersection_repository import IntersectionRepository
from backend.database.repositories.signal_repository import SignalRepository
from backend.database.repositories.simulation_repository import SimulationRepository
from backend.database.repositories.traffic_repository import TrafficRepository
from backend.services.persistence_service import PersistenceService


@pytest.fixture(autouse=True)
def ensure_db_connected():
    """Ensure database connection is initialized for tests."""
    db_manager.connect()
    yield
    # Cleanup test simulation records if any
    if db_manager.is_available and db_manager.sync_db is not None:
        db_manager.sync_db.simulation_runs.delete_many({"simulation_id": {"$regex": "^test-"}})
        db_manager.sync_db.traffic_snapshots.delete_many({"simulation_id": {"$regex": "^test-"}})
        db_manager.sync_db.signal_decisions.delete_many({"simulation_id": {"$regex": "^test-"}})


def test_database_connection_and_availability():
    """Test database manager connects and detects availability."""
    assert db_manager.is_available is True
    assert db_manager.sync_db is not None
    assert db_manager.async_db is not None


def test_create_indexes_idempotent():
    """Test index creation executes without error and is idempotent."""
    db_manager.create_indexes()
    if db_manager.is_available and db_manager.sync_db is not None:
        sim_indexes = db_manager.sync_db.simulation_runs.index_information()
        assert "simulation_id_1" in sim_indexes
        snap_indexes = db_manager.sync_db.traffic_snapshots.index_information()
        assert "simulation_id_1_simulation_time_1" in snap_indexes


def test_intersection_repository():
    """Test retrieving and upserting default intersection INT-001."""
    intersection = IntersectionRepository.upsert_default_intersection()
    assert intersection["intersection_id"] == "INT-001"
    assert "north" in intersection["approaches"]

    fetched = IntersectionRepository.get_intersection("INT-001")
    assert fetched is not None
    assert fetched["name"] == "Main Street 4-Way Intersection"


def test_simulation_repository_lifecycle():
    """Test create, update, get, and list operations in SimulationRepository."""
    sim_id = "test-sim-001"
    now_iso = datetime.utcnow().isoformat() + "Z"
    run_doc = {
        "simulation_id": sim_id,
        "intersection_id": "INT-001",
        "controller": "dqn",
        "seed": 42,
        "steps": 30,
        "gui": False,
        "status": "running",
        "started_at": now_iso,
    }
    created = SimulationRepository.create_run(run_doc)
    assert created is True

    fetched = SimulationRepository.get_run(sim_id)
    assert fetched is not None
    assert fetched["controller"] == "dqn"
    assert fetched["status"] == "running"

    # Update run to completed
    updated = SimulationRepository.update_run(sim_id, {
        "status": "completed",
        "completed_at": now_iso,
        "duration_seconds": 30.0,
        "metrics": {
            "total_vehicles_served": 25,
            "average_queue": 2.5,
            "average_waiting_time": 15.0,
            "phase_changes": 4,
        },
    })
    assert updated is True

    updated_run = SimulationRepository.get_run(sim_id)
    assert updated_run["status"] == "completed"
    assert updated_run["metrics"]["total_vehicles_served"] == 25

    # List runs
    runs = SimulationRepository.list_runs(controller="dqn", limit=50)
    assert any(r["simulation_id"] == sim_id for r in runs)


def test_traffic_repository_snapshots():
    """Test inserting and querying traffic telemetry snapshots."""
    sim_id = "test-sim-002"
    snapshots = [
        {
            "simulation_id": sim_id,
            "simulation_time": float(t),
            "step": t,
            "controller": "fixed",
            "vehicles": {"total": 5, "entered": 10, "completed": 5},
            "queues": {"north": 1, "south": 1, "east": 1, "west": 0, "total": 3, "peak": 3},
            "speed": {"average_mps": 10.5},
            "waiting": {"average_seconds": 5.0, "total_seconds": 25.0},
            "signal": {"phase_index": 0, "phase_name": "NORTH_SOUTH_GREEN", "state": "green", "elapsed_seconds": float(t)},
        }
        for t in range(1, 6)
    ]

    inserted = TrafficRepository.insert_snapshots_batch(snapshots)
    assert inserted is True

    fetched = TrafficRepository.get_snapshots(sim_id, limit=10)
    assert len(fetched) == 5
    assert fetched[0]["step"] == 1
    assert fetched[-1]["step"] == 5


def test_signal_repository_decisions():
    """Test inserting and querying signal decisions."""
    sim_id = "test-sim-003"
    decision = {
        "simulation_id": sim_id,
        "intersection_id": "INT-001",
        "timestamp": "2026-09-10T14:00:05Z",
        "simulation_time": 5.0,
        "controller": "dqn",
        "action_id": 1,
        "action": "SWITCH_NS",
        "requested_phase": 0,
        "approved": True,
        "reason": "DQN selected NS corridor",
        "current_phase": 0,
        "elapsed_green": 5.0,
    }
    inserted = SignalRepository.insert_decision(decision)
    assert inserted is True

    fetched = SignalRepository.get_decisions(sim_id, limit=10)
    assert len(fetched) == 1
    assert fetched[0]["action"] == "SWITCH_NS"
    assert fetched[0]["approved"] is True


def test_persistence_service_failure_isolation():
    """Test that persistence service handles database errors gracefully without raising exceptions."""
    # Test with non-existent / invalid operations
    PersistenceService.complete_simulation_run(
        simulation_id="non-existent-sim",
        status="completed",
        final_step=10,
        metrics=None,
    )
    # Ensure no exception is propagated
    assert True


def test_analytics_and_comparison_queries():
    """Test analytics summary and controller comparison aggregations."""
    summary = PersistenceService.get_analytics_summary()
    assert "total_simulations" in summary
    assert "controllers" in summary

    comparison = PersistenceService.get_controller_comparison()
    assert "controllers" in comparison
    assert "sample_count" in comparison
