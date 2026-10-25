"""API routers package."""

from fastapi import APIRouter

from backend.api.analytics import router as analytics_router
from backend.api.controllers import router as controllers_router
from backend.api.health import router as health_router
from backend.api.prediction import router as prediction_router
from backend.api.scenarios import router as scenarios_router
from backend.api.simulation import router as simulation_router
from backend.api.traffic import router as traffic_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(controllers_router)
api_router.include_router(simulation_router)
api_router.include_router(scenarios_router)
api_router.include_router(traffic_router)
api_router.include_router(analytics_router)
api_router.include_router(prediction_router)

__all__ = ["api_router"]

