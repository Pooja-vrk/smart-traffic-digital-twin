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
from simulation.scenario_generator import ScenarioConfig, ScenarioDemandGenerator
from simulation.environment import TrafficSimulationEnvironment
from simulation.controllers.fixed_time_controller import FixedTimeController


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
    parser.add_argument(
        "--emergency",
        action="store_true",
        help="Run emergency vehicle preemption scenario.",
    )
    parser.add_argument(
        "--approach",
        type=str,
        default="east",
        choices=["north", "south", "east", "west"],
        help="Approach corridor for emergency vehicle (default: east).",
    )
    parser.add_argument(
        "--emergency-type",
        type=str,
        default="ambulance",
        choices=["ambulance", "fire_engine", "emergency_vehicle"],
        help="Emergency vehicle type (default: ambulance).",
    )
    parser.add_argument(
        "--emergency-step",
        type=int,
        default=15,
        help="Simulation step to insert emergency vehicle (default: 15).",
    )
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    use_gui = not args.nogui

    print("=" * 65)
    print(" AI-Driven Digital Twin for Smart City Traffic Management")
    if args.emergency:
        print(" Emergency Vehicle Green Corridor Preemption Integration")
    else:
        print(" 4-Way Intersection Simulation & TraCI Foundation")
    print("=" * 65)
    print(f"Mode:             {'SUMO-GUI (Visual)' if use_gui else 'Headless (CLI)'}")
    print(f"Simulation Steps: {args.steps}")
    print(f"Report Interval:  Every {args.interval} steps")
    if args.emergency:
        print(f"Emergency Type:   {args.emergency_type} (ID: EV_01)")
        print(f"Approach:         {args.approach.upper()}")
        print(f"Spawn Step:       {args.emergency_step}s")
    print("=" * 65)

    sumocfg_path = None
    if args.emergency:
        cfg = ScenarioConfig(
            name=f"Emergency Preemption ({args.approach.upper()})",
            duration=args.steps,
            emergency_vehicle=True,
            emergency_approach=args.approach,
            emergency_step=args.emergency_step,
            emergency_vehicle_type=args.emergency_type,
        )
        _, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(cfg)

    from simulation.environment import TrafficSimulationEnvironment
    from simulation.controllers.fixed_time_controller import FixedTimeController

    sig_controller = FixedTimeController()
    env = TrafficSimulationEnvironment(
        sumocfg_path=sumocfg_path,
        use_gui=use_gui,
        controller=sig_controller,
        enable_emergency_priority=True,
    )

    try:
        env.start()
        print("\n[+] Simulation started successfully. Advancing simulation steps...\n")

        for step in range(1, args.steps + 1):
            state = env.step()
            metrics = env.get_metrics()

            if step % args.interval == 0 or step == 1 or step == args.steps or (state.emergency and state.emergency.active and (step % 5 == 0 or state.emergency.state in {"DETECTED", "VEHICLE_PASSED", "RESTORING_NORMAL"})):
                print(f"--- [Step {step:04d} / Time: {int(state.simulation_time):04d}s] ---")
                print(f"Active Vehicles:  {metrics.total_vehicles:<5} | Throughput:   {metrics.throughput}")
                print(f"Signal Phase:     {metrics.current_phase_name:<10} (Index: {metrics.current_phase})")
                print(f"North Queue:      {metrics.queues_by_approach.get('north', 0):<5} | South Queue:  {metrics.queues_by_approach.get('south', 0)}")
                print(f"East Queue:       {metrics.queues_by_approach.get('east', 0):<5} | West Queue:   {metrics.queues_by_approach.get('west', 0)}")
                print(f"Total Queue:      {metrics.total_queue_length:<5} | Avg Speed:    {metrics.average_speed:.2f} m/s")
                if state.emergency and state.emergency.active:
                    ev = state.emergency
                    if ev.distance_to_stopline is not None:
                        dist_txt = f"{ev.distance_to_stopline:.1f}m"
                    elif ev.state in {"VEHICLE_PASSED", "RESTORING_NORMAL"}:
                        dist_txt = "PASSED"
                    else:
                        dist_txt = "N/A"

                    if ev.eta_seconds is not None:
                        eta_txt = f"{ev.eta_seconds:.1f}s"
                    elif ev.state in {"VEHICLE_PASSED", "RESTORING_NORMAL"}:
                        eta_txt = "CLEARED"
                    elif ev.speed is not None and ev.speed < 1.0:
                        eta_txt = "QUEUED/SLOW"
                    else:
                        eta_txt = "N/A"

                    prio_txt = "ACTIVE" if ev.priority_active else ("RELEASED" if ev.state in {"VEHICLE_PASSED", "RESTORING_NORMAL"} else "PENDING")
                    spd_txt = f"{ev.speed:.2f}m/s" if ev.speed is not None else "N/A"
                    print(f"[EMERGENCY VEHICLE] ID={ev.vehicle_id} ({ev.vehicle_type}) | Approach={str(ev.approach).upper()} | State={ev.state}")
                    print(f"   Dist to Stopline: {dist_txt} | Speed: {spd_txt} | ETA: {eta_txt} | Priority: {prio_txt}")
                print()

            if use_gui and args.delay > 0:
                time.sleep(args.delay)

        print("[+] Simulation steps completed successfully.")

        if args.emergency:
            em_metrics = env.get_emergency_metrics()
            print("\n" + "=" * 65)
            print(" EMERGENCY VEHICLE CORRIDOR PERFORMANCE METRICS")
            print("=" * 65)
            if em_metrics:
                print(f"Vehicle ID:               {em_metrics.get('vehicle_id')}")
                print(f"Corridor Approach:        {str(em_metrics.get('approach')).upper()}")
                print(f"Actual Travel Time:       {em_metrics.get('travel_time'):.2f}s (Entry: {em_metrics.get('entry_time'):.1f}s, Exit: {em_metrics.get('exit_time'):.1f}s)")
                print(f"Free-Flow Baseline Time:  {em_metrics.get('free_flow_time'):.2f}s")
                print(f"Intersection Delay:       {em_metrics.get('intersection_delay'):.2f}s")
                print(f"Stopped Waiting Time:     {em_metrics.get('stopped_waiting_time'):.2f}s")
                print(f"Priority Green Duration:  {em_metrics.get('priority_duration'):.1f}s")
                print(f"Completed Successfully:   {em_metrics.get('completed')}")
            else:
                print("No emergency metrics recorded.")
            print("=" * 65 + "\n")

    except KeyboardInterrupt:
        print("\n[!] Simulation interrupted by user (Ctrl+C).")
    except Exception as e:
        print(f"\n[!] Simulation error occurred: {e}")
        raise
    finally:
        print("[*] Closing TraCI connection and cleaning up resources...")
        env.close()
        print("[OK] TraCI session closed cleanly.\n")


if __name__ == "__main__":
    main()
