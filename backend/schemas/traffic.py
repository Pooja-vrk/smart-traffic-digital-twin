"""Pydantic schemas for instantaneous traffic state and telemetry snapshots."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


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
    elapsed_seconds: float = Field(default=0.0, description="Time spent in the currently active phase")


class AIDecisionInfo(BaseModel):
    """Reinforcement learning decision telemetry when DQN controller is active."""
    action: str = Field(default="KEEP", description="Action name chosen by policy ('KEEP', 'SWITCH_NS', 'SWITCH_EW')")
    action_id: int = Field(default=0, description="Discrete action index (0, 1, 2)")
    requested_phase: int = Field(default=0, description="Target phase requested by DQN")
    approved: bool = Field(default=True, description="Whether SignalSafetyManager approved the requested phase")
    reason: Optional[str] = Field(default=None, description="Explanation or state details from AI controller")


class TrafficSnapshotResponse(BaseModel):
    """Complete consolidated traffic telemetry snapshot for REST queries and WebSocket broadcasts."""
    simulation_id: Optional[str] = Field(default=None, description="Identifier of current simulation run")
    simulation_time: float = Field(default=0.0, description="Elapsed simulation time in seconds")
    step: int = Field(default=0, description="Current simulation step integer")
    controller: str = Field(default="fixed", description="Active traffic controller identifier")
    vehicles: VehiclesInfo = Field(default_factory=VehiclesInfo)
    queues: QueuesInfo = Field(default_factory=QueuesInfo)
    speed: SpeedInfo = Field(default_factory=SpeedInfo)
    waiting: WaitingInfo = Field(default_factory=WaitingInfo)
    signal: SignalInfo = Field(default_factory=SignalInfo)
    ai: Optional[AIDecisionInfo] = Field(default=None, description="Present when DQN controller is running")
