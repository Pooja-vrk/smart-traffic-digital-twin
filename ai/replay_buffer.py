"""Experience Replay Buffer for Deep Q-Network reinforcement learning.

Stores transition tuples (state, action, reward, next_state, done) and provides
uniform random batch sampling to break temporal correlations during training.
"""

from __future__ import annotations

import random
from collections import deque
from typing import List, NamedTuple, Tuple, Union

import numpy as np
import torch


class Experience(NamedTuple):
    """Single transition step tuple."""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


class ReplayBuffer:
    """Fixed-capacity ring buffer storing transition experiences for DQN mini-batch training."""

    def __init__(self, capacity: int = 50_000) -> None:
        self.capacity = capacity
        self.buffer: deque[Experience] = deque(maxlen=capacity)

    def push(
        self,
        state: Union[List[float], np.ndarray],
        action: int,
        reward: float,
        next_state: Union[List[float], np.ndarray],
        done: bool,
    ) -> None:
        """Store a single experience transition in the replay buffer."""
        exp = Experience(
            state=np.array(state, dtype=np.float32),
            action=int(action),
            reward=float(reward),
            next_state=np.array(next_state, dtype=np.float32),
            done=bool(done),
        )
        self.buffer.append(exp)

    def sample(
        self,
        batch_size: int,
        device: torch.device = torch.device("cpu"),
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Uniformly sample a mini-batch of transitions converted to PyTorch tensors.

        Args:
            batch_size: Number of transitions to sample.
            device: Target torch device (CPU/GPU).

        Returns:
            Tuple of (states, actions, rewards, next_states, dones) tensors.
        """
        if len(self.buffer) < batch_size:
            raise ValueError(f"Not enough samples in buffer ({len(self.buffer)}) to sample batch of size {batch_size}")

        batch = random.sample(self.buffer, batch_size)

        states = torch.tensor(np.array([e.state for e in batch]), dtype=torch.float32, device=device)
        actions = torch.tensor(np.array([e.action for e in batch]), dtype=torch.long, device=device).unsqueeze(1)
        rewards = torch.tensor(np.array([e.reward for e in batch]), dtype=torch.float32, device=device).unsqueeze(1)
        next_states = torch.tensor(np.array([e.next_state for e in batch]), dtype=torch.float32, device=device)
        dones = torch.tensor(np.array([e.done for e in batch]), dtype=torch.float32, device=device).unsqueeze(1)

        return states, actions, rewards, next_states, dones

    def __len__(self) -> int:
        return len(self.buffer)

    def clear(self) -> None:
        self.buffer.clear()
