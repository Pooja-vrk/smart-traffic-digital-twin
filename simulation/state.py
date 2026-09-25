"""Traffic simulation state representation.

Defines structured dataclasses representing instantaneous digital twin
traffic states extracted via TraCI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ApproachState:
    """Traffic state for a single intersection approach direction."""
    direction: str  # 'north', 'south', 'east', 'west'
    inflow_edge: str
    vehicle_count: int = 0
    queue_length: int = 0  # Halted vehicles (speed < 0.1 m/s)
    waiting_time: float = 0.0  # Cumulative waiting time in seconds
    mean_speed: float = 0.0  # Average speed in m/s


@dataclass
class TrafficState:
    """Complete instantaneous state representation of the 4-way intersection.

    Designed to capture all operational metrics for digital twin telemetry
    while remaining directly convertible to reinforcement learning feature tensors.
    """
    simulation_time: float = 0.0
    step: int = 0

    # Approach-level states
    north: ApproachState = field(
        default_factory=lambda: ApproachState(direction="north", inflow_edge="N2C")
    )
    south: ApproachState = field(
        default_factory=lambda: ApproachState(direction="south", inflow_edge="S2C")
    )
    east: ApproachState = field(
        default_factory=lambda: ApproachState(direction="east", inflow_edge="E2C")
    )
    west: ApproachState = field(
        default_factory=lambda: ApproachState(direction="west", inflow_edge="W2C")
    )

    # Aggregated network metrics
    total_vehicles: int = 0
    total_queue: int = 0
    total_waiting_time: float = 0.0
    average_speed: float = 0.0

    # Traffic light state
    current_phase: int = 0
    current_phase_name: str = "NS_GREEN"
    time_since_phase_change: float = 0.0

    def to_feature_vector(self) -> List[float]:
        """Convert state into normalized feature vector compatible with DQN agent state space.

        Returns:
            List[float]: [
                north_queue,
                south_queue,
                east_queue,
                west_queue,
                current_phase,
                time_since_phase_change
            ]
        """
        return [
            float(self.north.queue_length),
            float(self.south.queue_length),
            float(self.east.queue_length),
            float(self.west.queue_length),
            float(self.current_phase),
            float(self.time_since_phase_change),
        ]

    def to_normalized_feature_vector(
        self,
        max_queue: float = 50.0,
        max_time: float = 60.0,
    ) -> List[float]:
        """Convert state into normalized continuous feature vector for DQN network input.

        Normalization strategy:
        - Queues: normalized by max expected approach queue (0.0 to 1.0+)
        - Current phase: categorical index normalized by 3.0 (0.0: NS_G, 0.33: NS_Y, 0.67: EW_G, 1.0: EW_Y)
        - Time in phase: normalized by max green time (0.0 to 1.0+)
        """
        return [
            float(self.north.queue_length) / max_queue,
            float(self.south.queue_length) / max_queue,
            float(self.east.queue_length) / max_queue,
            float(self.west.queue_length) / max_queue,
            float(self.current_phase) / 3.0,
            min(float(self.time_since_phase_change), max_time) / max_time,
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convert state dataclass to dictionary for JSON serialization and telemetry broadcast."""
        return asdict(self)
