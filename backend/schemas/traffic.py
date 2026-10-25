"""Pydantic schemas for instantaneous traffic state and telemetry snapshots."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class VehicleLiveState(BaseModel):
    """Instantaneous live spatial and kinematic telemetry of a simulated vehicle."""
    id: str = Field(..., description="Unique SUMO vehicle identifier")
    x: float = Field(..., description="X coordinate in SUMO cartesian space (0 to 600m)")
    y: float = Field(..., description="Y coordinate in SUMO cartesian space (0 to 600m)")
    angle: float = Field(..., description="Vehicle heading angle in degrees (0=N, 90=E, 180=S, 270=W)")
    speed: float = Field(..., description="Current speed in meters per second")
    lane_id: str = Field(default="", description="Identifier of lane currently occupied")
    edge_id: str = Field(default="", description="Identifier of edge/road currently occupied")
    waiting_time: float = Field(default=0.0, description="Accumulated waiting time in seconds")
    vehicle_type: str = Field(default="standard_car", description="Vehicle type classification")
    length: float = Field(default=5.0, description="Vehicle physical length in meters")
    width: float = Field(default=2.0, description="Vehicle physical width in meters")


class VehiclesInfo(BaseModel):
    """Vehicle count statistics across the intersection."""
    total: int = Field(default=0, description="Active vehicles currently within the intersection network")
    entered: int = Field(default=0, description="Cumulative vehicles that have entered the network")
    completed: int = Field(default=0, description="Cumulative vehicles that have completed their trip (throughput)")


class QueuesInfo(BaseModel):
    """Instantaneous halted queue counts per approach corridor."""
    north: int = Field(default=0, description="Halted vehicles on North approach")
    south: int = Field(default=0, description="Halted vehicles on South approach")
    east: int = Field(default=0, description="Halted vehicles on East approach")
    west: int = Field(default=0, description="Halted vehicles on West approach")
    total: int = Field(default=0, description="Sum of halted vehicles across all approaches")
    peak: int = Field(default=0, description="Peak instantaneous total queue recorded during run")


class SpeedInfo(BaseModel):
    """Instantaneous vehicle velocity statistics."""
    average_mps: float = Field(default=0.0, description="Mean speed of active vehicles in meters per second")


class WaitingInfo(BaseModel):
    """Accumulated delay and waiting statistics."""
    average_seconds: float = Field(default=0.0, description="Mean waiting time per vehicle in seconds")
    total_seconds: float = Field(default=0.0, description="Total cumulative waiting time across all vehicles")


class SignalInfo(BaseModel):
    """Instantaneous state of the intersection traffic light system."""
    phase_index: int = Field(default=0, description="Current active phase index (0: NS_G, 1: NS_Y, 2: EW_G, 3: EW_Y)")
    phase_name: str = Field(default="NS_GREEN", description="Descriptive name of active phase")
    state: str = Field(default="green", description="Signal state category ('green', 'yellow', 'red')")
    raw_state: str = Field(default="", description="TraCI raw traffic light state string (e.g. GGGggrrrrr...)")
    elapsed_seconds: float = Field(default=0.0, description="Time spent in the currently active phase")


class AIDecisionInfo(BaseModel):
    """Reinforcement learning decision telemetry when DQN controller is active."""
    action: str = Field(default="KEEP", description="Action name chosen by policy ('KEEP', 'SWITCH_NS', 'SWITCH_EW')")
    action_id: int = Field(default=0, description="Discrete action index (0, 1, 2)")
    requested_phase: int = Field(default=0, description="Target phase requested by DQN")
    approved: bool = Field(default=True, description="Whether SignalSafetyManager approved the requested phase")
    reason: Optional[str] = Field(default=None, description="Explanation or state details from AI controller")
    q_values: List[float] = Field(default_factory=list, description="Computed Q-values for action space [KEEP, REQ_NS, REQ_EW]")
    normalized_state: List[float] = Field(default_factory=list, description="Normalized feature vector fed to DQN")
    reward: Optional[float] = Field(default=None, description="Instantaneous step reward estimate")
    decision_time: Optional[float] = Field(default=None, description="Simulation timestamp when decision was made")


class EmergencyLiveInfo(BaseModel):
    """Real-time telemetry and priority status for active emergency vehicle."""
    active: bool = Field(default=False, description="Whether an emergency vehicle is active in the network")
    vehicle_id: Optional[str] = Field(default=None, description="SUMO vehicle identifier")
    vehicle_type: Optional[str] = Field(default=None, description="SUMO vehicle type")
    approach: Optional[str] = Field(default=None, description="Approaching intersection corridor ('north', 'south', 'east', 'west')")
    state: str = Field(default="IDLE", description="Tracking lifecycle ('IDLE', 'DETECTED', 'APPROACHING', 'PRIORITY_REQUESTED', 'PRIORITY_ACTIVE', 'INSIDE_JUNCTION', 'VEHICLE_PASSED', 'RESTORING_NORMAL')")
    distance: Optional[float] = Field(default=None, description="Distance in meters to intersection center")
    distance_to_stopline: Optional[float] = Field(default=None, description="Distance in meters to intersection stopline")
    lane_id: Optional[str] = Field(default=None, description="Active lane occupied by emergency vehicle")
    edge_id: Optional[str] = Field(default=None, description="Active network edge occupied by emergency vehicle")
    speed: Optional[float] = Field(default=None, description="Current speed in m/s")
    eta_seconds: Optional[float] = Field(default=None, description="Estimated time of arrival to stopline in seconds")
    priority_requested: bool = Field(default=False, description="Whether priority green has been requested")
    priority_approved: bool = Field(default=False, description="Whether priority has been approved by Safety Manager")
    priority_active: bool = Field(default=False, description="Whether priority green corridor is currently active")
    priority_duration: float = Field(default=0.0, description="Duration in seconds priority green corridor has been held")
    lifecycle_state: str = Field(default="IDLE", description="Explicit 7-stage lifecycle state")
    safety_status: str = Field(default="NORMAL", description="Safety status ('NORMAL', 'TRANSITIONING', 'MIN_GREEN_HOLD', 'PRIORITY_GRANTED')")
    current_action: str = "NORMAL_CONTROL"
    reason: Optional[str] = Field(default=None, description="Grounded explanation of the emergency priority decision")
    entry_time: Optional[float] = Field(default=None, description="Timestamp when EV entered network")
    exit_time: Optional[float] = Field(default=None, description="Timestamp when EV passed intersection")
    travel_time: Optional[float] = Field(default=None, description="Total travel time in seconds")
    delay_seconds: Optional[float] = Field(default=None, description="Intersection delay experienced by emergency vehicle")


class TrafficSnapshotResponse(BaseModel):
    """Complete consolidated traffic telemetry snapshot for REST queries and WebSocket broadcasts."""
    simulation_id: Optional[str] = Field(default=None, description="Identifier of current simulation run")
    simulation_time: float = Field(default=0.0, description="Elapsed simulation time in seconds")
    step: int = Field(default=0, description="Current simulation step integer")
    controller: str = Field(default="fixed", description="Active traffic controller identifier")
    vehicles: VehiclesInfo = Field(default_factory=VehiclesInfo)
    vehicles_data: List[VehicleLiveState] = Field(default_factory=list, description="Live per-vehicle positions and telemetry")
    queues: QueuesInfo = Field(default_factory=QueuesInfo)
    speed: SpeedInfo = Field(default_factory=SpeedInfo)
    waiting: WaitingInfo = Field(default_factory=WaitingInfo)
    signal: SignalInfo = Field(default_factory=SignalInfo)
    ai: Optional[AIDecisionInfo] = Field(default=None, description="Present when DQN controller is running")
    emergency: Optional[EmergencyLiveInfo] = Field(default=None, description="Live emergency vehicle intelligence state")


class PredictionLiveInfo(BaseModel):
    """Real-time 30-second congestion forecast and empirical confidence interval."""
    model_config = ConfigDict(protected_namespaces=())

    model_available: bool = Field(default=False, description="Whether prediction model is active and loaded")
    model_name: Optional[str] = Field(default=None, description="Name of predictive model")
    predicted_score: float = Field(default=0.0, description="Predicted future congestion score (0-100)")
    current_score: float = Field(default=0.0, description="Current instantaneous congestion score (0-100)")
    congestion_level: str = Field(default="UNKNOWN", description="Classification ('FREE_FLOW', 'LOW', 'MODERATE', 'HIGH', 'SEVERE')")
    horizon_seconds: float = Field(default=30.0, description="Forecast horizon in seconds")
    trend: str = Field(default="STABLE", description="Predicted trend: 'INCREASING', 'DECREASING', 'STABLE'")
    confidence_lower: Optional[float] = Field(default=None, description="10th percentile of ensemble predictions (80% CI lower)")
    confidence_upper: Optional[float] = Field(default=None, description="90th percentile of ensemble predictions (80% CI upper)")
    std_dev: Optional[float] = Field(default=None, description="Standard deviation across ensemble estimators")
    baseline_score: Optional[float] = Field(default=None, description="Persistence baseline prediction (current score)")
    evaluated_samples: int = Field(default=0, description="Count of time-aligned verified forecast samples")
    live_mae: Optional[float] = Field(default=None, description="Cumulative live Mean Absolute Error against actual observations")
    live_rmse: Optional[float] = Field(default=None, description="Cumulative live Root Mean Squared Error against actual observations")
    baseline_mae: Optional[float] = Field(default=None, description="Cumulative live baseline MAE for comparison")
    mae_improvement_pct: Optional[float] = Field(default=None, description="Percentage MAE improvement over baseline")
    last_verified_actual: Optional[float] = Field(default=None, description="Latest verified actual congestion score at t+30s")
    last_verified_predicted: Optional[float] = Field(default=None, description="Predicted score matching the latest verified snapshot")


class TrafficSnapshotResponse(BaseModel):
    """Complete consolidated traffic telemetry snapshot for REST queries and WebSocket broadcasts."""
    simulation_id: Optional[str] = Field(default=None, description="Identifier of current simulation run")
    simulation_time: float = Field(default=0.0, description="Elapsed simulation time in seconds")
    step: int = Field(default=0, description="Current simulation step integer")
    controller: str = Field(default="fixed", description="Active traffic controller identifier")
    vehicles: VehiclesInfo = Field(default_factory=VehiclesInfo)
    vehicles_data: List[VehicleLiveState] = Field(default_factory=list, description="Live per-vehicle positions and telemetry")
    queues: QueuesInfo = Field(default_factory=QueuesInfo)
    speed: SpeedInfo = Field(default_factory=SpeedInfo)
    waiting: WaitingInfo = Field(default_factory=WaitingInfo)
    signal: SignalInfo = Field(default_factory=SignalInfo)
    ai: Optional[AIDecisionInfo] = Field(default=None, description="Present when DQN controller is running")
    emergency: Optional[EmergencyLiveInfo] = Field(default=None, description="Live emergency vehicle intelligence state")
    prediction: Optional[PredictionLiveInfo] = Field(default=None, description="Live 30-second congestion forecast and empirical confidence")
    decision: Optional[Dict[str, Any]] = Field(default=None, description="Complete 7-stage Agentic AI decision record")
