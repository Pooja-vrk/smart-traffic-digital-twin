"""Database seeding and index initialization utility script."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.connection import db_manager
from backend.database.repositories.intersection_repository import IntersectionRepository



def seed_database() -> int:
    """Connect to MongoDB, create indexes, and seed default intersection metadata."""
    print("Connecting to MongoDB...")
    connected = db_manager.connect()
    if not connected:
        print("ERROR: Could not connect to MongoDB. Ensure MongoDB service is running.")
        return 1

    print("Creating database indexes across collections...")
    db_manager.create_indexes()

    print("Upserting default 4-way intersection (INT-001)...")
    intersection = IntersectionRepository.upsert_default_intersection()
    print(f"Intersection '{intersection['intersection_id']}' ({intersection['name']}) verified.")

    db_manager.disconnect()
    print("MongoDB database seeding and index setup COMPLETED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    sys.exit(seed_database())
