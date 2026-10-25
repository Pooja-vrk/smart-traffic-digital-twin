"""FastAPI application entry point for Smart Traffic Digital Twin."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api import api_router
from backend.config.settings import settings
from backend.database.connection import db_manager
from backend.database.repositories.intersection_repository import IntersectionRepository
from backend.services.scenario_manager import scenario_manager
from backend.services.simulation_manager import sim_manager
from backend.websocket.manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smart_traffic_backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup, database connection, and graceful shutdown lifecycles."""
    logger.info("Starting Smart Traffic Digital Twin Backend v%s...", settings.VERSION)
    loop = asyncio.get_running_loop()
    sim_manager.set_event_loop(loop)
    scenario_manager.set_event_loop(loop)
    logger.info("SimulationManager and ScenarioManager registered with event loop.")

    # Initialize MongoDB persistence
    mongo_connected = db_manager.connect()
    if mongo_connected:
        db_manager.create_indexes()
        IntersectionRepository.upsert_default_intersection()
        logger.info("MongoDB initialized with collections, indexes, and default intersection INT-001.")
    else:
        logger.warning("MongoDB unavailable. Digital Twin running with in-memory telemetry only.")

    # Eagerly load congestion prediction model
    try:
        from prediction.predictor import predictor
        loaded = predictor.load_model()
        if loaded:
            logger.info("Congestion prediction model loaded successfully at startup.")
        else:
            logger.warning("Congestion prediction model not available. Predictive intelligence will run in fallback mode.")
    except Exception as exc:
        logger.warning("Could not initialize prediction model at startup: %s", exc)

    yield

    logger.info("Shutting down Smart Traffic Digital Twin Backend...")
    sim_manager.shutdown()
    scenario_manager.stop_scenario()
    db_manager.disconnect()
    logger.info("Shutdown complete. All simulation, background, and database connections cleaned up.")



app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS for frontend access
origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
# Remove duplicates while preserving order
unique_origins = list(dict.fromkeys(origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=unique_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API endpoints
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """Root welcome endpoint providing service metadata and discovery links."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "description": settings.DESCRIPTION,
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
    }


@app.websocket("/ws/traffic")
async def websocket_traffic_endpoint(websocket: WebSocket) -> None:
    """WebSocket streaming channel for real-time traffic digital twin telemetry."""
    await ws_manager.connect(websocket)

    # Send immediate initial state
    try:
        status_info = sim_manager.get_status().model_dump()
        await websocket.send_json({
            "type": "status_update",
            "data": status_info,
        })

        latest_snap = sim_manager.get_current_traffic()
        if latest_snap:
            await websocket.send_json({
                "type": "traffic_update",
                "data": latest_snap.model_dump(),
            })

        while True:
            # Keep connection alive and process incoming client pings
            text = await websocket.receive_text()
            try:
                payload = json.loads(text)
                if isinstance(payload, dict) and payload.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.debug("WebSocket client loop terminated: %s", exc)
        await ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )

