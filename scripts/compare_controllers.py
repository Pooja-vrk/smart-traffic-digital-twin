"""Automated controller comparison runner: Fixed-Time vs Rule-Based Adaptive vs DQN.

Usage:
    python scripts/compare_controllers.py [--steps STEPS] [--seed SEED] [--model MODEL_PATH]

Example:
    python scripts/compare_controllers.py --steps 300 --seed 42
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

from simulation.config import AdaptiveConfig, DQNConfig, FixedTimeConfig
from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.dqn_controller import DQNController
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.environment import TrafficSimulationEnvironment
from simulation.metrics import AggregateMetrics


def parse_args() -> argparse.Namespace:
    default_model = PROJECT_ROOT / "ai" / "models" / "dqn_traffic_controller.pt"
    parser = argparse.ArgumentParser(
        description="Benchmark comparison between Fixed-Time, Adaptive, and DQN controllers."
    )
    parser.add_argument("--steps", type=int, default=300, help="Simulation steps per controller (default: 300).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic comparison (default: 42).")
    parser.add_argument("--model", type=str, default=str(default_model), help="Path to trained DQN model checkpoint.")
    return parser.parse_args()


def run_single_benchmark(
    controller_name: str,
    controller_instance: Any,
    steps: int,
    seed: int,
) -> tuple[AggregateMetrics, Dict[str, Any]]:
    """Execute a single controller benchmark run and return its aggregate metrics."""
    print(f"\n[+] Running {controller_name} benchmark ({steps} steps, seed={seed})...")
    env = TrafficSimulationEnvironment(
        use_gui=False,
        step_length=1.0,
        seed=seed,
        controller=controller_instance,
    )

    try:
        env.start()
        for step in range(1, steps + 1):
            env.step()
        aggregate = env.get_aggregate_metrics()
        stats = controller_instance.get_stats()
        print(f"[OK] {controller_name} completed. (Throughput={aggregate.total_vehicles_served}, AvgQueue={aggregate.average_queue:.2f})")
        return aggregate, stats
    finally:
        env.close()


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    comparison_id = f"cmp_tri_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    print("=" * 80)
    print(" AI-Driven Digital Twin for Smart City Traffic Management")
    print(" Tri-Controller Benchmark Comparison: Fixed-Time vs Adaptive vs DQN")
    print("=" * 80)
    print(f" Simulation Steps: {args.steps} seconds per run")
    print(f" Random Seed:      {args.seed}")
    print(f" Comparison ID:    {comparison_id}")
    print("=" * 80)

    # 1. Run Fixed-Time Controller
    fixed_cfg = FixedTimeConfig(ns_green_seconds=30.0, ns_yellow_seconds=3.0, ew_green_seconds=30.0, ew_yellow_seconds=3.0)
    fixed_controller = FixedTimeController(config=fixed_cfg)
    fixed_agg, fixed_stats = run_single_benchmark("Fixed-Time", fixed_controller, args.steps, args.seed)

    # 2. Run Adaptive Controller
    adapt_cfg = AdaptiveConfig(min_green_seconds=10.0, max_green_seconds=60.0, yellow_seconds=3.0, pressure_difference_threshold=3)
    adaptive_controller = AdaptiveController(config=adapt_cfg)
    adaptive_agg, adaptive_stats = run_single_benchmark("Rule-Based Adaptive", adaptive_controller, args.steps, args.seed)

    # 3. Run DQN Controller (if model exists)
    dqn_model_path = Path(args.model)
    dqn_agg: Optional[AggregateMetrics] = None
    dqn_stats: Optional[Dict[str, Any]] = None

    if dqn_model_path.is_file():
        try:
            dqn_controller = DQNController(model_path=dqn_model_path)
            dqn_agg, dqn_stats = run_single_benchmark("DQN Reinforcement Learning", dqn_controller, args.steps, args.seed)
        except Exception as e:
            print(f"[!] Warning: Could not evaluate DQN controller: {e}")
    else:
        print(f"\n[!] Notice: DQN model checkpoint not found at {dqn_model_path}. Train model to include DQN in comparison.")

    # Format Comparison Table
    print("\n" + "=" * 80)
    print(" CONTROLLER BENCHMARK COMPARISON RESULTS")
    print("=" * 80)
    if dqn_agg:
        print(f"{'Metric':<25} {'Fixed-Time':<15} {'Adaptive':<15} {'DQN (RL)':<15}")
        print("-" * 80)
        print(f"{'Throughput (veh)':<25} {fixed_agg.total_vehicles_served:<15} {adaptive_agg.total_vehicles_served:<15} {dqn_agg.total_vehicles_served:<15}")
        print(f"{'Total Entered (veh)':<25} {fixed_agg.total_vehicles_entered:<15} {adaptive_agg.total_vehicles_entered:<15} {dqn_agg.total_vehicles_entered:<15}")
        print(f"{'Average Queue (veh)':<25} {fixed_agg.average_queue:<15.2f} {adaptive_agg.average_queue:<15.2f} {dqn_agg.average_queue:<15.2f}")
        print(f"{'Max Queue (veh)':<25} {fixed_agg.max_queue:<15} {adaptive_agg.max_queue:<15} {dqn_agg.max_queue:<15}")
        print(f"{'Avg Waiting Time (s)':<25} {fixed_agg.average_waiting_time:<15.2f} {adaptive_agg.average_waiting_time:<15.2f} {dqn_agg.average_waiting_time:<15.2f}")
        print(f"{'Total Waiting Time (s)':<25} {fixed_agg.total_waiting_time:<15.2f} {adaptive_agg.total_waiting_time:<15.2f} {dqn_agg.total_waiting_time:<15.2f}")
        print(f"{'Avg Delay/Veh (s)':<25} {fixed_agg.average_delay:<15.2f} {adaptive_agg.average_delay:<15.2f} {dqn_agg.average_delay:<15.2f}")
        print(f"{'Average Speed (m/s)':<25} {fixed_agg.average_speed:<15.2f} {adaptive_agg.average_speed:<15.2f} {dqn_agg.average_speed:<15.2f}")
        print(f"{'Phase Changes':<25} {fixed_stats.get('phase_change_count', 0):<15} {adaptive_stats.get('phase_change_count', 0):<15} {dqn_stats.get('phase_change_count', 0):<15}")
        print(f"{'CO2 Emissions (kg)':<25} {fixed_agg.total_co2_emission_kg:<15.4f} {adaptive_agg.total_co2_emission_kg:<15.4f} {dqn_agg.total_co2_emission_kg:<15.4f}")
    else:
        print(f"{'Metric':<25} {'Fixed-Time':<15} {'Adaptive':<15}")
        print("-" * 80)
        print(f"{'Throughput (veh)':<25} {fixed_agg.total_vehicles_served:<15} {adaptive_agg.total_vehicles_served:<15}")
        print(f"{'Total Entered (veh)':<25} {fixed_agg.total_vehicles_entered:<15} {adaptive_agg.total_vehicles_entered:<15}")
        print(f"{'Average Queue (veh)':<25} {fixed_agg.average_queue:<15.2f} {adaptive_agg.average_queue:<15.2f}")
        print(f"{'Max Queue (veh)':<25} {fixed_agg.max_queue:<15} {adaptive_agg.max_queue:<15}")
        print(f"{'Avg Waiting Time (s)':<25} {fixed_agg.average_waiting_time:<15.2f} {adaptive_agg.average_waiting_time:<15.2f}")
        print(f"{'Total Waiting Time (s)':<25} {fixed_agg.total_waiting_time:<15.2f} {adaptive_agg.total_waiting_time:<15.2f}")
        print(f"{'Avg Delay/Veh (s)':<25} {fixed_agg.average_delay:<15.2f} {adaptive_agg.average_delay:<15.2f}")
        print(f"{'Average Speed (m/s)':<25} {fixed_agg.average_speed:<15.2f} {adaptive_agg.average_speed:<15.2f}")
        print(f"{'Phase Changes':<25} {fixed_stats.get('phase_change_count', 0):<15} {adaptive_stats.get('phase_change_count', 0):<15}")
        print(f"{'CO2 Emissions (kg)':<25} {fixed_agg.total_co2_emission_kg:<15.4f} {adaptive_agg.total_co2_emission_kg:<15.4f}")
    print("=" * 80)

    # Save comparison artifact
    comparison_payload = {
        "comparison_id": comparison_id,
        "timestamp": timestamp,
        "simulation_steps": args.steps,
        "seed": args.seed,
        "fixed_time": {
            "config": fixed_cfg.to_dict(),
            "stats": fixed_stats,
            "metrics": fixed_agg.to_dict(),
        },
        "adaptive": {
            "config": adapt_cfg.to_dict(),
            "stats": adaptive_stats,
            "metrics": adaptive_agg.to_dict(),
        },
    }

    if dqn_agg and dqn_stats:
        comparison_payload["dqn"] = {
            "model_path": str(dqn_model_path),
            "stats": dqn_stats,
            "metrics": dqn_agg.to_dict(),
        }

    output_dir = PROJECT_ROOT / "data" / "experiments" / "dqn"
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_file = output_dir / f"comparison_{args.seed}_{args.steps}s.json"
    with open(comparison_file, "w", encoding="utf-8") as f:
        json.dump(comparison_payload, f, indent=2)

    print(f"[+] Comparison data saved to: {comparison_file}\n")


if __name__ == "__main__":
    main()
