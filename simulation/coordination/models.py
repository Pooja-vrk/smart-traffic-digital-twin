"""Data models and enums for multi-intersection coordination and corridor progression.

Note on Network Architecture:
The SUMO road network (simulation/sumo/intersection.net.xml) defines a single physical
signalized junction at 'center' (INT-001, tlLogic id='center').
The peripheral nodes 'north', 'south', 'east', 'west' are boundary priority turnarounds.
In this digital twin, the gateway signals INT-N, INT-S, INT-E, and INT-W represent
*simulated arterial coordination intent* modeling adjacent signalized nodes, progression offsets,
and corridor preemption across a 5-node arterial network.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class CoordinationMode(str, enum.Enum):
    """Operational mode for arterial and network coordination."""
    ARTERY_EW = "ARTERY_EW"  # Prioritize East-West arterial green wave progression
    ARTERY_NS = "ARTERY_NS"  # Prioritize North-South transit corridor progression
    BALANCED_ADAPTIVE = "BALANCED_ADAPTIVE"  # Dynamically balance coordination based on multi-metric demand
    EMERGENCY_CORRIDOR = "EMERGENCY_CORRIDOR"  # Route preemption across all coordinated signals along EV path
    ISOLATED = "ISOLATED"  # Individual uncoordinated local actuation without progressive offsets


class ProgressionStatus(str, enum.Enum):
    """Progression state between adjacent signalized junctions."""
    SYNCHRONIZED = "SYNCHRONIZED"  # Normal green wave offset alignment
    PROGRESSION_ACTIVE = "PROGRESSION_ACTIVE"  # Platoon currently in progression window
    METERING_HOLD = "METERING_HOLD"  # Upstream signal holding flow to protect corridor / mitigate spillback
    ADVANCE_PREEMPTION = "ADVANCE_PREEMPTION"  # Downstream signal preemptively opening green for approaching EV
    SPILLBACK_MITIGATION = "SPILLBACK_MITIGATION"  # Active queue flush and upstream entry metering
    TRANSITION_CLEARANCE = "TRANSITION_CLEARANCE"  # Safe clearance yellow before phase / preemption shift
    ISOLATED = "ISOLATED"  # Uncoordinated local operation (no progressive offset applied)


@dataclass
class SpillbackMitigationDecision:
    """Explicit mitigation control decision for link queue spillback."""
    active: bool = False
    approach: Optional[str] = None
    queue_length: int = 0
    threshold: int = 14
    action: str = "NONE"  # 'NONE', 'METER_UPSTREAM_ENTRY', 'EXTEND_PRIMARY_GREEN'
    metering_rate_factor: float = 1.0  # 1.0 = unrestricted, 0.4 = 60% inflow throttling
    green_extension_seconds: float = 0.0
    explanation: str = "No spillback detected on connecting approach links."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CoordinatedNeighbor:
    """Simulated coordination intent state of an adjacent arterial gateway intersection.

    Gateway signals INT-N, INT-S, INT-E, and INT-W model boundary arterial junctions
    connecting to the central physical junction INT-001 (center).
    """
    intersection_id: str
    name: str
    direction: str  # 'north', 'south', 'east', 'west'
    corridor: str  # 'NS' or 'EW'
    distance_meters: float = 289.60
    ideal_travel_time_seconds: float = 20.85  # 289.60m / 13.89 m/s (~20.85s)
    current_offset_seconds: float = 0.0
    current_phase: int = 0
    phase_name: str = "GREEN"
    signal_state: str = "green"  # 'green', 'yellow', 'red' (simulated coordination intent)
    coordination_intent: str = "Simulated Arterial Intent"  # Explicit label for simulated signal intent
    is_physical_tls: bool = False  # False: gateway is a simulated intent node; center is physical SUMO TLS
    time_in_phase: float = 0.0
    queue_length: int = 0
    vehicle_count: int = 0
    progression_status: str = ProgressionStatus.SYNCHRONIZED.value
    preemption_active: bool = False
    coordination_role: str = "PEER"  # 'UPSTREAM', 'DOWNSTREAM', 'PEER', 'ISOLATED'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CorridorProgressionMetrics:
    """Progression metrics separating directly observed TraCI measurements from heuristic estimates.

    Direct observations reflect instantaneous ground truth from TraCI sensors.
    Heuristic scores represent algorithmic estimates of progression quality and platoon flow.
    """
    # ── Heuristic Algorithmic Scores (0-100%, 0 in ISOLATED mode) ───────
    arterial_ew_sync_score: float = 85.0  # Heuristic model estimate of EW green wave alignment
    arterial_ns_sync_score: float = 80.0  # Heuristic model estimate of NS transit corridor alignment
    overall_quality_score: float = 82.5  # Heuristic composite coordination quality index
    platoon_arrival_efficiency: float = 78.0  # Heuristic estimate of green-window arrival fraction

    # ── Directly Observed TraCI Measurements ────────────────────────────
    observed_mean_speed_mps: float = 13.89  # Ground-truth instantaneous average vehicle velocity
    observed_max_queue: int = 0  # Ground-truth worst-approach halted queue count
    observed_total_queue: int = 0  # Ground-truth total network halted vehicles

    # ── Operational Configuration & Progression Parameters ───────────────
    progression_speed_mps: float = 13.89  # Target progression design speed (50 km/h in m/s)
    cycle_length_seconds: float = 60.0  # Network coordinated cycle length in seconds
    active_corridor: str = "EAST_WEST"  # Dominant synchronized corridor ('EAST_WEST', 'NORTH_SOUTH', 'BALANCED', 'NONE')
    spillback_risk: str = "LOW"  # 'LOW', 'MODERATE', 'HIGH'
    coordination_mode: str = CoordinationMode.ARTERY_EW.value
    is_coordinated: bool = True  # False in ISOLATED mode
    emergency_preempted_corridor: Optional[str] = None
    spillback_mitigation: SpillbackMitigationDecision = field(default_factory=SpillbackMitigationDecision)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["spillback_mitigation"] = self.spillback_mitigation.to_dict()
        return data


@dataclass
class MultiIntersectionState:
    """Consolidated state representation of the coordinated multi-intersection digital twin."""
    primary_intersection_id: str = "INT-001"
    primary_tls_id: str = "center"  # Physical SUMO traffic light junction
    simulation_time: float = 0.0
    step: int = 0
    mode: str = CoordinationMode.ARTERY_EW.value
    cycle_length: float = 60.0
    primary_phase: int = 0
    primary_phase_name: str = "NS_GREEN"
    neighbors: Dict[str, CoordinatedNeighbor] = field(default_factory=dict)
    metrics: CorridorProgressionMetrics = field(default_factory=CorridorProgressionMetrics)
    emergency_active: bool = False
    emergency_approach: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_intersection_id": self.primary_intersection_id,
            "primary_tls_id": self.primary_tls_id,
            "simulation_time": round(self.simulation_time, 1),
            "step": self.step,
            "mode": self.mode,
            "cycle_length": round(self.cycle_length, 1),
            "primary_phase": self.primary_phase,
            "primary_phase_name": self.primary_phase_name,
            "neighbors": {k: v.to_dict() for k, v in self.neighbors.items()},
            "metrics": self.metrics.to_dict(),
            "emergency_active": self.emergency_active,
            "emergency_approach": self.emergency_approach,
            "spillback_mitigation": self.metrics.spillback_mitigation.to_dict(),
        }
