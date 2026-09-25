"""PyTorch Neural Network architecture for Deep Q-Network (DQN) value estimation.

Maps the 6-dimensional traffic state representation to Q-values for the 3 discrete signal actions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F


class DeepQNetwork(nn.Module):
    """Multi-Layer Perceptron (MLP) estimating action-value Q(s, a) functions."""

    def __init__(
        self,
        state_size: int = 6,
        action_size: int = 3,
        hidden_dim: int = 128,
    ) -> None:
        super().__init__()
        self.state_size = state_size
        self.action_size = action_size

        self.fc1 = nn.Linear(state_size, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, action_size)

        self._init_weights()

    def _init_weights(self) -> None:
        """Initialize linear layer weights using He / Kaiming normal initialization."""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, nonlinearity="relu")
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Forward pass computing Q-values for each discrete action.

        Args:
            state: Tensor of shape (batch_size, state_size) or (state_size,).

        Returns:
            torch.Tensor: Q-value estimates of shape (batch_size, action_size).
        """
        if state.dim() == 1:
            state = state.unsqueeze(0)

        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        q_values = self.fc3(x)
        return q_values

    def save_checkpoint(
        self,
        filepath: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save network state dictionary and optional training metadata."""
        save_path = Path(filepath)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "state_dict": self.state_dict(),
            "state_size": self.state_size,
            "action_size": self.action_size,
            "metadata": metadata or {},
        }
        torch.save(payload, save_path)

    def load_checkpoint(
        self,
        filepath: Union[str, Path],
        map_location: Optional[str] = "cpu",
    ) -> Dict[str, Any]:
        """Load network weights from saved checkpoint file."""
        load_path = Path(filepath)
        if not load_path.is_file():
            raise FileNotFoundError(f"DQN checkpoint not found at: {load_path}")

        checkpoint = torch.load(load_path, map_location=map_location)
        self.load_state_dict(checkpoint["state_dict"])
        return checkpoint.get("metadata", {})
