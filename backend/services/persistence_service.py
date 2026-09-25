"""Digital twin persistence service providing failure-isolated persistence operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.database.repositories.intersection_repository import IntersectionRepository
from backend.database.repositories.signal_repository import SignalRepository
from backend.database.repositories.simulation_repository import SimulationRepository
from backend.database.repositories.traffic_repository import TrafficRepository

logger = logging.getLogger(__name__)


class PersistenceService:
    """Coordinates persistence across simulation runs, snapshots, and decisions with full failure isolation."""

    INTERSECTION_ID = "INT-001"

    @classmethod
    def start_simulation_run(
        cls,
        simulation_id: str,
        controller: str,
        seed: int,
        steps: int,
        gui: bool,
    ) -> None:
        """Record simulation initialization in database."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            run_doc = {
                "simulation_id": simulation_id,
                "intersection_id": cls.INTERSECTION_ID,
                "controller": controller,
                "seed": seed,
                "steps": steps,
                "gui": gui,
                "status": "running",
                "started_at": now,
                "completed_at": None,
                "duration_seconds": None,
                "metrics": None,
            }
            SimulationRepository.create_run(run_doc)
        except Exception as exc:
            logger.warning("Persistence error on start_simulation_run (%s): %s", simulation_id, exc)

    @classmethod
    def save_traffic_snapshot(cls, snapshot_dict: Dict[str, Any]) -> None:
        """Persist instantaneous traffic telemetry snapshot."""
        try:
            doc = dict(snapshot_dict)
            doc["intersection_id"] = cls.INTERSECTION_ID
            if "timestamp" not in doc:
                doc["timestamp"] = datetime.now(timezone.utc).isoformat()
            TrafficRepository.insert_snapshot(doc)
        except Exception as exc:
            logger.debug("Persistence error on save_traffic_snapshot: %s", exc)

    @classmethod
    def save_signal_decision(
        cls,
        simulation_id: str,
        simulation_time: float,
        controller: str,
        action_id: int,
        action_name: str,
        requested_phase: int,
        approved: bool,
        current_phase: int,
        elapsed_green: float,
        reason: Optional[str] = None,
    ) -> None:
        """Persist a signal timing or AI controller action decision."""
        try:
            decision_doc = {
                "simulation_id": simulation_id,
                "intersection_id": cls.INTERSECTION_ID,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "simulation_time": simulation_time,
                "controller": controller,
                "action_id": action_id,
                "action": action_name,
                "requested_phase": requested_phase,
                "approved": approved,
                "reason": reason,
                "current_phase": current_phase,
                "elapsed_green": elapsed_green,
            }
            SignalRepository.insert_decision(decision_doc)
        except Exception as exc:
            logger.debug("Persistence error on save_signal_decision: %s", exc)

    @classmethod
    def complete_simulation_run(
        cls,
        simulation_id: str,
        status: str,
        final_step: int,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Finalize simulation run record with terminal status and aggregate performance metrics."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            update_data = {
                "status": status,
                "completed_at": now,
                "duration_seconds": float(final_step),
                "metrics": metrics,
            }
            SimulationRepository.update_run(simulation_id, update_data)
        except Exception as exc:
            logger.warning("Persistence error on complete_simulation_run (%s): %s", simulation_id, exc)

    @classmethod
    def get_simulation_history(
        cls,
        controller: Optional[str] = None,
        seed: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent simulation runs from database."""
        return SimulationRepository.list_runs(
            controller=controller,
            seed=seed,
            status=status,
            limit=limit,
        )

    @classmethod
    def get_simulation_detail(cls, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve details and metrics of a specific simulation run."""
        return SimulationRepository.get_run(simulation_id)

    @classmethod
    def get_simulation_snapshots(cls, simulation_id: str, limit: int = 300) -> List[Dict[str, Any]]:
        """Retrieve chronological traffic snapshots for a simulation run."""
        return TrafficRepository.get_snapshots(simulation_id, limit=limit)

    @classmethod
    def get_simulation_decisions(cls, simulation_id: str, limit: int = 300) -> List[Dict[str, Any]]:
        """Retrieve chronological signal decisions for a simulation run."""
        return SignalRepository.get_decisions(simulation_id, limit=limit)

    @classmethod
    def get_analytics_summary(cls) -> Dict[str, Any]:
        """Compute aggregate platform KPI statistics across completed simulation runs."""
        return SimulationRepository.get_analytics_summary()

    @classmethod
    def get_controller_comparison(cls) -> Dict[str, Any]:
        """Compute mean benchmark comparison metrics across controllers."""
        return SimulationRepository.get_controller_comparison()
