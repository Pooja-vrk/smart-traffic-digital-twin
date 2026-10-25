"""Data structures and typed models for the Agentic Traffic Decision Engine.

Defines standardized observations, detected conditions, and unified decision records
used across all traffic signal controllers.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ControllerType(str, Enum):
    """Supported traffic controller types."""
    FIXED = "fixed"
    ADAPTIVE = "adaptive"
    DQN = "dqn"
    UNKNOWN = "unknown"


class ActionName(str, Enum):
    """Standardized action identifiers."""
    KEEP = "KEEP"
    REQUEST_NORTH_SOUTH = "REQUEST_NORTH_SOUTH"
    REQUEST_EAST_WEST = "REQUEST_EAST_WEST"
    CYCLE_PHASE = "CYCLE_PHASE"
    EXTEND_GREEN = "EXTEND_GREEN"
    REQUEST_EMERGENCY_PRIORITY = "REQUEST_EMERGENCY_PRIORITY"


class SafetyValidationStatus(str, Enum):
    """Outcome of SignalSafetyManager transition enforcement."""
    APPROVED = "APPROVED"
    RESTRICTED_MIN_GREEN = "RESTRICTED_MIN_GREEN"
    IN_YELLOW_CLEARANCE = "IN_YELLOW_CLEARANCE"
    OVERRIDE_MAX_GREEN = "OVERRIDE_MAX_GREEN"
    EMERGENCY_OVERRIDE = "EMERGENCY_OVERRIDE"


class ExecutionStatus(str, Enum):
    """Execution status on TraCI traffic light system."""
    EXECUTED = "EXECUTED"
    DEFERRED = "DEFERRED"
    FALLBACK = "FALLBACK"
    FAILED = "FAILED"
    SAFE_SHUTDOWN = "SAFE_SHUTDOWN"


class CongestionLevel(str, Enum):
    """Measurable traffic congestion classification."""
    FREE_FLOW = "FREE_FLOW"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


@dataclass
class TrafficObservation:
    """Standardized observation containing verified measurements from the simulation."""
    simulation_time: float = 0.0
    simulation_id: Optional[str] = None
    step: int = 0
    controller: str = "Unknown"
    queue_length_by_approach: Dict[str, int] = field(default_factory=dict)
    waiting_time_by_approach: Dict[str, float] = field(default_factory=dict)
    mean_speed_by_approach: Dict[str, float] = field(default_factory=dict)
    vehicle_counts: Dict[str, int] = field(default_factory=dict)
    current_signal_phase: int = 0
    current_phase_name: str = "NS_GREEN"
    time_in_current_phase: float = 0.0
    is_in_transition: bool = False
    emergency_vehicle: Dict[str, Any] = field(default_factory=dict)
    measurements_available: bool = True
    unavailable_fields: List[str] = field(default_factory=list)

    @classmethod
    def from_traffic_state(
        cls,
        state: Any,
        controller_name: str,
        simulation_id: Optional[str] = None,
        safety_manager: Optional[Any] = None,
        metrics: Optional[Any] = None,
    ) -> TrafficObservation:
        """Factory creating a standardized observation from a TrafficState."""
        unavailable: List[str] = []

        # Extract queue lengths
        queues: Dict[str, int] = {}
        for direction in ("north", "south", "east", "west"):
            approach = getattr(state, direction, None)
            if approach is not None and hasattr(approach, "queue_length"):
                queues[direction] = int(approach.queue_length)
            else:
                queues[direction] = 0
                unavailable.append(f"queue_{direction}")
        queues["total"] = int(getattr(state, "total_queue", sum(queues.values())))

        # Extract waiting times
        waiting_times: Dict[str, float] = {}
        for direction in ("north", "south", "east", "west"):
            approach = getattr(state, direction, None)
            if approach is not None and hasattr(approach, "waiting_time"):
                waiting_times[direction] = round(float(approach.waiting_time), 2)
            else:
                waiting_times[direction] = 0.0
                unavailable.append(f"waiting_{direction}")
        waiting_times["total"] = round(float(getattr(state, "total_waiting_time", sum(waiting_times.values()))), 2)

        # Extract mean speeds
        speeds: Dict[str, float] = {}
        for direction in ("north", "south", "east", "west"):
            approach = getattr(state, direction, None)
            if approach is not None and hasattr(approach, "mean_speed"):
                speeds[direction] = round(float(approach.mean_speed), 2)
            else:
                speeds[direction] = 0.0
                unavailable.append(f"speed_{direction}")
        speeds["average"] = round(float(getattr(state, "average_speed", 0.0)), 2)

        # Extract vehicle counts
        total_veh = int(getattr(state, "total_vehicles", 0))
        entered_veh = int(getattr(metrics, "total_vehicles", total_veh)) if metrics else total_veh
        completed_veh = int(getattr(metrics, "throughput", 0)) if metrics else 0
        vehicle_counts = {
            "total": total_veh,
            "entered": entered_veh,
            "completed": completed_veh,
        }

        # Signal state and safety manager details
        curr_phase = int(getattr(state, "current_phase", 0))
        phase_name = str(getattr(state, "current_phase_name", "UNKNOWN"))
        time_in_phase = float(getattr(state, "time_since_phase_change", 0.0))
        is_trans = False

        if safety_manager is not None:
            time_in_phase = float(getattr(safety_manager, "time_in_current_phase", time_in_phase))
            is_trans = bool(getattr(safety_manager, "is_in_transition", False))

        # Emergency vehicle data
        ev_data: Dict[str, Any] = {"active": False, "state": "IDLE"}
        ev_state = getattr(state, "emergency", None)
        if ev_state is not None and getattr(ev_state, "active", False):
            ev_data = {
                "active": True,
                "vehicle_id": getattr(ev_state, "vehicle_id", None),
                "vehicle_type": getattr(ev_state, "vehicle_type", "emergency"),
                "approach": getattr(ev_state, "approach", None),
                "state": getattr(ev_state, "state", "IDLE"),
                "distance": getattr(ev_state, "distance", None),
                "speed": getattr(ev_state, "speed", None),
                "priority_requested": getattr(ev_state, "priority_requested", False),
                "priority_approved": getattr(ev_state, "priority_approved", False),
                "priority_active": getattr(ev_state, "priority_active", False),
                "safety_status": getattr(ev_state, "safety_status", "NORMAL"),
            }

        return cls(
            simulation_time=float(getattr(state, "simulation_time", 0.0)),
            simulation_id=simulation_id,
            step=int(getattr(state, "step", 0)),
            controller=controller_name,
            queue_length_by_approach=queues,
            waiting_time_by_approach=waiting_times,
            mean_speed_by_approach=speeds,
            vehicle_counts=vehicle_counts,
            current_signal_phase=curr_phase,
            current_phase_name=phase_name,
            time_in_current_phase=round(time_in_phase, 1),
            is_in_transition=is_trans,
            emergency_vehicle=ev_data,
            measurements_available=len(unavailable) == 0,
            unavailable_fields=unavailable,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert observation to dictionary."""
        return asdict(self)


