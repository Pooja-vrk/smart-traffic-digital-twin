"""Repository for intersection metadata persistence."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.database.connection import db_manager

logger = logging.getLogger(__name__)

DEFAULT_INTERSECTION_DATA: Dict[str, Any] = {
    "intersection_id": "INT-001",
    "name": "Main Street 4-Way Intersection",
    "location": {
        "type": "simulated",
        "description": "SUMO 4-way urban signalized intersection",
    },
    "approaches": ["north", "south", "east", "west"],
    "phases": [
        {"index": 0, "name": "NORTH_SOUTH_GREEN", "state": "GrGr"},
        {"index": 1, "name": "NORTH_SOUTH_YELLOW", "state": "yryr"},
        {"index": 2, "name": "EAST_WEST_GREEN", "state": "rGrG"},
        {"index": 3, "name": "EAST_WEST_YELLOW", "state": "ryry"},
    ],
}


class IntersectionRepository:
    """Provides database queries and seeding for simulated intersection configurations."""

    @staticmethod
    def get_intersection(intersection_id: str = "INT-001") -> Optional[Dict[str, Any]]:
        """Retrieve intersection document by identifier."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return DEFAULT_INTERSECTION_DATA

        try:
            doc = db_manager.sync_db.intersections.find_one(
                {"intersection_id": intersection_id},
                {"_id": 0},
            )
            return doc or DEFAULT_INTERSECTION_DATA
        except Exception as exc:
            logger.warning("Error fetching intersection %s: %s", intersection_id, exc)
            return DEFAULT_INTERSECTION_DATA

    @staticmethod
    def upsert_default_intersection() -> Dict[str, Any]:
        """Seed or update the standard 4-way intersection document."""
        if not db_manager.is_available or db_manager.sync_db is None:
            return DEFAULT_INTERSECTION_DATA

        now = datetime.now(timezone.utc).isoformat()
        doc = dict(DEFAULT_INTERSECTION_DATA)
        doc["updated_at"] = now

        try:
            db_manager.sync_db.intersections.update_one(
                {"intersection_id": doc["intersection_id"]},
                {
                    "$set": doc,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            logger.info("Upserted default intersection INT-001")
            return doc
        except Exception as exc:
            logger.warning("Error upserting intersection: %s", exc)
            return DEFAULT_INTERSECTION_DATA
