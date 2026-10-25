"""Repository for agentic AI decision records and explainability traces."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import pymongo

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class DecisionRepository:
    """Manages persistent storage, chronological querying, and multi-criteria filtering of explainable decision records."""

    COLLECTION_NAME = "agentic_decisions"

    @classmethod
    def insert_decision(cls, decision: Dict[str, Any]) -> bool:
        """Insert a single complete AgenticDecisionRecord dictionary."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return False

        try:
            doc = dict(decision)
            doc.pop("_id", None)
            db_manager.sync_db[cls.COLLECTION_NAME].insert_one(doc)
            return True
        except Exception as exc:
            logger.debug("Failed to insert agentic decision: %s", exc)
            return False

    @classmethod
    def insert_decisions_batch(cls, decisions: List[Dict[str, Any]]) -> bool:
        """Batch insert multiple AgenticDecisionRecord dictionaries."""
        if not db_manager.is_available or db_manager.sync_db is None or not decisions:
            return False

        try:
            clean_docs = []
            for d in decisions:
                doc = dict(d)
                doc.pop("_id", None)
                clean_docs.append(doc)
            db_manager.sync_db[cls.COLLECTION_NAME].insert_many(clean_docs, ordered=False)
            return True
        except Exception as exc:
            logger.debug("Failed to batch insert agentic decisions: %s", exc)
            return False

    @classmethod
    def get_decisions(
        cls,
        simulation_id: str,
        controller: Optional[str] = None,
        safety_override_only: bool = False,
        emergency_only: bool = False,
        skip: int = 0,
        limit: int = 300,
    ) -> List[Dict[str, Any]]:
        """Retrieve chronological explainable decision records with multi-criteria filtering."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return []

        try:
            query: Dict[str, Any] = {"simulation_id": simulation_id}
            if controller:
                query["controller"] = {"$regex": f"^{controller}$", "$options": "i"}
            if safety_override_only:
                query["is_safety_override"] = True
            if emergency_only:
                query["emergency.active"] = True

            cursor = (
                db_manager.sync_db[cls.COLLECTION_NAME]
                .find(query, {"_id": 0})
                .sort("simulation_time", pymongo.ASCENDING)
                .skip(skip)
                .limit(min(limit, 2000))
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("Failed to fetch agentic decisions for %s: %s", simulation_id, exc)
            return []

    @classmethod
    def get_decision_by_id(cls, simulation_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single decision record by decision_id."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return None

        try:
            doc = db_manager.sync_db[cls.COLLECTION_NAME].find_one(
                {"simulation_id": simulation_id, "decision_id": decision_id},
                {"_id": 0},
            )
            return doc
        except Exception as exc:
            logger.warning("Failed to fetch decision %s for %s: %s", decision_id, simulation_id, exc)
            return None

    @classmethod
    def count_decisions(
        cls,
        simulation_id: str,
        controller: Optional[str] = None,
        safety_override_only: bool = False,
        emergency_only: bool = False,
    ) -> int:
        """Count decision records matching filter criteria."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return 0

        try:
            query: Dict[str, Any] = {"simulation_id": simulation_id}
            if controller:
                query["controller"] = {"$regex": f"^{controller}$", "$options": "i"}
            if safety_override_only:
                query["is_safety_override"] = True
            if emergency_only:
                query["emergency.active"] = True

            return db_manager.sync_db[cls.COLLECTION_NAME].count_documents(query)
        except Exception as exc:
            logger.warning("Failed to count agentic decisions for %s: %s", simulation_id, exc)
            return 0
