"""Pydantic schemas for simulation endpoints and controller metadata."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
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
    emergency_vehicle: bool = Field(
        default=False,
        description="Whether to schedule an emergency vehicle during this simulation run",
    )
    emergency_vehicle_type: Optional[Literal["ambulance", "fire_engine", "police", "emergency_vehicle"]] = Field(
        default="ambulance",
        description="Type of emergency vehicle ('ambulance', 'fire_engine', 'police', 'emergency_vehicle')",
    )
    emergency_approach: Optional[Literal["north", "south", "east", "west"]] = Field(
        default="east",
        description="Approach corridor for emergency vehicle ('north', 'south', 'east', 'west')",
    )
    emergency_step: Optional[int] = Field(
        default=None,
        ge=0,
        description="Simulation step at which to inject the emergency vehicle",
    )


class EmergencyVehicleRequest(BaseModel):
    """Request payload to trigger/schedule an emergency vehicle in the running simulation."""
    vehicle_type: Literal["ambulance", "fire_engine", "police", "emergency_vehicle"] = Field(
        default="ambulance",
        description="Emergency vehicle type: 'ambulance', 'fire_engine', 'police', or 'emergency_vehicle'",
    )
    approach: Literal["north", "south", "east", "west"] = Field(
        default="east",
        description="Inflow approach corridor: 'north', 'south', 'east', or 'west'",
    )
    spawn_step: Optional[int] = Field(
        default=None,
        ge=0,
        description="Simulation step to spawn vehicle. If None or <= current step, activates on next step.",
    )


class EmergencyVehicleResponse(BaseModel):
    """Response returned upon successful emergency vehicle activation/scheduling."""
    status: str = Field(default="activated", description="Status of the emergency dispatch ('activated' or 'scheduled')")
    simulation_id: str = Field(..., description="Target active simulation session identifier")
    vehicle_id: str = Field(default="EV_01", description="Assigned TraCI vehicle ID")
    vehicle_type: str = Field(..., description="Emergency vehicle type")
    approach: str = Field(..., description="Corridor approach direction")
    spawn_step: int = Field(..., description="Simulation step at which vehicle is scheduled to enter")
    message: str = Field(..., description="Human-readable confirmation message")


class CoordinationModeRequest(BaseModel):
    """Request payload to change multi-intersection coordination mode."""
    mode: Literal["ARTERY_EW", "ARTERY_NS", "BALANCED_ADAPTIVE", "ISOLATED"] = Field(
        default="ARTERY_EW",
        description="Coordination mode: 'ARTERY_EW', 'ARTERY_NS', 'BALANCED_ADAPTIVE', or 'ISOLATED'",
    )


class CoordinationModeResponse(BaseModel):
    """Response returned upon changing multi-intersection coordination mode."""
    status: str = Field(default="success")
    simulation_id: str = Field(default="")
    mode: str = Field(...)
    message: str = Field(...)
    coordination: Dict[str, Any] = Field(default_factory=dict)


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
    prediction_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Time-aligned live congestion forecast evaluation metrics (MAE, RMSE, baseline comparison)",
    )


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


class AgenticDecisionResponse(BaseModel):
    """Complete explainable Agentic AI decision record representing the full 7-stage loop."""
    model_config = ConfigDict(protected_namespaces=())

    decision_id: str = Field(default="", description="Unique UUID for decision instance")
    simulation_id: Optional[str] = Field(default=None, description="Simulation identifier")
    simulation_time: float = Field(default=0.0, description="Simulation elapsed time in seconds")
    step: int = Field(default=0, description="Simulation step integer")
    controller: str = Field(default="Unknown", description="Active controller identifier")
    observation: Dict[str, Any] = Field(default_factory=dict, description="Stage 1: Verified snapshot observations")
    detected_conditions: Dict[str, Any] = Field(default_factory=dict, description="Stage 2: Analyzed directional pressures and congestion")
    requested_action: str = Field(default="KEEP", description="Stage 3: Proposed action name")
    requested_phase: int = Field(default=0, description="Stage 3: Proposed green phase index (0 or 2)")
    validated_action: str = Field(default="APPROVED", description="Stage 4: Legally safe action approved or overridden")
    validated_phase: int = Field(default=0, description="Stage 4: Validated phase index enforced by safety manager")
    is_safety_override: bool = Field(default=False, description="Whether safety manager overrode or restricted the proposed action")
    safety_status: str = Field(default="SAFE", description="Safety manager state classification")
    safety_reason: str = Field(default="", description="Safety manager verification rationale")
    decision_reason: str = Field(default="", description="Controller policy rationale and supporting state")
    execution_status: str = Field(default="EXECUTED", description="Stage 5: TraCI actuation status")
    q_values: Optional[List[float]] = Field(default=None, description="Raw policy network expected cumulative returns (never labeled as probabilities)")
    reward: Optional[float] = Field(default=None, description="Step reinforcement learning reward")
    prediction: Optional[Dict[str, Any]] = Field(default=None, description="Time-aligned live congestion forecast when available")
    emergency: Optional[Dict[str, Any]] = Field(default=None, description="Emergency green corridor tracking when active")
    post_action_metrics: Optional[Dict[str, Any]] = Field(default=None, description="Stage 6: Outcome deltas measured from prior step")

    # Backward compatibility fields
    action_id: Optional[int] = Field(default=None)
    action: Optional[str] = Field(default=None)
    approved: Optional[bool] = Field(default=None)
    current_phase: Optional[int] = Field(default=None)
    elapsed_green: Optional[float] = Field(default=None)
    reason: Optional[str] = Field(default=None)


class ReplayFrameResponse(BaseModel):
    """Synchronized offline telemetry and decision frame."""
    step: int = Field(..., description="Simulation step index")
    simulation_time: float = Field(..., description="Simulation timestamp in seconds")
    snapshot: Dict[str, Any] = Field(..., description="Instantaneous digital twin traffic snapshot")
    decision: Optional[Dict[str, Any]] = Field(default=None, description="Agentic decision made at this step")


class ReplayBundleResponse(BaseModel):
    """Complete recorded experiment telemetry bundle for offline playback without SUMO."""
    simulation_id: str = Field(..., description="Simulation identifier")
    controller: str = Field(..., description="Active controller identifier")
    total_frames: int = Field(..., description="Total count of chronological frames")
    duration_seconds: float = Field(..., description="Total duration of recorded experiment in seconds")
    frames: List[ReplayFrameResponse] = Field(default_factory=list, description="Chronological playback frames")


AgenticDecisionResponse.model_rebuild()
ReplayBundleResponse.model_rebuild()
