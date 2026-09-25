"""Deep Q-Network (DQN) training pipeline.

Trains an autonomous reinforcement learning policy agent against the SUMO
4-way intersection environment, recording episode statistics and serializing
model checkpoints.

Usage:
    python -m ai.train [--episodes EPISODES] [--steps STEPS] [--seed SEED]

Example:
    python -m ai.train --episodes 30 --steps 300 --seed 42
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import torch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.dqn_agent import DQNAgent
from ai.environment import TrafficRLEnvironment
from simulation.config import DQNConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def set_seed(seed: int) -> None:
    """Set random seeds across Python, NumPy, and PyTorch for reproducible training."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train DQN Agent for Smart Traffic Signal Control.")
    parser.add_argument("--episodes", type=int, default=30, help="Number of training episodes (default: 30).")
    parser.add_argument("--steps", type=int, default=300, help="Simulation steps per episode (default: 300).")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed (default: 42).")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate for Adam optimizer (default: 0.001).")
    parser.add_argument("--gamma", type=float, default=0.95, help="Discount factor gamma (default: 0.95).")
    parser.add_argument("--batch-size", type=int, default=64, help="Mini-batch size (default: 64).")
    parser.add_argument("--epsilon-start", type=float, default=1.0, help="Initial epsilon exploration rate (default: 1.0).")
    parser.add_argument("--epsilon-end", type=float, default=0.05, help="Minimum epsilon exploration rate (default: 0.05).")
    parser.add_argument("--epsilon-decay", type=float, default=0.98, help="Geometric decay factor per episode (default: 0.98).")
    parser.add_argument("--decision-interval", type=int, default=5, help="Seconds between DQN decisions (default: 5).")
    parser.add_argument("--model-path", type=str, default=None, help="Custom output model checkpoint path.")
    return parser.parse_args()


