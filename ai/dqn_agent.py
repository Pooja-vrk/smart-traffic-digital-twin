"""Deep Q-Network (DQN) Agent for autonomous traffic signal control.

Manages policy/target neural networks, experience replay sampling, epsilon-greedy
action selection, Bellman loss optimization, and model checkpoint serialization.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from ai.neural_network import DeepQNetwork
from ai.replay_buffer import ReplayBuffer
from simulation.config import DQNConfig

logger = logging.getLogger(__name__)


class DQNAgent:
    """Deep Q-Network reinforcement learning agent."""

    # Action enumeration
    ACTION_KEEP = 0
    ACTION_REQUEST_NS = 1
    ACTION_REQUEST_EW = 2

    ACTION_NAMES = {
        0: "KEEP_CURRENT_PHASE",
        1: "REQUEST_NORTH_SOUTH",
        2: "REQUEST_EAST_WEST",
    }

    def __init__(
        self,
        config: Optional[DQNConfig] = None,
        device: Optional[Union[str, torch.device]] = None,
    ) -> None:
        self.config = config or DQNConfig()

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Policy and Target Neural Networks
        self.policy_net = DeepQNetwork(
            state_size=self.config.state_size,
            action_size=self.config.action_size,
            hidden_dim=128,
        ).to(self.device)

        self.target_net = DeepQNetwork(
            state_size=self.config.state_size,
            action_size=self.config.action_size,
            hidden_dim=128,
        ).to(self.device)

        self.update_target_network()
        self.target_net.eval()

        # Optimizer and Loss
        self.optimizer = optim.Adam(
            self.policy_net.parameters(),
            lr=self.config.learning_rate,
        )
        self.criterion = nn.SmoothL1Loss()  # Huber loss for stability

        # Experience Replay Memory
        self.memory = ReplayBuffer(capacity=self.config.replay_buffer_size)

        # Exploration parameters
        self.epsilon = self.config.epsilon_start
        self.epsilon_end = self.config.epsilon_end
        self.epsilon_decay = self.config.epsilon_decay

        # Step counters
        self.train_step_count = 0
        self.total_episodes = 0

    def update_target_network(self) -> None:
        """Synchronize target network weights with policy network."""
        self.target_net.load_state_dict(self.policy_net.state_dict())
        logger.debug("Target network weights synchronized.")

    def select_action(
        self,
        state: Union[List[float], np.ndarray],
        evaluate: bool = False,
    ) -> int:
        """Select an action using epsilon-greedy exploration strategy.

        Args:
            state: Continuous feature state vector of length 6.
            evaluate: If True, disables random exploration (greedy policy).

        Returns:
            int: Selected action index (0, 1, or 2).
        """
        if not evaluate and random.random() < self.epsilon:
            # Exploration: Random action
            return random.randrange(self.config.action_size)

        # Exploitation: Greedy action with highest estimated Q-value
        self.policy_net.eval()
        with torch.no_grad():
            state_tensor = torch.tensor(
                state,
                dtype=torch.float32,
                device=self.device,
            ).unsqueeze(0)
            q_values = self.policy_net(state_tensor)
            action = int(torch.argmax(q_values, dim=1).item())
        self.policy_net.train()
        return action

    def store_transition(
        self,
        state: Union[List[float], np.ndarray],
        action: int,
        reward: float,
        next_state: Union[List[float], np.ndarray],
        done: bool,
    ) -> None:
        """Store environmental transition into replay buffer."""
        self.memory.push(state, action, reward, next_state, done)

    def train_step(self) -> Optional[float]:
        """Perform one optimization step on a mini-batch sampled from replay memory.

        Returns:
            Optional[float]: Loss value if optimization occurred, else None.
        """
        if len(self.memory) < self.config.min_replay_size or len(self.memory) < self.config.batch_size:
            return None

        states, actions, rewards, next_states, dones = self.memory.sample(
            batch_size=self.config.batch_size,
            device=self.device,
        )

        # 1. Compute current Q(s, a) estimates from policy network
        current_q_values = self.policy_net(states).gather(1, actions)

        # 2. Compute Bellman target: r + gamma * max_a' Q_target(s', a') * (1 - done)
        with torch.no_grad():
            next_q_values = self.target_net(next_states).max(1)[0].unsqueeze(1)
            target_q_values = rewards + (self.config.gamma * next_q_values * (1.0 - dones))

        # 3. Compute Huber loss
        loss = self.criterion(current_q_values, target_q_values)

        # 4. Backpropagation with gradient clipping
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        self.train_step_count += 1

        # Periodically synchronize target network
        if self.train_step_count % self.config.target_update_frequency == 0:
            self.update_target_network()

        return float(loss.item())

    def decay_epsilon(self) -> float:
        """Decay exploration rate according to configured geometric decay schedule."""
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        return self.epsilon

    def save_checkpoint(
        self,
        filepath: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save complete agent checkpoint including policy weights, target weights, optimizer state."""
        save_path = Path(filepath)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        meta = {
            "config": self.config.to_dict(),
            "epsilon": self.epsilon,
            "train_step_count": self.train_step_count,
            "total_episodes": self.total_episodes,
        }
        if metadata:
            meta.update(metadata)

        payload = {
            "policy_net_state": self.policy_net.state_dict(),
            "target_net_state": self.target_net.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "metadata": meta,
        }
        torch.save(payload, save_path)
        logger.info("Saved DQN checkpoint to: %s", save_path)

    def load_checkpoint(
        self,
        filepath: Union[str, Path],
    ) -> Dict[str, Any]:
        """Load complete agent checkpoint from disk."""
        load_path = Path(filepath)
        if not load_path.is_file():
            raise FileNotFoundError(f"DQN checkpoint file not found at: {load_path}")

        checkpoint = torch.load(load_path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint["policy_net_state"])
        self.target_net.load_state_dict(checkpoint.get("target_net_state", checkpoint["policy_net_state"]))
        if "optimizer_state" in checkpoint:
            self.optimizer.load_state_dict(checkpoint["optimizer_state"])

        metadata = checkpoint.get("metadata", {})
        if "epsilon" in metadata:
            self.epsilon = float(metadata["epsilon"])
        if "train_step_count" in metadata:
            self.train_step_count = int(metadata["train_step_count"])
        if "total_episodes" in metadata:
            self.total_episodes = int(metadata["total_episodes"])

        logger.info("Loaded DQN checkpoint from: %s", load_path)
        return metadata
