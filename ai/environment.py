"""Reinforcement Learning Environment wrapper for the 4-way SUMO intersection.

Provides standard Gym-compatible step, reset, and state extraction APIs
operating on top of TraCI and SignalSafetyManager.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from ai.reward import RewardBreakdown, RewardCalculator
from simulation.config import DQNConfig
from simulation.controllers.base_controller import SignalSafetyManager
from simulation.environment import TrafficSimulationEnvironment
from simulation.metrics import AggregateMetrics, SimulationMetrics
from simulation.state import TrafficState


class TrafficRLEnvironment:
    """Gym-like Reinforcement Learning environment interface for traffic signal control."""

    def __init__(
        self,
        config: Optional[DQNConfig] = None,
        use_gui: bool = False,
        seed: Optional[int] = 42,
        sumocfg_path: Optional[Path | str] = None,
    ) -> None:
        self.config = config or DQNConfig()
        self.use_gui = use_gui
        self.seed = seed
        self.sumocfg_path = sumocfg_path

        # Internal simulation instance
        self.sim_env = TrafficSimulationEnvironment(
            sumocfg_path=sumocfg_path,
            use_gui=use_gui,
            step_length=1.0,
            seed=seed,
        )

        # Safety manager enforcing physical traffic signal safety constraints
        self.safety_manager = SignalSafetyManager(
            min_green_seconds=self.config.min_green_seconds,
            yellow_seconds=self.config.yellow_seconds,
            max_green_seconds=self.config.max_green_seconds,
        )

        # Reward calculator
        self.reward_calculator = RewardCalculator(
            weight_queue=self.config.weight_queue,
            weight_wait_delta=self.config.weight_wait_delta,
            weight_throughput=self.config.weight_throughput,
            weight_switch=self.config.weight_switch,
        )

        self._current_step = 0
        self._episode_step = 0
        self._target_green = SignalSafetyManager.NS_GREEN
        self._previous_phase = SignalSafetyManager.NS_GREEN
        self._is_active = False

    def reset(self, seed: Optional[int] = None) -> List[float]:
        """Reset the SUMO simulation and return initial normalized state vector."""
        if seed is not None:
            self.seed = seed
            self.sim_env.traci_controller.seed = seed

        # Close existing session if active
        if self._is_active:
            self.sim_env.close()

        initial_state = self.sim_env.start(use_gui=self.use_gui)
        self._is_active = True

        self.safety_manager.reset(initial_phase=SignalSafetyManager.NS_GREEN)
        self.reward_calculator.reset(initial_state)

        self._current_step = 0
        self._episode_step = 0
        self._target_green = SignalSafetyManager.NS_GREEN
        self._previous_phase = SignalSafetyManager.NS_GREEN

        return initial_state.to_normalized_feature_vector(
            max_queue=self.config.max_queue_norm,
            max_time=self.config.max_green_seconds,
        )

    def step(self, action: int) -> Tuple[List[float], float, bool, Dict[str, Any]]:
        """Advance the environment by decision_interval seconds with the selected action.

        Action Mapping:
            0: KEEP_CURRENT_PHASE - Continue active green corridor
            1: REQUEST_NORTH_SOUTH - Request NS_GREEN (Phase 0)
            2: REQUEST_EAST_WEST - Request EW_GREEN (Phase 2)

        Returns:
            Tuple of (next_state_features, reward, done, info_dict).
        """
        if not self._is_active:
            raise RuntimeError("Environment is not active. Call reset() before stepping.")

        # 1. Map high-level action to requested target green phase
        current_safe_phase = self.safety_manager.current_phase
        if action == 0:  # KEEP
            # Keep whichever corridor is active
            if current_safe_phase in {SignalSafetyManager.NS_GREEN, SignalSafetyManager.NS_YELLOW}:
                self._target_green = SignalSafetyManager.NS_GREEN
            else:
                self._target_green = SignalSafetyManager.EW_GREEN
        elif action == 1:  # REQUEST NS
            self._target_green = SignalSafetyManager.NS_GREEN
        elif action == 2:  # REQUEST EW
            self._target_green = SignalSafetyManager.EW_GREEN

        # 2. Advance SUMO simulation by decision_interval seconds
        phase_changed_during_interval = False
        decision_steps = self.config.decision_interval
        latest_state = self.sim_env.get_state()

        for _ in range(decision_steps):
            # Compute legally safe phase through safety manager
            safe_phase = self.safety_manager.step(
                requested_green_phase=self._target_green,
                step_length=1.0,
            )

            if safe_phase != self._previous_phase:
                phase_changed_during_interval = True
                self._previous_phase = safe_phase

            self.sim_env.set_signal_phase(safe_phase)
            latest_state = self.sim_env.step()
            self._current_step += 1

        self._episode_step += 1

        # 3. Compute step reward
        metrics = self.sim_env.get_metrics()
        reward, breakdown = self.reward_calculator.compute_reward(
            current_state=latest_state,
            current_throughput=metrics.throughput,
            phase_changed=phase_changed_during_interval,
        )

        # 4. Check termination condition
        done = self._current_step >= self.config.max_steps_per_episode

        # 5. Extract next normalized state features
        next_state_vec = latest_state.to_normalized_feature_vector(
            max_queue=self.config.max_queue_norm,
            max_time=self.config.max_green_seconds,
        )

        info = {
            "step": self._current_step,
            "episode_step": self._episode_step,
            "raw_state": latest_state.to_dict(),
            "metrics": metrics.to_dict(),
            "reward_breakdown": breakdown.__dict__,
            "applied_phase": self.safety_manager.current_phase,
            "is_in_transition": self.safety_manager.is_in_transition,
        }

        return next_state_vec, reward, done, info

    def get_state(self) -> List[float]:
        """Query current normalized state vector."""
        state = self.sim_env.get_state()
        return state.to_normalized_feature_vector(
            max_queue=self.config.max_queue_norm,
            max_time=self.config.max_green_seconds,
        )

    def get_aggregate_metrics(self) -> AggregateMetrics:
        """Query aggregate metrics of the current episode run."""
        return self.sim_env.get_aggregate_metrics()

    def close(self) -> None:
        """Terminate simulation and release TraCI resources."""
        if self._is_active:
            self.sim_env.close()
            self._is_active = False

    def __enter__(self) -> TrafficRLEnvironment:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
