"""Evaluation pipeline for trained Deep Q-Network (DQN) traffic controller.

Loads trained neural network weights, runs deterministic greedy evaluation against
SUMO, and collects standardized traffic metrics for baseline comparison.

Usage:
    python -m ai.evaluate [--model MODEL_PATH] [--steps STEPS] [--seed SEED] [--gui]

Example:
    python -m ai.evaluate --steps 300 --seed 42
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.controllers.dqn_controller import DQNController
from simulation.environment import TrafficSimulationEnvironment
from simulation.metrics import AggregateMetrics


def parse_args() -> argparse.Namespace:
    default_model = PROJECT_ROOT / "ai" / "models" / "dqn_traffic_controller.pt"
    parser = argparse.ArgumentParser(description="Evaluate trained DQN traffic controller.")
    parser.add_argument("--model", type=str, default=str(default_model), help="Path to trained PyTorch DQN checkpoint.")
    parser.add_argument("--steps", type=int, default=300, help="Number of simulation evaluation steps (default: 300).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic evaluation (default: 42).")
    parser.add_argument("--gui", action="store_true", help="Run with SUMO-GUI visual simulation.")
    parser.add_argument("--save", action="store_true", default=True, help="Save evaluation JSON results (default: True).")
    return parser.parse_args()


def evaluate_dqn(
    model_path: Optional[str] = None,
    steps: int = 300,
    seed: int = 42,
    use_gui: bool = False,
    save: bool = True,
) -> tuple[AggregateMetrics, Dict[str, Any]]:
    """Execute DQN evaluation run and return aggregate metrics."""
    sys.stdout.reconfigure(line_buffering=True)
    resolved_model_path = Path(model_path) if model_path else PROJECT_ROOT / "ai" / "models" / "dqn_traffic_controller.pt"

    eval_id = f"eval_dqn_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    print("=" * 70)
    print(" AI-Driven Digital Twin — DQN Controller Evaluation")
    print("=" * 70)
    print(f" Evaluation ID:    {eval_id}")
    print(f" Model Checkpoint: {resolved_model_path}")
    print(f" Simulation Steps: {steps} seconds")
    print(f" Random Seed:      {seed}")
    print(f" Interface Mode:   {'SUMO-GUI (Visual)' if use_gui else 'Headless (CLI)'}")
    print("=" * 70)

    # Initialize DQN controller
    controller = DQNController(model_path=resolved_model_path)
    env = TrafficSimulationEnvironment(
        use_gui=use_gui,
        step_length=1.0,
        seed=seed,
        controller=controller,
    )

    try:
        env.start()
        print("\n[+] Simulation initialized. Executing greedy policy inference...\n")

        for step in range(1, steps + 1):
            env.step()

        aggregate = env.get_aggregate_metrics()
        stats = controller.get_stats()

        print("=" * 70)
        print(" DQN EVALUATION SUMMARY")
        print("=" * 70)
        print(f" Throughput:           {aggregate.total_vehicles_served} vehicles")
        print(f" Total Entered:        {aggregate.total_vehicles_entered} vehicles")
        print(f" Average Queue:        {aggregate.average_queue:.2f} vehicles")
        print(f" Maximum Queue:        {aggregate.max_queue} vehicles")
        print(f" Average Waiting Time: {aggregate.average_waiting_time:.2f} s")
        print(f" Total Waiting Time:   {aggregate.total_waiting_time:.2f} s")
        print(f" Average Delay/Veh:    {aggregate.average_delay:.2f} s/veh")
        print(f" Average Speed:        {aggregate.average_speed:.2f} m/s")
        print(f" Phase Changes:        {stats.get('phase_change_count', 0)}")
        print(f" CO2 Emissions Proxy:  {aggregate.total_co2_emission_kg:.4f} kg")
        print("=" * 70)

        result_payload = {
            "eval_id": eval_id,
            "controller": "dqn",
            "model_path": str(resolved_model_path),
            "timestamp": timestamp,
            "simulation_steps": steps,
            "seed": seed,
            "controller_stats": stats,
            "aggregate_metrics": aggregate.to_dict(),
        }

        if save:
            out_dir = PROJECT_ROOT / "data" / "experiments" / "dqn"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"evaluation_{seed}_{steps}s.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result_payload, f, indent=2)
            print(f"[+] Evaluation results saved to: {out_file}\n")

        return aggregate, stats

    finally:
        env.close()


def main() -> None:
    args = parse_args()
    evaluate_dqn(
        model_path=args.model,
        steps=args.steps,
        seed=args.seed,
        use_gui=args.gui,
        save=args.save,
    )


if __name__ == "__main__":
    main()
