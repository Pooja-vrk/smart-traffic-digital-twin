"""Pydantic schemas for WebSocket telemetry message packets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    """Standardized WebSocket packet contract for digital twin streaming."""
    type: Literal[
        "simulation_started",
        "traffic_update",
        "ai_decision",
        "simulation_completed",
        "simulation_stopped",
        "simulation_error",
        "status_update",
        "emergency_scheduled",
        "emergency_update",
        "scenario_stage_update",
        "scenario_status_update",
        "scenario_completed",
        "scenario_stopped",
        "pong",
    ] = Field(..., description="Message event type classification")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of packet creation",
    )
    simulation_id: Optional[str] = Field(default=None, description="Active simulation identifier")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload dictionary")