def train_dqn(
    episodes: int = 30,
    max_steps_per_episode: int = 300,
    seed: int = 42,
    lr: float = 0.001,
    gamma: float = 0.95,
    batch_size: int = 64,
    epsilon_start: float = 1.0,
    epsilon_end: float = 0.05,
    epsilon_decay: float = 0.98,
    decision_interval: int = 5,
    model_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete DQN training loop."""
    sys.stdout.reconfigure(line_buffering=True)
    set_seed(seed)

    run_id = f"dqn_train_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    default_model_dir = PROJECT_ROOT / "ai" / "models"
    default_model_dir.mkdir(parents=True, exist_ok=True)
    out_model_path = Path(model_path) if model_path else default_model_dir / "dqn_traffic_controller.pt"
    best_model_path = default_model_dir / "dqn_best_model.pt"

    config = DQNConfig(
        num_episodes=episodes,
        max_steps_per_episode=max_steps_per_episode,
        learning_rate=lr,
        gamma=gamma,
        batch_size=batch_size,
        epsilon_start=epsilon_start,
        epsilon_end=epsilon_end,
        epsilon_decay=epsilon_decay,
        decision_interval=decision_interval,
    )

    print("=" * 75)
    print(" AI-Driven Digital Twin — Deep Q-Network (DQN) Training Pipeline")
    print("=" * 75)
    print(f" Run ID:             {run_id}")
    print(f" Total Episodes:     {episodes}")
    print(f" Steps per Episode:  {max_steps_per_episode} s")
    print(f" Decision Interval:  {decision_interval} s")
    print(f" Learning Rate:      {lr} | Gamma: {gamma} | Batch Size: {batch_size}")
    print(f" Epsilon Schedule:   {epsilon_start} -> {epsilon_end} (decay: {epsilon_decay})")
    print(f" Model Output:       {out_model_path}")
    print("=" * 75)

    env = TrafficRLEnvironment(config=config, use_gui=False, seed=seed)
    agent = DQNAgent(config=config)

    # History tracking
    episode_rewards: List[float] = []
    episode_losses: List[float] = []
    episode_epsilons: List[float] = []
    episode_queues: List[float] = []
    episode_throughputs: List[int] = []
    episode_delays: List[float] = []

    best_reward = -float("inf")
    start_time = time.time()

    try:
        for ep in range(1, episodes + 1):
            ep_seed = seed + (ep * 7)
            state = env.reset(seed=ep_seed)
            done = False

            total_ep_reward = 0.0
            ep_loss_list: List[float] = []

            while not done:
                action = agent.select_action(state, evaluate=False)
                next_state, reward, done, info = env.step(action)

                agent.store_transition(state, action, reward, next_state, done)
                loss = agent.train_step()
                if loss is not None:
                    ep_loss_list.append(loss)

                total_ep_reward += reward
                state = next_state

            # Post-episode bookkeeping
            agent.decay_epsilon()
            agent.total_episodes = ep

            agg = env.get_aggregate_metrics()
            mean_loss = float(np.mean(ep_loss_list)) if ep_loss_list else 0.0

            episode_rewards.append(round(total_ep_reward, 2))
            episode_losses.append(round(mean_loss, 4))
            episode_epsilons.append(round(agent.epsilon, 4))
            episode_queues.append(round(agg.average_queue, 2))
            episode_throughputs.append(agg.total_vehicles_served)
            episode_delays.append(round(agg.average_delay, 2))

            rolling_window = min(ep, 10)
            rolling_avg_reward = np.mean(episode_rewards[-rolling_window:])

            print(
                f"Episode {ep:02d}/{episodes:02d} | "
                f"Reward: {total_ep_reward:>7.1f} | "
                f"Avg(10): {rolling_avg_reward:>7.1f} | "
                f"Eps: {agent.epsilon:.3f} | "
                f"Loss: {mean_loss:.4f} | "
                f"AvgQ: {agg.average_queue:.2f} | "
                f"TP: {agg.total_vehicles_served}"
            )

            # Checkpoint best model
            if total_ep_reward > best_reward:
                best_reward = total_ep_reward
                agent.save_checkpoint(
                    best_model_path,
                    metadata={"best_reward": best_reward, "best_episode": ep},
                )

        # Save final checkpoint
        agent.save_checkpoint(
            out_model_path,
            metadata={
                "run_id": run_id,
                "timestamp": timestamp,
                "final_epsilon": agent.epsilon,
                "episodes_completed": episodes,
                "best_reward": best_reward,
            },
        )

    finally:
        env.close()

    elapsed_time = time.time() - start_time
    print("=" * 75)
    print(f"[OK] Training completed in {elapsed_time:.1f} seconds.")
    print(f"     Best Episode Reward: {best_reward:.2f}")
    print(f"     Saved Latest Model:  {out_model_path}")
    print(f"     Saved Best Model:    {best_model_path}")
    print("=" * 75)

    history_payload = {
        "run_id": run_id,
        "timestamp": timestamp,
        "elapsed_seconds": round(elapsed_time, 2),
        "seed": seed,
        "hyperparameters": config.to_dict(),
        "episodes": episodes,
        "episode_rewards": episode_rewards,
        "episode_losses": episode_losses,
        "episode_epsilons": episode_epsilons,
        "episode_average_queues": episode_queues,
        "episode_throughputs": episode_throughputs,
        "episode_average_delays": episode_delays,
        "best_reward": round(best_reward, 2),
        "model_path": str(out_model_path),
        "best_model_path": str(best_model_path),
    }

    history_dir = PROJECT_ROOT / "data" / "experiments" / "dqn"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / f"training_history_{run_id}.json"
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_payload, f, indent=2)

    print(f"[+] Training history logged to: {history_file}\n")
    return history_payload


def main() -> None:
    args = parse_args()
    train_dqn(
        episodes=args.episodes,
        max_steps_per_episode=args.steps,
        seed=args.seed,
        lr=args.lr,
        gamma=args.gamma,
        batch_size=args.batch_size,
        epsilon_start=args.epsilon_start,
        epsilon_end=args.epsilon_end,
        epsilon_decay=args.epsilon_decay,
        decision_interval=args.decision_interval,
        model_path=args.model_path,
    )


if __name__ == "__main__":
    main()
