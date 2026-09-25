"""Multi-objective reward function computation for traffic signal reinforcement learning.

Computes mathematically balanced step rewards balancing queue minimization,
waiting time reduction, throughput maximization, and phase switching penalties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from simulation.state import TrafficState


@dataclass
class RewardBreakdown:
    """Detailed components of the computed step reward."""
    total_reward: float
    queue_penalty: float
    waiting_delta_penalty: float
    throughput_reward: float
    switch_penalty: float


class RewardCalculator:
    """Stateful reward computer evaluating environmental transitions across decision steps."""

    def __init__(
        self,
        weight_queue: float = 0.5,
        weight_wait_delta: float = 0.05,
        weight_throughput: float = 2.0,
        weight_switch: float = 1.0,
        reward_clip: Optional[float] = 25.0,
    ) -> None:
        self.weight_queue = weight_queue
        self.weight_wait_delta = weight_wait_delta
        self.weight_throughput = weight_throughput
        self.weight_switch = weight_switch
        self.reward_clip = reward_clip

        self._previous_waiting_time: float = 0.0
        self._previous_throughput: int = 0
        self._previous_phase: Optional[int] = None

    def reset(self, initial_state: Optional[TrafficState] = None) -> None:
        """Reset internal history baselines."""
        self._previous_waiting_time = initial_state.total_waiting_time if initial_state else 0.0
        self._previous_throughput = 0
        self._previous_phase = initial_state.current_phase if initial_state else None

    def compute_reward(
        self,
        current_state: TrafficState,
        current_throughput: int,
        phase_changed: bool = False,
    ) -> tuple[float, RewardBreakdown]:
        """Compute the instantaneous step reward and its constituent sub-metrics.

        Equation:
            Reward = - (w_q * TotalQueue) - (w_w * DeltaWait) + (w_tp * DeltaThroughput) - (w_s * SwitchPenalty)

        Args:
            current_state: Traffic state at the end of the decision interval.
            current_throughput: Cumulative throughput count at the end of interval.
            phase_changed: Whether a signal phase transition occurred during the interval.

        Returns:
            Tuple of (scalar_reward, RewardBreakdown).
        """
        # 1. Total queue penalty (halted vehicles)
        total_queue = float(current_state.total_queue)
        queue_penalty = self.weight_queue * total_queue

        # 2. Delta waiting time penalty (change in delay accumulation)
        current_wait = float(current_state.total_waiting_time)
        delta_wait = max(0.0, current_wait - self._previous_waiting_time)
        wait_penalty = self.weight_wait_delta * delta_wait
        self._previous_waiting_time = current_wait

        # 3. Delta throughput reward (vehicles cleared through junction)
        delta_tp = max(0, current_throughput - self._previous_throughput)
        tp_reward = self.weight_throughput * float(delta_tp)
        self._previous_throughput = current_throughput

        # 4. Phase switching penalty (discourages unnecessary oscillation)
        switch_penalty = self.weight_switch if phase_changed else 0.0

        # Raw total reward
        raw_reward = -queue_penalty - wait_penalty + tp_reward - switch_penalty

        # Optional symmetric clipping for gradient stability
        if self.reward_clip is not None:
            clipped_reward = max(-self.reward_clip, min(self.reward_clip, raw_reward))
        else:
            clipped_reward = raw_reward

        breakdown = RewardBreakdown(
            total_reward=round(clipped_reward, 3),
            queue_penalty=round(queue_penalty, 3),
            waiting_delta_penalty=round(wait_penalty, 3),
            throughput_reward=round(tp_reward, 3),
            switch_penalty=round(switch_penalty, 3),
        )

        return float(clipped_reward), breakdown
