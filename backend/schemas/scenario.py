"""Pydantic schemas for Scenario / What-If Lab endpoints and configurations."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DirectionBiasSchema(BaseModel):
    """Directional traffic demand distribution percentages."""
    north: float = Field(default=25.0, ge=0.0, le=100.0, description="North inflow percentage (0-100)")
    south: float = Field(default=25.0, ge=0.0, le=100.0, description="South inflow percentage (0-100)")
    east: float = Field(default=25.0, ge=0.0, le=100.0, description="East inflow percentage (0-100)")
    west: float = Field(default=25.0, ge=0.0, le=100.0, description="West inflow percentage (0-100)")

    @field_validator("west")
    @classmethod
    def validate_sum(cls, v: float, info) -> float:
        values = info.data
        n = values.get("north", 0.0)
        s = values.get("south", 0.0)
        e = values.get("east", 0.0)
        total = round(n + s + e + v, 1)
        if not (99.0 <= total <= 101.0):
            raise ValueError(f"Direction percentages must sum to 100% (got {total:.1f}%)")
        return v

    def to_dict(self) -> Dict[str, float]:
        return {
            "north": round(self.north, 1),
            "south": round(self.south, 1),
            "east": round(self.east, 1),
            "west": round(self.west, 1),
        }


class ScenarioPresetInfo(BaseModel):
    """Preset scenario specification template."""
    id: str
    name: str
    description: str
    density: str
    multiplier: float
    direction_bias: DirectionBiasSchema
    recommended_duration: int = 300
    emergency_vehicle: bool = False
    emergency_approach: str = "east"
    emergency_step: int = 15
    emergency_vehicle_type: str = "ambulance"


class ScenarioRunRequest(BaseModel):
    """Request payload to initiate a Scenario Lab experiment run."""
    name: str = Field(default="Custom Scenario", description="Human-readable scenario label")
    density: Literal["low", "medium", "high", "very_high", "custom"] = Field(
        default="medium",
        description="Traffic density level ('low', 'medium', 'high', 'very_high', 'custom')",
    )
    multiplier: Optional[float] = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        description="Custom demand multiplier if density is 'custom' or fine-tuned",
    )
    direction_bias: DirectionBiasSchema = Field(
        default_factory=DirectionBiasSchema,
        description="Directional traffic distribution summing to 100%",
    )
    controller: Literal["fixed", "adaptive", "dqn"] = Field(
        default="dqn",
        description="Traffic controller to evaluate ('fixed', 'adaptive', 'dqn')",
    )
    duration: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Scenario simulation duration in seconds (30 to 3600)",
    )
    seed: int = Field(
        default=42,
        ge=0,
        le=999999,
        description="Random seed for deterministic vehicle routing",
    )
    gui: bool = Field(
        default=False,
        description="Whether to launch SUMO-GUI window",
    )
    compare_all_controllers: bool = Field(
        default=False,
        description="If True, executes sequential benchmark runs across Fixed-Time, Adaptive, and DQN",
    )
    emergency_vehicle: bool = Field(
        default=False,
        description="Whether to inject a high-priority emergency vehicle into the scenario",
    )
    emergency_approach: Literal["north", "south", "east", "west"] = Field(
        default="east",
        description="Approach corridor from which the emergency vehicle enters ('north', 'south', 'east', 'west')",
    )
    emergency_step: int = Field(
        default=15,
        ge=1,
        le=3600,
        description="Simulation time step (second) at which the emergency vehicle is inserted",
    )
    emergency_vehicle_type: Literal["ambulance", "fire_engine", "emergency_vehicle"] = Field(
        default="ambulance",
        description="Type of emergency vehicle to deploy ('ambulance', 'fire_engine', 'emergency_vehicle')",
    )


class ScenarioStatusResponse(BaseModel):
    """Runtime status of the Scenario Lab runner."""
    running: bool = Field(..., description="Whether a scenario is actively executing")
    status: Literal[
        "idle", "configuring", "queued", "starting", "running", "completed", "stopping", "stopped", "failed"
    ] = Field(..., description="Detailed lifecycle status")
    scenario_id: Optional[str] = Field(default=None, description="Active scenario UUID")
    scenario_name: Optional[str] = Field(default=None, description="Active scenario label")
    controller: Optional[str] = Field(default=None, description="Current controller being evaluated")
    seed: Optional[int] = Field(default=None, description="Configured seed")
    current_step: Optional[int] = Field(default=None, description="Current step in active run")
    total_steps: Optional[int] = Field(default=None, description="Target duration steps")
    simulation_time: Optional[float] = Field(default=None, description="Current simulation time")
    is_comparison: bool = Field(default=False, description="Whether running multi-controller comparison")
    current_stage: Optional[str] = Field(default=None, description="Current comparison stage name")
    stage_index: Optional[int] = Field(default=None, description="Comparison stage index (1-based)")
    total_stages: Optional[int] = Field(default=None, description="Total comparison stages (e.g. 3)")
    progress_pct: Optional[float] = Field(default=None, description="Overall progress percentage")
    error: Optional[str] = Field(default=None, description="Error details if status is 'failed'")


class ScenarioResultResponse(BaseModel):
    """Result metrics and performance summary of a completed scenario experiment."""
    scenario_id: str = Field(..., description="Unique scenario experiment identifier")
    scenario_name: str = Field(..., description="Human-readable scenario name")
    configuration: Dict[str, Any] = Field(..., description="Complete scenario configuration parameters")
    controller: str = Field(..., description="Controller evaluated")
    seed: int = Field(..., description="Simulation random seed")
    duration: int = Field(..., description="Duration in seconds")
    status: str = Field(default="completed", description="Execution status")
    metrics: Dict[str, Any] = Field(..., description="Primary aggregate performance metrics")
    comparison: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Multi-controller benchmark comparison results if executed",
    )
    ai_stats: Optional[Dict[str, Any]] = Field(
        default=None,
        description="DQN agent action, Q-value, and decision stats",
    )
    prediction_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Time-aligned live congestion forecast evaluation metrics (MAE, RMSE, baseline comparison)",
    )
    emergency_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Empirical emergency green corridor performance metrics (travel time, delay, time to priority, baseline comparison)",
    )
    created_at: Optional[str] = Field(default=None, description="Timestamp ISO 8601")


class ScenarioHistoryItem(BaseModel):
    """Historical scenario summary record."""
    scenario_id: str
    scenario_name: str
    controller: str
    density: str
    multiplier: float
    seed: int
    duration: int
    status: str
    metrics: Optional[Dict[str, Any]] = None
    is_comparison: bool = False
    comparison: Optional[Dict[str, Any]] = None
    emergency_metrics: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
