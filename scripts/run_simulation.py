"""Interactive runner script for the SUMO traffic simulation foundation.

Usage:
    python scripts/run_simulation.py [--nogui] [--steps STEPS] [--interval INTERVAL]

Examples:
    # Run with SUMO-GUI for visual verification:
    python scripts/run_simulation.py

    # Run in headless mode for 200 steps:
    python scripts/run_simulation.py --nogui --steps 200
"""

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.traci_controller import TraCIController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SUMO 4-way intersection simulation and print live traffic metrics."
    )
    parser.add_argument(
        "--nogui",
        action="store_true",
        help="Run in headless CLI mode without SUMO-GUI.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=200,
        help="Number of simulation steps to execute (default: 200).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Print metrics every N simulation steps (default: 10).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.02,
        help="Delay in seconds between GUI steps for smooth visualization (default: 0.02).",
    )
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    use_gui = not args.nogui

    print("=" * 65)
    print(" AI-Driven Digital Twin for Smart City Traffic Management")
    print(" Step 2: 4-Way Intersection Simulation & TraCI Foundation")
    print("=" * 65)
    print(f"Mode:             {'SUMO-GUI (Visual)' if use_gui else 'Headless (CLI)'}")
    print(f"Simulation Steps: {args.steps}")
    print(f"Report Interval:  Every {args.interval} steps")
    print("=" * 65)

    controller = TraCIController(use_gui=use_gui)

    try:
        controller.start_simulation()
        print("\n[+] Simulation started successfully. Advancing simulation steps...\n")

        for step in range(1, args.steps + 1):
            state = controller.step_simulation()
            metrics = controller.get_metrics()

            if step % args.interval == 0 or step == 1 or step == args.steps:
                print(f"--- [Step {step:04d} / Time: {int(state.simulation_time):04d}s] ---")
                print(f"Active Vehicles:  {metrics.total_vehicles:<5} | Throughput:   {metrics.throughput}")
                print(f"Signal Phase:     {metrics.current_phase_name:<10} (Index: {metrics.current_phase})")
                print(f"North Queue:      {metrics.queues_by_approach.get('north', 0):<5} | South Queue:  {metrics.queues_by_approach.get('south', 0)}")
                print(f"East Queue:       {metrics.queues_by_approach.get('east', 0):<5} | West Queue:   {metrics.queues_by_approach.get('west', 0)}")
                print(f"Total Queue:      {metrics.total_queue_length:<5} | Avg Speed:    {metrics.average_speed:.2f} m/s")
                print(f"Total Wait Time:  {metrics.total_waiting_time:.1f} s | CO2 Proxy:    {metrics.co2_emission_proxy_mg:.1f} mg/s")
                print()

            if use_gui and args.delay > 0:
                time.sleep(args.delay)

        print("[+] Simulation steps completed successfully.")

    except KeyboardInterrupt:
        print("\n[!] Simulation interrupted by user (Ctrl+C).")
    except Exception as e:
        print(f"\n[!] Simulation error occurred: {e}")
        raise
    finally:
        print("[*] Closing TraCI connection and cleaning up resources...")
        controller.close_simulation()
        print("[OK] TraCI session closed cleanly.\n")


if __name__ == "__main__":
    main()
