"""Live traffic telemetry and intersection snapshot endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.schemas.traffic import TrafficSnapshotResponse
from backend.services.simulation_manager import sim_manager

router = APIRouter(prefix="/traffic", tags=["Traffic Telemetry"])


@router.get(
    "/current",
    response_model=TrafficSnapshotResponse,
    summary="Get Current Traffic Snapshot",
)
async def get_current_traffic() -> TrafficSnapshotResponse:
    """Retrieve the latest real-time digital twin state (queues, speeds, delays, signal phases, AI actions)."""
    snapshot = sim_manager.get_current_traffic()
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active or recent traffic telemetry snapshot available. Start a simulation first.",
        )
    return snapshot
