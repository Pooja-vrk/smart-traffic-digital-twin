"""Repository for simulation experiment runs and analytical aggregations."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import pymongo

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class SimulationRepository:
    """Manages CRUD queries and analytics over simulation_runs collection."""

    @staticmethod
    def create_run(run_data: Dict[str, Any]) -> bool:
        """Insert a new simulation run document at session start."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return False

        try:
            doc = dict(run_data)
            # Remove any raw Mongo _id if provided
            doc.pop("_id", None)
            db_manager.sync_db.simulation_runs.insert_one(doc)
            return True
        except Exception as exc:
            logger.warning("Failed to create simulation_run %s: %s", run_data.get("simulation_id"), exc)
            return False

    @staticmethod
    def update_run(simulation_id: str, update_data: Dict[str, Any]) -> bool:
        """Update simulation run status, completion timestamp, and final metrics."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return False

        try:
            clean_update = {k: v for k, v in update_data.items() if k != "_id"}
            db_manager.sync_db.simulation_runs.update_one(
                {"simulation_id": simulation_id},
                {"$set": clean_update},
            )
            return True
        except Exception as exc:
            logger.warning("Failed to update simulation_run %s: %s", simulation_id, exc)
            return False

    @staticmethod
    def get_run(simulation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific simulation run document by its UUID."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return None

        try:
            doc = db_manager.sync_db.simulation_runs.find_one(
                {"simulation_id": simulation_id},
                {"_id": 0},
            )
            return doc
        except Exception as exc:
            logger.warning("Failed to fetch simulation_run %s: %s", simulation_id, exc)
            return None

    @staticmethod
    def list_runs(
        controller: Optional[str] = None,
        seed: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List historical simulation runs matching optional filters."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return []

        query: Dict[str, Any] = {}
        if controller:
            query["controller"] = controller
        if seed is not None:
            query["seed"] = seed
        if status:
            query["status"] = status

        try:
            cursor = (
                db_manager.sync_db.simulation_runs.find(query, {"_id": 0})
                .sort("started_at", pymongo.DESCENDING)
                .limit(min(limit, 500))
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("Failed to list simulation runs: %s", exc)
            return []

    @staticmethod
    def get_analytics_summary() -> Dict[str, Any]:
        """Compute aggregate summary stats from stored completed simulations."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return {
                "total_simulations": 0,
                "controllers": {"fixed": 0, "adaptive": 0, "dqn": 0},
                "best_throughput": None,
                "lowest_average_queue": None,
                "lowest_average_wait": None,
                "total_vehicles_served": 0,
            }

        try:
            completed_runs = list(
                db_manager.sync_db.simulation_runs.find(
                    {"status": "completed"},
                    {"_id": 0, "controller": 1, "metrics": 1},
                )
            )

            if not completed_runs:
                return {
                    "total_simulations": 0,
                    "controllers": {"fixed": 0, "adaptive": 0, "dqn": 0},
                    "best_throughput": None,
                    "lowest_average_queue": None,
                    "lowest_average_wait": None,
                    "total_vehicles_served": 0,
                }

            controller_counts: Dict[str, int] = {"fixed": 0, "adaptive": 0, "dqn": 0}
            throughputs: List[int] = []
            avg_queues: List[float] = []
            avg_waits: List[float] = []
            tot_served = 0

            for run in completed_runs:
                c = run.get("controller", "unknown")
                controller_counts[c] = controller_counts.get(c, 0) + 1

                m = run.get("metrics", {})
                if m:
                    served = m.get("total_vehicles_served") or m.get("throughput") or 0
                    throughputs.append(served)
                    tot_served += served

                    q = m.get("average_queue")
                    if q is not None:
                        avg_queues.append(q)

                    w = m.get("average_waiting_time") or m.get("average_wait")
                    if w is not None:
                        avg_waits.append(w)

            return {
                "total_simulations": len(completed_runs),
                "controllers": controller_counts,
                "best_throughput": max(throughputs) if throughputs else None,
                "lowest_average_queue": round(min(avg_queues), 2) if avg_queues else None,
                "lowest_average_wait": round(min(avg_waits), 2) if avg_waits else None,
                "total_vehicles_served": tot_served,
            }

        except Exception as exc:
            logger.warning("Failed to calculate analytics summary: %s", exc)
            return {
                "total_simulations": 0,
                "controllers": {"fixed": 0, "adaptive": 0, "dqn": 0},
                "best_throughput": None,
                "lowest_average_queue": None,
                "lowest_average_wait": None,
                "total_vehicles_served": 0,
            }

    @staticmethod
    def get_controller_comparison() -> Dict[str, Any]:
        """Aggregate mean metrics grouped by controller for benchmarking visualization."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return {"controllers": {}, "sample_count": 0}

        try:
            completed_runs = list(
                db_manager.sync_db.simulation_runs.find(
                    {"status": "completed"},
                    {"_id": 0, "controller": 1, "metrics": 1},
                )
            )

            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for run in completed_runs:
                c = run.get("controller", "unknown")
                m = run.get("metrics")
                if m:
                    grouped.setdefault(c, []).append(m)

            comparison: Dict[str, Any] = {}
            for c, metrics_list in grouped.items():
                n = len(metrics_list)
                comparison[c] = {
                    "runs_count": n,
                    "throughput": round(sum(m.get("total_vehicles_served", m.get("throughput", 0)) for m in metrics_list) / n, 2),
                    "average_queue": round(sum(m.get("average_queue", 0) for m in metrics_list) / n, 2),
                    "peak_queue": round(sum(m.get("max_queue", m.get("peak_queue", 0)) for m in metrics_list) / n, 2),
                    "average_wait": round(sum(m.get("average_waiting_time", m.get("average_wait", 0)) for m in metrics_list) / n, 2),
                    "average_delay": round(sum(m.get("average_delay", 0) for m in metrics_list) / n, 2),
                    "average_speed": round(sum(m.get("average_speed", 0) for m in metrics_list) / n, 2),
                    "phase_changes": round(sum(m.get("phase_changes", 0) for m in metrics_list) / n, 2),
                    "estimated_co2_kg": round(sum(m.get("total_co2_emission_kg", m.get("estimated_co2_kg", 0)) for m in metrics_list) / n, 2),
                }

            return {
                "controllers": comparison,
                "sample_count": len(completed_runs),
            }

        except Exception as exc:
            logger.warning("Failed to calculate controller comparison: %s", exc)
            return {"controllers": {}, "sample_count": 0}
