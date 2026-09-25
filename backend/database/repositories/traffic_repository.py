"""Repository for periodic traffic digital twin state snapshots."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
import pymongo

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class TrafficRepository:
    """Manages insertion and query of high-resolution traffic telemetry snapshots."""

    @staticmethod
    def insert_snapshot(snapshot: Dict[str, Any]) -> bool:
        """Insert a single traffic telemetry snapshot."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return False

        try:
            doc = dict(snapshot)
            doc.pop("_id", None)
            db_manager.sync_db.traffic_snapshots.insert_one(doc)
            return True
        except Exception as exc:
            logger.debug("Failed to insert traffic snapshot: %s", exc)
            return False

    @staticmethod
    def insert_snapshots_batch(snapshots: List[Dict[str, Any]]) -> bool:
        """Batch insert multiple traffic telemetry snapshots."""
        if not db_manager.is_available or db_manager.sync_db is None or not snapshots:
            return False

        try:
            clean_docs = []
            for s in snapshots:
                d = dict(s)
                d.pop("_id", None)
                clean_docs.append(d)
            db_manager.sync_db.traffic_snapshots.insert_many(clean_docs, ordered=False)
            return True
        except Exception as exc:
            logger.debug("Failed to batch insert traffic snapshots: %s", exc)
            return False

    @staticmethod
    def get_snapshots(simulation_id: str, limit: int = 300) -> List[Dict[str, Any]]:
        """Retrieve chronological traffic snapshots for a specific simulation run."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return []

        try:
            cursor = (
                db_manager.sync_db.traffic_snapshots.find(
                    {"simulation_id": simulation_id},
                    {"_id": 0},
                )
                .sort("simulation_time", pymongo.ASCENDING)
                .limit(min(limit, 1000))
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("Failed to fetch snapshots for simulation %s: %s", simulation_id, exc)
            return []
