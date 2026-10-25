"""Digital twin persistence service providing failure-isolated persistence operations."""

from __future__ import annotations

import collections
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.database.repositories.decision_repository import DecisionRepository
from backend.database.repositories.intersection_repository import IntersectionRepository
from backend.database.repositories.signal_repository import SignalRepository
from backend.database.repositories.simulation_repository import SimulationRepository
from backend.database.repositories.traffic_repository import TrafficRepository

logger = logging.getLogger(__name__)


class PersistenceService:
    """Coordinates persistence across simulation runs, snapshots, and decisions with full failure isolation."""

    INTERSECTION_ID = "INT-001"

    # In-memory buffer caches for fast test isolation and graceful fallback
    _in_memory_snapshots: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    _in_memory_decisions: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)

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
            sim_id = doc.get("simulation_id")
            doc["intersection_id"] = cls.INTERSECTION_ID
            if "timestamp" not in doc:
                doc["timestamp"] = datetime.now(timezone.utc).isoformat()

            # Store in in-memory fallback ring
            if sim_id:
                mem_list = cls._in_memory_snapshots[sim_id]
                mem_list.append(doc)
                if len(mem_list) > 2000:
                    cls._in_memory_snapshots[sim_id] = mem_list[-2000:]

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
        """Persist a signal timing or AI controller action decision (legacy schema)."""
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
    def save_agentic_decision(cls, decision_dict: Dict[str, Any]) -> None:
        """Persist a complete explainable AgenticDecisionRecord with fallback caching."""
        try:
            doc = dict(decision_dict)
            sim_id = doc.get("simulation_id")
            if "timestamp" not in doc:
                doc["timestamp"] = datetime.now(timezone.utc).isoformat()
            doc["intersection_id"] = cls.INTERSECTION_ID

            # Backward-compatibility mappings if missing
            if "action_id" not in doc:
                doc["action_id"] = doc.get("validated_phase", 0)
            if "action" not in doc:
                doc["action"] = doc.get("requested_action", "KEEP")
            if "approved" not in doc:
                doc["approved"] = (doc.get("validated_action") == "APPROVED")
            if "current_phase" not in doc:
                obs = doc.get("observation", {})
                doc["current_phase"] = obs.get("current_signal_phase", 0) if isinstance(obs, dict) else 0
            if "elapsed_green" not in doc:
                obs = doc.get("observation", {})
                doc["elapsed_green"] = obs.get("time_in_current_phase", 0.0) if isinstance(obs, dict) else 0.0
            if "reason" not in doc:
                doc["reason"] = doc.get("decision_reason", "")

            if sim_id:
                mem_list = cls._in_memory_decisions[sim_id]
                mem_list.append(doc)
                if len(mem_list) > 2000:
                    cls._in_memory_decisions[sim_id] = mem_list[-2000:]

            DecisionRepository.insert_decision(doc)
        except Exception as exc:
            logger.debug("Persistence error on save_agentic_decision: %s", exc)

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
        """Retrieve chronological traffic snapshots for a simulation run with in-memory fallback."""
        snaps = TrafficRepository.get_snapshots(simulation_id, limit=limit)
        if snaps:
            return snaps
        return cls._in_memory_snapshots.get(simulation_id, [])[:limit]

    @classmethod
    def get_simulation_decisions(
        cls,
        simulation_id: str,
        controller: Optional[str] = None,
        safety_override_only: bool = False,
        emergency_only: bool = False,
        skip: int = 0,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        """Retrieve chronological decisions with multi-criteria filtering."""
        # 1. Query rich DecisionRepository first
        decisions = DecisionRepository.get_decisions(
            simulation_id=simulation_id,
            controller=controller,
            safety_override_only=safety_override_only,
            emergency_only=emergency_only,
            skip=skip,
            limit=limit,
        )
        if decisions:
            return decisions

        # 2. Query in-memory fallback cache
        mem_list = cls._in_memory_decisions.get(simulation_id, [])
        if mem_list:
            filtered = mem_list
            if controller:
                filtered = [d for d in filtered if str(d.get("controller", "")).lower() == controller.lower()]
            if safety_override_only:
                filtered = [d for d in filtered if d.get("is_safety_override") is True]
            if emergency_only:
                filtered = [
                    d for d in filtered
                    if (isinstance(d.get("emergency"), dict) and d["emergency"].get("active") is True)
                ]
            return filtered[skip : skip + limit]

        # 3. Fallback to legacy SignalRepository if no rich decisions exist
        if not safety_override_only and not emergency_only and not controller:
            return SignalRepository.get_decisions(simulation_id, limit=limit)

        return []

    @classmethod
    def get_single_decision(cls, simulation_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve detailed decision record by simulation_id and decision_id."""
        dec = DecisionRepository.get_decision_by_id(simulation_id, decision_id)
        if dec:
            return dec
        for d in cls._in_memory_decisions.get(simulation_id, []):
            if d.get("decision_id") == decision_id:
                return d
        return None

    @classmethod
    def get_replay_frames(cls, simulation_id: str, limit: int = 1000) -> Dict[str, Any]:
        """Assemble time-synchronized offline telemetry and decision frames without running SUMO."""
        snapshots = cls.get_simulation_snapshots(simulation_id, limit=limit)
        decisions = cls.get_simulation_decisions(simulation_id, limit=limit)

        dec_by_step = {d.get("step"): d for d in decisions if "step" in d and d.get("step") is not None}
        dec_by_time = {round(float(d.get("simulation_time", 0.0)), 1): d for d in decisions if "simulation_time" in d}

        frames: List[Dict[str, Any]] = []
        for snap in snapshots:
            step = snap.get("step", 0)
            sim_time = round(float(snap.get("simulation_time", 0.0)), 1)
            dec = dec_by_step.get(step) or dec_by_time.get(sim_time)
            frames.append({
                "step": step,
                "simulation_time": snap.get("simulation_time", 0.0),
                "snapshot": snap,
                "decision": dec,
            })

        controller_name = (
            snapshots[0].get("controller") if snapshots else (
                decisions[0].get("controller") if decisions else "unknown"
            )
        )
        duration = float(frames[-1]["simulation_time"]) if frames else 0.0

        return {
            "simulation_id": simulation_id,
            "controller": controller_name,
            "total_frames": len(frames),
            "duration_seconds": duration,
            "frames": frames,
        }

    @classmethod
    def get_analytics_summary(cls) -> Dict[str, Any]:
        """Compute aggregate platform KPI statistics across completed simulation runs."""
        return SimulationRepository.get_analytics_summary()

    @classmethod
    def get_controller_comparison(cls) -> Dict[str, Any]:
        """Compute mean benchmark comparison metrics across controllers."""
        return SimulationRepository.get_controller_comparison()
