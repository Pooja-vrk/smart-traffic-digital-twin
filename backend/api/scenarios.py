"""Scenario / What-If Lab API router endpoints."""

from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.schemas.scenario import (
    ScenarioHistoryItem,
    ScenarioPresetInfo,
    ScenarioResultResponse,
    ScenarioRunRequest,
    ScenarioStatusResponse,
)
from backend.services.scenario_manager import scenario_manager
from backend.services.simulation_manager import (
    ControllerNotFoundError,
    ModelNotFoundError,
    SimulationAlreadyRunningError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenarios", tags=["Scenario Lab"])


@router.get(
    "/presets",
    response_model=List[ScenarioPresetInfo],
    summary="List Scenario Presets",
)
async def get_scenario_presets() -> List[ScenarioPresetInfo]:
    """Retrieve pre-configured traffic demand scenario presets."""
    return scenario_manager.get_presets()


@router.post(
    "/run",
    response_model=ScenarioStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Traffic Scenario",
)
async def run_scenario(request: ScenarioRunRequest) -> ScenarioStatusResponse:
    """Launch a parametric traffic demand scenario through the real SUMO digital twin."""
    try:
        return scenario_manager.run_scenario(request)
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
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        )
    except Exception as err:
        logger.error("Failed to run scenario: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error executing scenario: {err}",
        )


@router.post(
    "/stop",
    response_model=ScenarioStatusResponse,
    summary="Stop Running Scenario",
)
async def stop_scenario() -> ScenarioStatusResponse:
    """Gracefully stop the actively running traffic scenario experiment."""
    return scenario_manager.stop_scenario()


@router.get(
    "/status",
    response_model=ScenarioStatusResponse,
    summary="Get Active Scenario Status",
)
async def get_active_scenario_status() -> ScenarioStatusResponse:
    """Query current execution state and progress of the scenario runner."""
    return scenario_manager.get_status()


@router.get(
    "/status/{scenario_id}",
    response_model=ScenarioStatusResponse,
    summary="Get Specific Scenario Status",
)
async def get_scenario_status(scenario_id: str) -> ScenarioStatusResponse:
    """Query execution status for a specific scenario session ID."""
    current_status = scenario_manager.get_status()
    if current_status.scenario_id == scenario_id:
        return current_status

    # Check persistent result
    result = scenario_manager.get_scenario_result(scenario_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario session '{scenario_id}' not found.",
        )

    return ScenarioStatusResponse(
        running=False,
        status=result.status if result.status in [
            "idle", "configuring", "queued", "starting", "running", "completed", "stopping", "stopped", "failed"
        ] else "completed",
        scenario_id=result.scenario_id,
        scenario_name=result.scenario_name,
        controller=result.controller,
        seed=result.seed,
        current_step=result.duration,
        total_steps=result.duration,
        simulation_time=float(result.duration),
        progress_pct=100.0,
    )


@router.get(
    "/result/latest",
    response_model=ScenarioResultResponse,
    summary="Get Latest Completed Scenario Result",
)
async def get_latest_scenario_result() -> ScenarioResultResponse:
    """Retrieve the aggregate metrics and benchmark report of the latest completed scenario."""
    res = scenario_manager.get_latest_result()
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed scenario results available in current session. Run a scenario first.",
        )
    return res


@router.get(
    "/history",
    response_model=List[ScenarioHistoryItem],
    summary="List Scenario History",
)
async def get_scenario_history(
    limit: int = Query(default=50, ge=1, le=100, description="Max history items to retrieve"),
) -> List[ScenarioHistoryItem]:
    """Retrieve historical scenario experiment summaries and benchmark results."""
    return scenario_manager.get_scenario_history(limit=limit)


@router.get(
    "/{scenario_id}/result",
    response_model=ScenarioResultResponse,
    summary="Get Scenario Result by ID",
)
async def get_scenario_result_by_id(scenario_id: str) -> ScenarioResultResponse:
    """Retrieve detailed metrics and comparison data for a specific completed scenario run."""
    res = scenario_manager.get_scenario_result(scenario_id)
    if res is None:
        # Also check in-memory latest
        latest = scenario_manager.get_latest_result()
        if latest and latest.scenario_id == scenario_id:
            return latest
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario result with ID '{scenario_id}' not found.",
        )
    return res


@router.get(
    "/{scenario_id}",
    response_model=ScenarioResultResponse,
    summary="Get Scenario Details",
)
async def get_scenario_details(scenario_id: str) -> ScenarioResultResponse:
    """Retrieve complete metadata, parameters, and results for a specific scenario experiment."""
    return await get_scenario_result_by_id(scenario_id)