@dataclass
class DetectedConditions:
    """Analyzed traffic conditions derived from the observation."""
    ns_pressure: int = 0
    ew_pressure: int = 0
    pressure_imbalance: int = 0
    dominant_corridor: str = "BALANCED"  # "NORTH_SOUTH", "EAST_WEST", "BALANCED"
    congestion_level: str = "FREE_FLOW"
    total_queue: int = 0
    average_speed: float = 0.0
    total_waiting_time: float = 0.0
    min_green_satisfied: bool = True
    max_green_exceeded: bool = False
    emergency_detected: bool = False
    emergency_approach: Optional[str] = None
    in_yellow_transition: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert conditions to dictionary."""
        return asdict(self)


@dataclass
class AgenticDecisionRecord:
    """Consistent, immutable typed decision record generated at each simulation step."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    simulation_id: Optional[str] = None
    simulation_time: float = 0.0
    step: int = 0
    controller: str = "Unknown"
    observation: TrafficObservation = field(default_factory=TrafficObservation)
    detected_conditions: DetectedConditions = field(default_factory=DetectedConditions)
    requested_action: str = "KEEP"
    requested_phase: int = 0
    validated_action: str = "APPROVED"
    validated_phase: int = 0
    is_safety_override: bool = False
    safety_status: str = "SAFE"
    safety_reason: str = ""
    decision_reason: str = ""
    execution_status: str = "EXECUTED"
    q_values: Optional[List[float]] = None
    reward: Optional[float] = None
    prediction: Optional[Dict[str, Any]] = None
    emergency: Optional[Dict[str, Any]] = None
    post_action_metrics: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete decision record to dictionary."""
        return {
            "decision_id": self.decision_id,
            "simulation_id": self.simulation_id,
            "simulation_time": self.simulation_time,
            "step": self.step,
            "controller": self.controller,
            "observation": self.observation.to_dict() if hasattr(self.observation, "to_dict") else self.observation,
            "detected_conditions": self.detected_conditions.to_dict() if hasattr(self.detected_conditions, "to_dict") else self.detected_conditions,
            "requested_action": self.requested_action,
            "requested_phase": self.requested_phase,
            "validated_action": self.validated_action,
            "validated_phase": self.validated_phase,
            "is_safety_override": self.is_safety_override,
            "safety_status": self.safety_status,
            "safety_reason": self.safety_reason,
            "decision_reason": self.decision_reason,
            "execution_status": self.execution_status,
            "q_values": list(self.q_values) if self.q_values is not None else None,
            "reward": self.reward,
            "prediction": self.prediction,
            "emergency": self.emergency,
            "post_action_metrics": self.post_action_metrics,
        }
