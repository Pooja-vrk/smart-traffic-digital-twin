"""Repository for congestion prediction results."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import pymongo

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)


class PredictionRepository:
    """Manages persistence of congestion prediction results."""

    @staticmethod
    def insert_prediction(prediction: Dict[str, Any]) -> bool:
        """Insert a single congestion prediction result."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return False

        try:
            doc = dict(prediction)
            doc.pop("_id", None)
            db_manager.sync_db.congestion_predictions.insert_one(doc)
            return True
        except Exception as exc:
            logger.debug("Failed to insert prediction: %s", exc)
            return False

    @staticmethod
    def get_predictions(
        simulation_id: Optional[str] = None,
        intersection_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve prediction results with optional filters."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return []

        try:
            query: Dict[str, Any] = {}
            if simulation_id:
                query["simulation_id"] = simulation_id
            if intersection_id:
                query["intersection_id"] = intersection_id

            cursor = (
                db_manager.sync_db.congestion_predictions.find(query, {"_id": 0})
                .sort("timestamp", pymongo.DESCENDING)
                .limit(min(limit, 1000))
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("Failed to fetch predictions: %s", exc)
            return []

    @staticmethod
    def get_recent_predictions(limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve the most recent prediction results."""
        return PredictionRepository.get_predictions(limit=limit)