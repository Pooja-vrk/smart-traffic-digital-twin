"""System health and binary availability endpoint."""

from __future__ import annotations

import logging
from typing import Any, Dict
from fastapi import APIRouter
import sumolib

from backend.config.settings import settings
from backend.database.connection import db_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Health"])


@router.get("/health", summary="Health Check")
async def health_check() -> Dict[str, Any]:
    """Check backend operational health, SUMO binary availability, and MongoDB connectivity."""
    sumo_available = False
    try:
        binary_path = sumolib.checkBinary("sumo")
        sumo_available = binary_path is not None and len(binary_path) > 0
    except Exception as exc:
        logger.debug("SUMO binary check exception: %s", exc)
        sumo_available = False

    mongo_available = db_manager.is_available
    overall_status = "ok" if (sumo_available and mongo_available) else ("degraded" if sumo_available else "error")

    return {
        "status": overall_status,
        "service": "smart-traffic-digital-twin",
        "version": settings.VERSION,
        "sumo_available": sumo_available,
        "mongodb_available": mongo_available,
    }

