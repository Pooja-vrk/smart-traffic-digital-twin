"""Traffic signal controllers listing and model availability endpoint."""

from __future__ import annotations

from typing import List
from fastapi import APIRouter

from backend.schemas.simulation import ControllerInfo
from backend.services.simulation_manager import sim_manager

router = APIRouter(prefix="", tags=["Controllers"])


@router.get("/controllers", response_model=List[ControllerInfo], summary="List Available Controllers")
async def list_controllers() -> List[ControllerInfo]:
    """Retrieve all supported traffic signal controllers (Fixed-Time, Adaptive, DQN) and their readiness."""
    return sim_manager.get_available_controllers()
