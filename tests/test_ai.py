"""Automated unit and integration tests for Deep Q-Network (DQN) AI layer."""

import tempfile
from pathlib import Path
import numpy as np
import pytest
import torch

from ai.dqn_agent import DQNAgent
from ai.environment import TrafficRLEnvironment
from ai.neural_network import DeepQNetwork
from ai.replay_buffer import ReplayBuffer
from ai.reward import RewardCalculator
from simulation.config import DQNConfig
from simulation.controllers.base_controller import SignalSafetyManager
from simulation.controllers.dqn_controller import DQNController
from simulation.state import TrafficState


def test_dqn_neural_network_architecture():
    """Verify DeepQNetwork initialization, forward pass shape, and output dimensions."""
    net = DeepQNetwork(state_size=6, action_size=3, hidden_dim=128)
    assert net.state_size == 6
    assert net.action_size == 3

    # Test single state input (shape: [6])
    dummy_state = torch.randn(6)
    q_vals_single = net(dummy_state)
    assert q_vals_single.shape == (1, 3)

    # Test batch state input (shape: [32, 6])
    dummy_batch = torch.randn(32, 6)
    q_vals_batch = net(dummy_batch)
    assert q_vals_batch.shape == (32, 3)


def test_replay_buffer_operations():
    """Verify ReplayBuffer insertion, sampling shapes, and capacity limits."""
    buffer = ReplayBuffer(capacity=100)
    assert len(buffer) == 0

    # Insert 10 transitions
    for i in range(10):
        s = np.random.randn(6).astype(np.float32)
        a = i % 3
        r = float(i)
        next_s = np.random.randn(6).astype(np.float32)
        done = (i == 9)
        buffer.push(s, a, r, next_s, done)

    assert len(buffer) == 10

    # Sample batch of 4
    states, actions, rewards, next_states, dones = buffer.sample(batch_size=4)
    assert states.shape == (4, 6)
    assert actions.shape == (4, 1)
    assert rewards.shape == (4, 1)
    assert next_states.shape == (4, 6)
    assert dones.shape == (4, 1)


def test_epsilon_greedy_action_selection():
    """Verify exploration when epsilon=1.0 and greedy exploitation when evaluate=True."""
    agent = DQNAgent(config=DQNConfig(epsilon_start=1.0, epsilon_end=0.0))
    dummy_state = [0.1, 0.2, 0.0, 0.0, 0.0, 0.5]

    # With epsilon=1.0, should select actions in range [0, 2]
    action_explore = agent.select_action(dummy_state, evaluate=False)
    assert action_explore in {0, 1, 2}

    # In evaluate mode, greedy deterministic action
    action_eval1 = agent.select_action(dummy_state, evaluate=True)
    action_eval2 = agent.select_action(dummy_state, evaluate=True)
    assert action_eval1 in {0, 1, 2}
    assert action_eval1 == action_eval2, "Greedy evaluation must be deterministic"


def test_target_network_synchronization():
    """Verify target network synchronization copies policy weights correctly."""
    agent = DQNAgent()
    # Mutate policy weights manually
    with torch.no_grad():
        agent.policy_net.fc1.weight.fill_(7.0)

    # Before sync, target weights differ
    assert not torch.allclose(agent.policy_net.fc1.weight, agent.target_net.fc1.weight)

    # After sync, weights match exactly
    agent.update_target_network()
    assert torch.allclose(agent.policy_net.fc1.weight, agent.target_net.fc1.weight)


