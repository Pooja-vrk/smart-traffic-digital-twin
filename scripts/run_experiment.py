"""Run reproducible traffic experiments with Fixed-Time, Adaptive, or DQN controllers.

Usage:
    python scripts/run_experiment.py --controller [fixed|adaptive|dqn] [--steps STEPS] [--seed SEED] [--gui]

Examples:
    python scripts/run_experiment.py --controller fixed --steps 500
    python scripts/run_experiment.py --controller adaptive --steps 500 --gui
    python scripts/run_experiment.py --controller dqn --steps 500 --model ai/models/dqn_traffic_controller.pt
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
import uuid
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.config import AdaptiveConfig, DQNConfig, ExperimentConfig, FixedTimeConfig
from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.dqn_controller import DQNController
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.environment import TrafficSimulationEnvironment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a reproducible traffic control experiment using Fixed-Time, Adaptive, or DQN control."
    )
    parser.add_argument(
        "--controller",
        type=str,
        choices=["fixed", "adaptive", "dqn"],
        default="fixed",
        help="Signal control algorithm ('fixed', 'adaptive', or 'dqn').",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Path to trained PyTorch DQN checkpoint (only for --controller dqn).",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=500,
        help="Number of simulation steps / seconds to run (default: 500).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for traffic reproducibility (default: 42).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=50,
        help="Telemetry logging interval in simulation steps (default: 50).",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch SUMO-GUI for visual verification.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save experiment results to disk (default: True).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom file path for JSON results output.",
    )
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()

    run_id = f"exp_{args.controller}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    print("=" * 70)
    print(" AI-Driven Digital Twin for Smart City Traffic Management")
    print(f" Experiment Run: {run_id}")
    print("=" * 70)
    print(f" Controller:          {args.controller.upper()}")
    print(f" Simulation Steps:    {args.steps} seconds")
    print(f" Seed:                {args.seed}")
    print(f" Interface Mode:      {'SUMO-GUI (Visual)' if args.gui else 'Headless (CLI)'}")
    print("=" * 70)

    # Initialize controller
    if args.controller == "fixed":
        fixed_cfg = FixedTimeConfig(ns_green_seconds=30.0, ns_yellow_seconds=3.0, ew_green_seconds=30.0, ew_yellow_seconds=3.0)
        controller = FixedTimeController(config=fixed_cfg)
        controller_params = fixed_cfg.to_dict()
        category = "baseline"
    elif args.controller == "adaptive":
        adapt_cfg = AdaptiveConfig(min_green_seconds=10.0, max_green_seconds=60.0, yellow_seconds=3.0, pressure_difference_threshold=3)
        controller = AdaptiveController(config=adapt_cfg)
        controller_params = adapt_cfg.to_dict()
        category = "baseline"
    elif args.controller == "dqn":
        dqn_cfg = DQNConfig(min_green_seconds=10.0, max_green_seconds=60.0, yellow_seconds=3.0)
        model_p = args.model or str(PROJECT_ROOT / "ai" / "models" / "dqn_traffic_controller.pt")
        controller = DQNController(model_path=model_p, config=dqn_cfg)
        controller_params = dqn_cfg.to_dict()
        category = "dqn"

    env = TrafficSimulationEnvironment(
        use_gui=args.gui,
        step_length=1.0,
        seed=args.seed,
        controller=controller,
    )

    try:
        env.start()
        print("\n[+] Simulation initialized. Executing control steps...\n")

        for step in range(1, args.steps + 1):
            state = env.step()
            metrics = env.get_metrics()

            if step % args.interval == 0 or step == 1 or step == args.steps:
                print(f"--- [Step {step:04d} / {args.steps:04d}] | Phase: {metrics.current_phase_name:<10} ---")
                print(f"  Active Veh: {metrics.total_vehicles:<4} | Throughput: {metrics.throughput:<4} | Avg Speed: {metrics.average_speed:.2f} m/s")
                print(f"  Total Queue: {metrics.total_queue_length:<3} (N={metrics.queues_by_approach.get('north', 0)}, S={metrics.queues_by_approach.get('south', 0)}, E={metrics.queues_by_approach.get('east', 0)}, W={metrics.queues_by_approach.get('west', 0)})")
                print(f"  Total Wait: {metrics.total_waiting_time:.1f}s | CO2: {metrics.co2_emission_proxy_mg:.1f} mg/s")
                print()

        aggregate = env.get_aggregate_metrics()
        stats = controller.get_stats()

        print("=" * 70)
        print(" FINAL EXPERIMENT SUMMARY")
        print("=" * 70)
        print(f" Total Steps:          {aggregate.total_simulation_steps}")
        print(f" Throughput:           {aggregate.total_vehicles_served} vehicles")
        print(f" Total Entered:        {aggregate.total_vehicles_entered} vehicles")
        print(f" Average Queue:        {aggregate.average_queue:.2f} vehicles")
        print(f" Maximum Queue:        {aggregate.max_queue} vehicles")
        print(f" Average Waiting Time: {aggregate.average_waiting_time:.2f} s")
        print(f" Total Waiting Time:   {aggregate.total_waiting_time:.2f} s")
        print(f" Average Delay/Veh:    {aggregate.average_delay:.2f} s/veh")
        print(f" Average Speed:        {aggregate.average_speed:.2f} m/s")
        print(f" Phase Changes:        {stats.get('phase_change_count', 0)}")
        print(f" Est. CO2 Emissions:   {aggregate.total_co2_emission_kg:.4f} kg")
        print("=" * 70)

        result_payload = {
            "run_id": run_id,
            "controller": args.controller,
            "timestamp": timestamp,
            "simulation_duration_seconds": args.steps,
            "seed": args.seed,
            "traffic_configuration_id": "routes.rou.xml",
            "controller_parameters": controller_params,
            "controller_stats": stats,
            "aggregate_metrics": aggregate.to_dict(),
        }

        if args.save:
            output_dir = PROJECT_ROOT / "data" / "experiments" / category
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(args.output) if args.output else output_dir / f"{args.controller}_{args.seed}_{args.steps}s.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result_payload, f, indent=2)
            print(f"[+] Experiment results saved to: {output_path}\n")

    except KeyboardInterrupt:
        print("\n[!] Experiment interrupted by user (Ctrl+C).")
    except Exception as e:
        print(f"\n[!] Experiment failed with error: {e}")
        raise
    finally:
        print("[*] Closing TraCI session...")
        env.close()
        print("[OK] TraCI closed successfully.\n")


if __name__ == "__main__":
    main()
