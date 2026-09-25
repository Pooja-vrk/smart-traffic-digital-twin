"""Repository for traffic signal and AI decision logs."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
import pymongo

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class SignalRepository:
    """Manages storage and retrieval of controller and reinforcement learning signal decisions."""

    @staticmethod
    def insert_decision(decision: Dict[str, Any]) -> bool:
        """Insert a single signal decision record."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return False

        try:
            doc = dict(decision)
            doc.pop("_id", None)
            db_manager.sync_db.signal_decisions.insert_one(doc)
            return True
        except Exception as exc:
            logger.debug("Failed to insert signal decision: %s", exc)
            return False

    @staticmethod
    def get_decisions(simulation_id: str, limit: int = 300) -> List[Dict[str, Any]]:
        """Retrieve chronological signal decisions for a specific simulation run."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return []

        try:
            cursor = (
                db_manager.sync_db.signal_decisions.find(
                    {"simulation_id": simulation_id},
                    {"_id": 0},
                )
                .sort("simulation_time", pymongo.ASCENDING)
                .limit(min(limit, 1000))
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("Failed to fetch signal decisions for %s: %s", simulation_id, exc)
            return []