def test_reward_calculator():
    """Verify RewardCalculator computation and breakdown values."""
    calc = RewardCalculator(
        weight_queue=0.5,
        weight_wait_delta=0.05,
        weight_throughput=2.0,
        weight_switch=1.0,
    )
    state = TrafficState(total_queue=4, total_waiting_time=100.0)
    calc.reset(initial_state=TrafficState(total_queue=0, total_waiting_time=80.0))

    reward, breakdown = calc.compute_reward(
        current_state=state,
        current_throughput=3,
        phase_changed=True,
    )

    # Delta wait = 100 - 80 = 20 -> wait_penalty = 0.05 * 20 = 1.0
    # Queue penalty = 0.5 * 4 = 2.0
    # Throughput reward = 2.0 * 3 = 6.0
    # Switch penalty = 1.0
    # Total = -2.0 - 1.0 + 6.0 - 1.0 = 2.0
    assert breakdown.queue_penalty == 2.0
    assert breakdown.waiting_delta_penalty == 1.0
    assert breakdown.throughput_reward == 6.0
    assert breakdown.switch_penalty == 1.0
    assert reward == 2.0


def test_checkpoint_save_and_load():
    """Verify DQN model checkpoints can be serialized and deserialized with metadata intact."""
    agent = DQNAgent(config=DQNConfig(learning_rate=0.005))
    agent.epsilon = 0.45
    agent.total_episodes = 12

    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as tmp_f:
        tmp_path = Path(tmp_f.name)

    try:
        agent.save_checkpoint(tmp_path, metadata={"custom_note": "unit_test"})
        assert tmp_path.is_file()

        new_agent = DQNAgent(config=DQNConfig())
        meta = new_agent.load_checkpoint(tmp_path)

        assert meta["custom_note"] == "unit_test"
        assert new_agent.epsilon == 0.45
        assert new_agent.total_episodes == 12

        # Verify weights match
        for p1, p2 in zip(agent.policy_net.parameters(), new_agent.policy_net.parameters()):
            assert torch.allclose(p1, p2)
    finally:
        if tmp_path.is_file():
            tmp_path.unlink()


def test_missing_checkpoint_raises_error():
    """Verify DQNController raises clear FileNotFoundError when model path does not exist."""
    fake_path = Path("ai/models/non_existent_model_12345.pt")
    with pytest.raises(FileNotFoundError, match="DQN model checkpoint not found"):
        DQNController(model_path=fake_path)


def test_rl_environment_lifecycle():
    """Verify TrafficRLEnvironment reset, step, and state feature extraction."""
    env = TrafficRLEnvironment(
        config=DQNConfig(decision_interval=2, max_steps_per_episode=10),
        use_gui=False,
        seed=42,
    )

    try:
        initial_state = env.reset(seed=42)
        assert isinstance(initial_state, list)
        assert len(initial_state) == 6

        # Step with ACTION_KEEP (0)
        next_state, reward, done, info = env.step(action=0)
        assert len(next_state) == 6
        assert isinstance(reward, float)
        assert isinstance(done, bool)
        assert "reward_breakdown" in info
        assert "applied_phase" in info
        assert info["step"] == 2  # 1 step with decision_interval=2 -> 2 sim seconds

    finally:
        env.close()


def test_dqn_controller_safety_integration():
    """Verify DQNController requests pass through SignalSafetyManager and prevent unsafe jumps."""
    # Create agent with initialized weights
    agent = DQNAgent()
    controller = DQNController(agent=agent)

    # Force initial phase to NS_GREEN
    assert controller.safety_manager.current_phase == SignalSafetyManager.NS_GREEN

    # Simulate state wanting EW_GREEN
    state = TrafficState(current_phase=0, time_since_phase_change=12.0)
    state.north.queue_length = 0
    state.east.queue_length = 15

    # Mock traci controller dummy
    class MockTraCI:
        step_length = 1.0
        applied_phases = []
        def set_tls_phase(self, phase):
            self.applied_phases.append(phase)

    mock_traci = MockTraCI()
    controller.safety_manager.time_in_current_phase = 12.0  # Min green satisfied

    # Force action to REQUEST_EW (2)
    controller.decide_target_phase = lambda s: SignalSafetyManager.EW_GREEN

    applied_phase = controller.step(state, mock_traci)
    # Must enter NS_YELLOW (1) first, NOT EW_GREEN (2) directly!
    assert applied_phase == SignalSafetyManager.NS_YELLOW
    assert controller.safety_manager.is_in_transition
