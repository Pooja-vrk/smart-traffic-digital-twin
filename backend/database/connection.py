"""MongoDB connection and lifecycle manager."""

from __future__ import annotations

import logging
from typing import Optional
import pymongo
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.database import Database

from backend.config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages asynchronous and synchronous connections to MongoDB with automatic failure isolation."""

    def __init__(self) -> None:
        self.motor_client: Optional[AsyncIOMotorClient] = None
        self.async_db: Optional[AsyncIOMotorDatabase] = None
        self.sync_client: Optional[pymongo.MongoClient] = None
        self.sync_db: Optional[Database] = None
        self._available: bool = False
        self._db_name: str = settings.DATABASE_NAME
        self._uri: str = settings.MONGODB_URI

    @property
    def is_available(self) -> bool:
        """Check whether MongoDB is connected and operational."""
        return self._available

    def connect(self, uri: Optional[str] = None, db_name: Optional[str] = None) -> bool:
        """Initialize MongoDB client connections and verify ping."""
        self._uri = uri or settings.MONGODB_URI
        self._db_name = db_name or settings.DATABASE_NAME

        try:
            # Verify synchronous ping first with short timeout
            self.sync_client = pymongo.MongoClient(
                self._uri,
                serverSelectionTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
            )
            self.sync_client.admin.command("ping")
            self.sync_db = self.sync_client[self._db_name]

            # Initialize asynchronous Motor client
            self.motor_client = AsyncIOMotorClient(
                self._uri,
                serverSelectionTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
            )
            self.async_db = self.motor_client[self._db_name]
            self._available = True

            logger.info("Connected to MongoDB database '%s' at %s", self._db_name, self._uri)
            return True

        except Exception as exc:
            logger.warning("MongoDB connection failed (%s). Operating in degraded mode (in-memory only).", exc)
            self._available = False
            self.sync_client = None
            self.sync_db = None
            self.motor_client = None
            self.async_db = None
            return False

    def disconnect(self) -> None:
        """Safely close all MongoDB client connections."""
        if self.motor_client is not None:
            self.motor_client.close()
            self.motor_client = None
            self.async_db = None
        if self.sync_client is not None:
            self.sync_client.close()
            self.sync_client = None
            self.sync_db = None
        self._available = False
        logger.info("Closed MongoDB database connections.")

    def create_indexes(self) -> None:
        """Create necessary performance and query indexes across all collections."""
        if not self._available or self.sync_db is None:
            return

        try:
            # 1. intersections: unique intersection_id
            self.sync_db.intersections.create_index("intersection_id", unique=True)

            # 2. simulation_runs: unique simulation_id, compound/single on controller, seed, status
            self.sync_db.simulation_runs.create_index("simulation_id", unique=True)
            self.sync_db.simulation_runs.create_index([("controller", pymongo.ASCENDING), ("completed_at", pymongo.DESCENDING)])
            self.sync_db.simulation_runs.create_index([("status", pymongo.ASCENDING)])

            # 3. traffic_snapshots: compound simulation_id + simulation_time, simulation_id + timestamp
            self.sync_db.traffic_snapshots.create_index([
                ("simulation_id", pymongo.ASCENDING),
                ("simulation_time", pymongo.ASCENDING),
            ])
            self.sync_db.traffic_snapshots.create_index([
                ("simulation_id", pymongo.ASCENDING),
                ("timestamp", pymongo.ASCENDING),
            ])

            # 4. signal_decisions: compound simulation_id + simulation_time
            self.sync_db.signal_decisions.create_index([
                ("simulation_id", pymongo.ASCENDING),
                ("simulation_time", pymongo.ASCENDING),
            ])

            # 5. congestion_predictions: compound simulation_id + simulation_time, timestamp, intersection_id + timestamp
            self.sync_db.congestion_predictions.create_index([
                ("simulation_id", pymongo.ASCENDING),
                ("simulation_time", pymongo.ASCENDING),
            ])
            self.sync_db.congestion_predictions.create_index("timestamp")
            self.sync_db.congestion_predictions.create_index([
                ("intersection_id", pymongo.ASCENDING),
                ("timestamp", pymongo.DESCENDING),
            ])

            logger.info("MongoDB indexes verified and created successfully.")
        except Exception as exc:
            logger.warning("Failed to create MongoDB indexes: %s", exc)


# Global DatabaseManager singleton
db_manager = DatabaseManager()
