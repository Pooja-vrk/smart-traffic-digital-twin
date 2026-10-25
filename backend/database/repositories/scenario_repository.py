"""Repository for Scenario Lab experiments with MongoDB and in-memory fallback."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import pymongo

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class ScenarioRepository:
    """Manages CRUD persistence for scenario experiment runs."""

    # In-memory storage fallback for degraded mode / tests
    _in_memory_store: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def create_scenario(cls, doc: Dict[str, Any]) -> bool:
        """Insert a new scenario experiment record."""
        scenario_id = doc.get("scenario_id")
        if not scenario_id:
            return False

        clean_doc = dict(doc)
        clean_doc.pop("_id", None)
        cls._in_memory_store[scenario_id] = dict(clean_doc)

        if not db_manager.is_available or db_manager.sync_db is None:
            return True

        try:
            db_manager.sync_db.scenarios.insert_one(clean_doc)
            return True
        except Exception as exc:
            logger.warning("Failed to persist scenario %s in MongoDB: %s", scenario_id, exc)
            return True  # Fallback retained in memory

    @classmethod
    def update_scenario(cls, scenario_id: str, update_data: Dict[str, Any]) -> bool:
        """Update scenario record status, metrics, and completion data."""
        clean_update = {k: v for k, v in update_data.items() if k != "_id"}

        if scenario_id in cls._in_memory_store:
            cls._in_memory_store[scenario_id].update(clean_update)

        if not db_manager.is_available or db_manager.sync_db is None:
            return True

        try:
            db_manager.sync_db.scenarios.update_one(
                {"scenario_id": scenario_id},
                {"$set": clean_update},
            )
            return True
        except Exception as exc:
            logger.warning("Failed to update scenario %s in MongoDB: %s", scenario_id, exc)
            return True

    @classmethod
    def get_scenario(cls, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific scenario run by ID."""
        if db_manager.is_available and db_manager.sync_db is not None:
            try:
                doc = db_manager.sync_db.scenarios.find_one(
                    {"scenario_id": scenario_id},
                    {"_id": 0},
                )
                if doc:
                    return doc
            except Exception as exc:
                logger.warning("Failed to query scenario %s in MongoDB: %s", scenario_id, exc)

        return cls._in_memory_store.get(scenario_id)

    @classmethod
    def list_scenarios(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """List historical scenario runs ordered by start time descending."""
        if db_manager.is_available and db_manager.sync_db is not None:
            try:
                cursor = (
                    db_manager.sync_db.scenarios.find({}, {"_id": 0})
                    .sort("created_at", pymongo.DESCENDING)
                    .limit(min(limit, 100))
                )
                items = list(cursor)
                if items:
                    return items
            except Exception as exc:
                logger.warning("Failed to list scenarios from MongoDB: %s", exc)

        # Fallback to in-memory store
        items = list(cls._in_memory_store.values())
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items[:limit]

    @classmethod
    def clear_in_memory(cls) -> None:
        """Clear in-memory records (used in unit test isolation)."""
        cls._in_memory_store.clear()
