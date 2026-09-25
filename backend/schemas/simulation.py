"""Pydantic schemas for simulation endpoints and controller metadata."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ControllerInfo(BaseModel):
    """Metadata describing an available traffic signal controller."""
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(..., description="Unique controller identifier ('fixed', 'adaptive', 'dqn')")
    name: str = Field(..., description="Human-readable controller display name")
    type: str = Field(..., description="Controller type category ('baseline', 'adaptive', 'reinforcement_learning')")
    available: bool = Field(default=True, description="Whether controller and any required models are ready for execution")
    model_path: Optional[str] = Field(default=None, description="Relative model checkpoint path if applicable")



class SimulationStartRequest(BaseModel):
    """Request payload to initiate a new traffic simulation session."""
    controller: Literal["fixed", "adaptive", "dqn"] = Field(
        default="fixed",
        description="Traffic signal controller to evaluate: 'fixed', 'adaptive', or 'dqn'",
    )
    steps: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Total simulation duration in seconds (1 to 3600)",
    )
    seed: int = Field(
        default=42,
        description="Random seed for deterministic vehicle route generation and arrivals",
    )
    gui: bool = Field(
        default=False,
        description="Whether to launch with graphical SUMO-GUI window (headless otherwise)",
    )


class SimulationStartResponse(BaseModel):
    """Response returned upon successful simulation launch."""
    status: str = Field(default="started", description="Operation status ('started')")
    simulation_id: str = Field(..., description="Unique UUID for the initiated simulation session")
    controller: str = Field(..., description="Selected traffic controller")
    steps: int = Field(..., description="Requested total simulation steps")
    seed: int = Field(..., description="Configured simulation seed")


class SimulationStopResponse(BaseModel):
    """Response returned when stopping an active simulation session."""
    status: str = Field(..., description="Operation status ('stopped' or 'idle')")
    simulation_id: Optional[str] = Field(default=None, description="Simulation ID that was terminated")


class SimulationStatusResponse(BaseModel):
    """Current runtime status of the simulation runner engine."""
    running: bool = Field(..., description="Whether a simulation is actively executing")
    status: Literal["idle", "starting", "running", "stopping", "completed", "stopped", "error"] = Field(
        ...,
        description="Detailed lifecycle state",
    )
    simulation_id: Optional[str] = Field(default=None, description="Active or last simulation ID")
    controller: Optional[str] = Field(default=None, description="Active controller identifier")
    seed: Optional[int] = Field(default=None, description="Simulation seed")
    current_step: Optional[int] = Field(default=None, description="Current elapsed simulation step")
    total_steps: Optional[int] = Field(default=None, description="Target total simulation steps")
    simulation_time: Optional[float] = Field(default=None, description="Current simulation time in seconds")
    error: Optional[str] = Field(default=None, description="Error message if status is 'error'")


class SimulationResultResponse(BaseModel):
    """Aggregated performance metrics from the most recent completed simulation run."""
    simulation_id: str = Field(..., description="Unique simulation identifier")
    controller: str = Field(..., description="Controller evaluated")
    seed: int = Field(..., description="Simulation random seed")
    steps: int = Field(..., description="Total completed simulation steps")
    status: str = Field(default="completed", description="Final run status")
    metrics: Dict[str, Any] = Field(..., description="Comprehensive aggregate performance metrics dictionary")


class SimulationRunDetail(BaseModel):
    """Detailed persistent record of an experiment run."""
    simulation_id: str = Field(..., description="Unique UUID for simulation session")
    intersection_id: str = Field(default="INT-001", description="Associated intersection ID")
    controller: str = Field(..., description="Traffic signal controller ID")
    seed: int = Field(..., description="Random seed")
    steps: int = Field(..., description="Simulation duration in seconds")
    gui: bool = Field(default=False, description="Whether GUI was enabled")
    status: str = Field(..., description="Run status ('running', 'completed', 'stopped', 'error')")
    started_at: Optional[str] = Field(default=None, description="Start timestamp ISO 8601")
    completed_at: Optional[str] = Field(default=None, description="Completion timestamp ISO 8601")
    duration_seconds: Optional[float] = Field(default=None, description="Elapsed execution seconds")
    metrics: Optional[Dict[str, Any]] = Field(default=None, description="Final aggregate performance metrics")


class SignalDecisionResponse(BaseModel):
    """Logged signal controller phase actuation decision."""
    simulation_id: str = Field(..., description="Simulation identifier")
    intersection_id: str = Field(default="INT-001", description="Intersection identifier")
    timestamp: str = Field(..., description="Decision timestamp")
    simulation_time: float = Field(..., description="Simulation elapsed time in seconds")
    controller: str = Field(..., description="Controller identifier")
    action_id: int = Field(..., description="Selected discrete action index")
    action: str = Field(..., description="Action name ('KEEP', 'SWITCH_NS', 'SWITCH_EW')")
    requested_phase: int = Field(..., description="Target phase index requested")
    approved: bool = Field(..., description="Whether approved by SignalSafetyManager")
    reason: Optional[str] = Field(default=None, description="Decision rationale")
    current_phase: int = Field(..., description="Signal phase active at decision time")
    elapsed_green: float = Field(..., description="Elapsed duration in active green")

