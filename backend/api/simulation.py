"""Simulation lifecycle control and execution endpoints."""

from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.schemas.simulation import (
    AgenticDecisionResponse,
    ReplayBundleResponse,
    SignalDecisionResponse,
    SimulationResultResponse,
    SimulationRunDetail,
    SimulationStartRequest,
    SimulationStartResponse,
    SimulationStatusResponse,
    SimulationStopResponse,
)
from backend.services.persistence_service import PersistenceService
from backend.services.simulation_manager import (
    ControllerNotFoundError,
    ModelNotFoundError,
    SimulationAlreadyRunningError,
    sim_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.post(
    "/start",
    response_model=SimulationStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start Simulation",
)
async def start_simulation(request: SimulationStartRequest) -> SimulationStartResponse:
    """Launch a new microscopic SUMO simulation session with the selected controller.

    Returns immediately while simulation advances asynchronously in the background.
    """
    try:
        response = sim_manager.start_simulation(request)
        return response
    except SimulationAlreadyRunningError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )
    except ModelNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        )
    except ControllerNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )
    except Exception as err:
        logger.error("Failed to start simulation: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error starting simulation: {err}",
        )


@router.post(
    "/stop",
    response_model=SimulationStopResponse,
    summary="Stop Simulation",
)
async def stop_simulation() -> SimulationStopResponse:
    """Request safe interruption and shutdown of the active simulation session."""
    return sim_manager.stop_simulation()


@router.get(
    "/status",
    response_model=SimulationStatusResponse,
    summary="Simulation Status",
)
async def get_simulation_status() -> SimulationStatusResponse:
    """Retrieve the current lifecycle state, active step, and progress of the simulation runner."""
    return sim_manager.get_status()


@router.get(
    "/result",
    response_model=SimulationResultResponse,
    summary="Latest Simulation Result",
)
async def get_simulation_result() -> SimulationResultResponse:
    """Retrieve the aggregate metrics and performance summary of the most recently completed run."""
    result = sim_manager.get_latest_result()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed simulation results available. Run a simulation to completion first.",
        )
    return result


@router.get(
    "/history",
    response_model=List[SimulationRunDetail],
    summary="List Simulation History",
)
async def list_simulation_history(
    controller: Optional[str] = Query(default=None, description="Filter by controller ID"),
    seed: Optional[int] = Query(default=None, description="Filter by random seed"),
    status: Optional[str] = Query(default=None, description="Filter by run status"),
    limit: int = Query(default=50, ge=1, le=500, description="Max records to return"),
) -> List[SimulationRunDetail]:
    """Retrieve historical simulation runs with optional filtering from persistent MongoDB storage."""
    runs = PersistenceService.get_simulation_history(
        controller=controller,
        seed=seed,
        status=status,
        limit=limit,
    )
    return [SimulationRunDetail(**r) for r in runs]


@router.get(
    "/{simulation_id}",
    response_model=SimulationRunDetail,
    summary="Get Simulation Detail",
)
async def get_simulation_detail(simulation_id: str) -> SimulationRunDetail:
    """Retrieve detailed metadata and final metrics for a specific simulation session."""
    doc = PersistenceService.get_simulation_detail(simulation_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation run with ID '{simulation_id}' not found in database.",
        )
    return SimulationRunDetail(**doc)


@router.get(
    "/{simulation_id}/snapshots",
    summary="Get Simulation Traffic Snapshots",
)
async def get_simulation_snapshots(
    simulation_id: str,
    limit: int = Query(default=300, ge=1, le=1000, description="Max snapshots to retrieve"),
) -> List[dict]:
    """Retrieve chronological digital twin traffic telemetry snapshots recorded during a run."""
    return PersistenceService.get_simulation_snapshots(simulation_id, limit=limit)


@router.get(
    "/{simulation_id}/decisions",
    summary="Get Simulation Decisions",
)
async def get_simulation_decisions(
    simulation_id: str,
    controller: Optional[str] = Query(default=None, description="Filter by controller"),
    safety_override_only: bool = Query(default=False, description="Filter to safety overrides only"),
    emergency_only: bool = Query(default=False, description="Filter to emergency priority events only"),
    skip: int = Query(default=0, ge=0, description="Offset for pagination"),
    limit: int = Query(default=300, ge=1, le=1000, description="Max decision logs to retrieve"),
) -> List[dict]:
    """Retrieve chronological controller signal switching and explainable AI decisions."""
    decisions = PersistenceService.get_simulation_decisions(
        simulation_id=simulation_id,
        controller=controller,
        safety_override_only=safety_override_only,
        emergency_only=emergency_only,
        skip=skip,
        limit=limit,
    )
    return decisions


@router.get(
    "/{simulation_id}/decisions/{decision_id}",
    summary="Get Single Decision Inspection",
)
async def get_single_decision_detail(
    simulation_id: str,
    decision_id: str,
) -> dict:
    """Retrieve full 7-stage explainability details for a single decision record."""
    decision = PersistenceService.get_single_decision(simulation_id, decision_id)
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision '{decision_id}' for simulation '{simulation_id}' not found.",
        )
    return decision


@router.get(
    "/{simulation_id}/replay",
    response_model=ReplayBundleResponse,
    summary="Get Simulation Offline Replay Telemetry Frames",
)
async def get_simulation_replay(
    simulation_id: str,
    limit: int = Query(default=1000, ge=1, le=5000, description="Max replay frames to return"),
) -> ReplayBundleResponse:
    """Retrieve time-synchronized offline telemetry frames and decision records without running SUMO."""
    bundle = PersistenceService.get_replay_frames(simulation_id, limit=limit)
    if not bundle or not bundle.get("frames"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No telemetry replay frames recorded for simulation '{simulation_id}'.",
        )
    return ReplayBundleResponse(**bundle)
