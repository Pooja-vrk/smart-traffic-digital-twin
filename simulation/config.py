"""Simulation and experiment configuration dataclasses.

Provides standardized configuration schemas for reproducible traffic experiments
across Fixed-Time, Adaptive, and Reinforcement Learning (DQN) controllers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class FixedTimeConfig:
    """Configuration for Fixed-Time traffic signal controller."""
    ns_green_seconds: float = 30.0
    ns_yellow_seconds: float = 3.0
    ew_green_seconds: float = 30.0
    ew_yellow_seconds: float = 3.0
    all_red_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AdaptiveConfig:
    """Configuration for Rule-Based Adaptive traffic signal controller."""
    min_green_seconds: float = 10.0
    max_green_seconds: float = 60.0
    yellow_seconds: float = 3.0
    all_red_seconds: float = 0.0
    pressure_difference_threshold: int = 3  # Minimum queue difference to trigger switch
    queue_speed_threshold: float = 0.1  # Vehicles with speed < threshold (m/s) considered queued

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DQNConfig:
    """Configuration hyperparameters for Deep Q-Network (DQN) Agent."""
    state_size: int = 6
    action_size: int = 3
    learning_rate: float = 0.001
    gamma: float = 0.95
    batch_size: int = 64
    replay_buffer_size: int = 50_000
    min_replay_size: int = 128
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay: float = 0.985
    target_update_frequency: int = 10  # Training steps between target network syncs
    decision_interval: int = 5  # Simulation seconds per DQN action decision
    min_green_seconds: float = 10.0
    max_green_seconds: float = 60.0
    yellow_seconds: float = 3.0
    max_queue_norm: float = 50.0  # Normalization factor for queue length features
    num_episodes: int = 50
    max_steps_per_episode: int = 500  # Total simulation seconds per episode

    # Reward weighting coefficients
    weight_queue: float = 0.5
    weight_wait_delta: float = 0.05
    weight_throughput: float = 2.0
    weight_switch: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentConfig:
    """Configuration parameters for a reproducible simulation experiment."""
    controller_type: str = "fixed"  # 'fixed' | 'adaptive' | 'dqn'
    simulation_steps: int = 1000
    step_length: float = 1.0
    seed: int = 42
    use_gui: bool = False
    tls_id: str = "center"
    traffic_demand_id: str = "routes.rou.xml"
    metric_collection_interval: int = 10
    sumocfg_path: Optional[str] = None
    model_path: Optional[str] = None

    # Controller-specific sub-configs
    fixed_time_config: FixedTimeConfig = field(default_factory=FixedTimeConfig)
    adaptive_config: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    dqn_config: DQNConfig = field(default_factory=DQNConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "controller_type": self.controller_type,
            "simulation_steps": self.simulation_steps,
            "step_length": self.step_length,
            "seed": self.seed,
            "use_gui": self.use_gui,
            "tls_id": self.tls_id,
            "traffic_demand_id": self.traffic_demand_id,
            "metric_collection_interval": self.metric_collection_interval,
            "sumocfg_path": self.sumocfg_path,
            "model_path": self.model_path,
            "fixed_time_config": self.fixed_time_config.to_dict(),
            "adaptive_config": self.adaptive_config.to_dict(),
            "dqn_config": self.dqn_config.to_dict(),
        }
