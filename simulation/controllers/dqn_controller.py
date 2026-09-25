"""Deep Q-Network (DQN) inference controller.

Wraps a trained DQN policy model into the standard BaseController interface,
enforcing safe signal actuations via SignalSafetyManager.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ai.dqn_agent import DQNAgent
from simulation.config import DQNConfig
from simulation.controllers.base_controller import BaseController, SignalSafetyManager
from simulation.state import TrafficState

logger = logging.getLogger(__name__)


class DQNController(BaseController):
    """Reinforcement learning controller performing greedy action selection from a trained PyTorch DQN model."""

    DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "ai" / "models" / "dqn_traffic_controller.pt"

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        config: Optional[DQNConfig] = None,
        tls_id: str = "center",
        agent: Optional[DQNAgent] = None,
    ) -> None:
        self.config = config or DQNConfig()
        self.model_path = Path(model_path) if model_path else self.DEFAULT_MODEL_PATH

        safety_mgr = SignalSafetyManager(
            min_green_seconds=self.config.min_green_seconds,
            yellow_seconds=self.config.yellow_seconds,
            max_green_seconds=self.config.max_green_seconds,
        )

        super().__init__(name="DQN-ReinforcementLearning", tls_id=tls_id, safety_manager=safety_mgr)

        if agent is not None:
            self.agent = agent
        else:
            self.agent = DQNAgent(config=self.config)
            self._load_model()

        self._active_green = SignalSafetyManager.NS_GREEN
        self._last_selected_action = 0

    def _load_model(self) -> None:
        """Load trained model weights from disk."""
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"DQN model checkpoint not found at: {self.model_path.resolve()}\n"
                f"Please train the model using 'python -m ai.train' before running DQN controller evaluation."
            )
        self.agent.load_checkpoint(self.model_path)
        logger.info("DQNController successfully loaded model from: %s", self.model_path)

    def reset(self) -> None:
        """Reset controller state."""
        super().reset()
        self._active_green = SignalSafetyManager.NS_GREEN
        self._last_selected_action = 0

    def decide_target_phase(self, state: TrafficState) -> int:
        """Query trained DQN policy to determine target green phase.

        Args:
            state: Instantaneous traffic state.

        Returns:
            int: Desired green phase (0 for NS_GREEN, 2 for EW_GREEN).
        """
        # 1. Extract normalized feature vector
        norm_features = state.to_normalized_feature_vector(
            max_queue=self.config.max_queue_norm,
            max_time=self.config.max_green_seconds,
        )

        # 2. Greedy action selection (evaluation mode, no exploration)
        action = self.agent.select_action(norm_features, evaluate=True)
        self._last_selected_action = action

        # 3. Map action to target green corridor
        current_safe_phase = self.safety_manager.current_phase

        if action == DQNAgent.ACTION_KEEP:
            if current_safe_phase in {SignalSafetyManager.NS_GREEN, SignalSafetyManager.NS_YELLOW}:
                self._active_green = SignalSafetyManager.NS_GREEN
            else:
                self._active_green = SignalSafetyManager.EW_GREEN
        elif action == DQNAgent.ACTION_REQUEST_NS:
            self._active_green = SignalSafetyManager.NS_GREEN
        elif action == DQNAgent.ACTION_REQUEST_EW:
            self._active_green = SignalSafetyManager.EW_GREEN

        return self._active_green

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats["config"] = self.config.to_dict()
        stats["last_selected_action"] = self._last_selected_action
        stats["last_action_name"] = DQNAgent.ACTION_NAMES.get(self._last_selected_action, "UNKNOWN")
        stats["model_path"] = str(self.model_path)
        return stats
