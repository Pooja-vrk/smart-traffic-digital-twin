"""Traffic performance metrics calculation and aggregation.

Computes standard macroscopic and microscopic traffic performance indicators
directly from TraCI simulation data.

QUEUE DEFINITION:
A queued vehicle is strictly defined across all controllers as an active vehicle
on an intersection approach inflow edge (N2C, S2C, E2C, W2C) whose instantaneous
speed is less than 0.1 m/s (halting speed threshold).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class SimulationMetrics:
    """Consolidated instantaneous metrics snapshot representing network-wide performance."""
    simulation_time: float = 0.0
    step: int = 0
    total_vehicles: int = 0
    total_queue_length: int = 0
    average_speed: float = 0.0
    total_waiting_time: float = 0.0
    throughput: int = 0  # Cumulative completed trips
    current_phase: int = 0
    current_phase_name: str = "NS_GREEN"
    co2_emission_proxy_mg: float = 0.0  # Instantaneous CO2 emission proxy (mg/s)

    # Breakdown by approach
    queues_by_approach: Dict[str, int] = field(default_factory=dict)
    waiting_time_by_approach: Dict[str, float] = field(default_factory=dict)
    vehicle_count_by_approach: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary representation."""
        return asdict(self)


@dataclass
class AggregateMetrics:
    """Aggregated experiment-level performance metrics computed over an entire simulation run."""
    total_simulation_steps: int = 0
    total_simulation_time: float = 0.0
    total_vehicles_served: int = 0  # Completed trips (throughput)
    total_vehicles_entered: int = 0  # Unique vehicles observed in network
    average_queue: float = 0.0  # Mean total queue length across all steps
    max_queue: int = 0  # Peak total queue length observed
    average_waiting_time: float = 0.0  # Mean per-step accumulated waiting time
    total_waiting_time: float = 0.0  # Total cumulative waiting time across all vehicles (seconds)
    average_speed: float = 0.0  # Mean speed across all active vehicle steps (m/s)
    average_delay: float = 0.0  # Mean delay per entered vehicle (seconds/vehicle)
    phase_changes: int = 0  # Total number of signal phase transitions
    total_co2_emission_kg: float = 0.0  # Cumulative estimated CO2 emissions (kg)

    # Approach-level breakdown
    average_queue_by_approach: Dict[str, float] = field(default_factory=dict)
    max_queue_by_approach: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert aggregate metrics to dictionary representation."""
        return asdict(self)


class MetricsCalculator:
    """Stateful metric tracker monitoring cumulative throughput, queues, delays, and emissions."""

    APPROACH_EDGES = {
        "north": "N2C",
        "south": "S2C",
        "east": "E2C",
        "west": "W2C",
    }

    PHASE_NAMES = {
        0: "NS_GREEN",
        1: "NS_YELLOW",
        2: "EW_GREEN",
        3: "EW_YELLOW",
    }

    def __init__(self) -> None:
        self._all_seen_vehicles: Set[str] = set()
        self._arrived_vehicles: Set[str] = set()
        self._cumulative_throughput: int = 0

        # Step-by-step history accumulators
        self._step_queues: List[int] = []
        self._step_queues_by_approach: Dict[str, List[int]] = {
            "north": [],
            "south": [],
            "east": [],
            "west": [],
        }
        self._step_speeds: List[float] = []
        self._step_wait_times: List[float] = []
        self._step_co2_mg: List[float] = []
        self._last_phase: Optional[int] = None
        self._phase_changes: int = 0
        self._total_steps: int = 0
        self._last_sim_time: float = 0.0

    def reset(self) -> None:
        """Reset internal trip accounting counters and history accumulators."""
        self._all_seen_vehicles.clear()
        self._arrived_vehicles.clear()
        self._cumulative_throughput = 0
        self._step_queues.clear()
        for direction in self._step_queues_by_approach:
            self._step_queues_by_approach[direction].clear()
        self._step_speeds.clear()
        self._step_wait_times.clear()
        self._step_co2_mg.clear()
        self._last_phase = None
        self._phase_changes = 0
        self._total_steps = 0
        self._last_sim_time = 0.0

    def compute(
        self,
        traci_module: Any,
        tls_id: str = "center",
        step: int = 0,
        sim_time: float = 0.0,
        time_since_phase_change: float = 0.0,
    ) -> SimulationMetrics:
        """Extract and compute performance metrics for the current simulation step."""
        self._total_steps = step
        self._last_sim_time = sim_time

        # Active vehicle IDs currently in simulation
        active_veh_ids = traci_module.vehicle.getIDList()
        total_active_vehicles = len(active_veh_ids)

        for veh_id in active_veh_ids:
            self._all_seen_vehicles.add(veh_id)

        # Update throughput tracking using arriving/arrived vehicles
        arrived_this_step = traci_module.simulation.getArrivedIDList()
        for veh_id in arrived_this_step:
            if veh_id not in self._arrived_vehicles:
                self._arrived_vehicles.add(veh_id)
                self._cumulative_throughput += 1

        # Query traffic light state
        try:
            current_phase = int(traci_module.trafficlight.getPhase(tls_id))
        except Exception:
            current_phase = 0

        if self._last_phase is not None and current_phase != self._last_phase:
            self._phase_changes += 1
        self._last_phase = current_phase

        phase_name = self.PHASE_NAMES.get(current_phase, f"PHASE_{current_phase}")

        # Compute speed, waiting time, and CO2 emissions
        total_speed = 0.0
        total_waiting_time = 0.0
        total_co2_mg = 0.0

        for veh_id in active_veh_ids:
            try:
                speed = traci_module.vehicle.getSpeed(veh_id)
                wait_time = traci_module.vehicle.getWaitingTime(veh_id)
                co2_mg = traci_module.vehicle.getCO2Emission(veh_id)  # in mg/s

                total_speed += speed
                total_waiting_time += wait_time
                if co2_mg > 0:
                    total_co2_mg += co2_mg
            except Exception:
                continue

        avg_speed = (total_speed / total_active_vehicles) if total_active_vehicles > 0 else 0.0

        # Compute approach-level metrics (speed < 0.1 m/s)
        queues_by_approach: Dict[str, int] = {}
        waiting_by_approach: Dict[str, float] = {}
        vehicles_by_approach: Dict[str, int] = {}
        total_queue = 0

        for direction, edge_id in self.APPROACH_EDGES.items():
            try:
                queue = traci_module.edge.getLastStepHaltingNumber(edge_id)
                veh_count = traci_module.edge.getLastStepVehicleNumber(edge_id)
                wait_time = traci_module.edge.getWaitingTime(edge_id)
            except Exception:
                queue = 0
                veh_count = 0
                wait_time = 0.0

            queues_by_approach[direction] = queue
            waiting_by_approach[direction] = float(wait_time)
            vehicles_by_approach[direction] = veh_count
            total_queue += queue
            self._step_queues_by_approach[direction].append(queue)

        # Accumulate history for aggregate metrics
        self._step_queues.append(total_queue)
        if total_active_vehicles > 0:
            self._step_speeds.append(avg_speed)
        self._step_wait_times.append(total_waiting_time)
        self._step_co2_mg.append(total_co2_mg)

        return SimulationMetrics(
            simulation_time=sim_time,
            step=step,
            total_vehicles=total_active_vehicles,
            total_queue_length=total_queue,
            average_speed=round(avg_speed, 2),
            total_waiting_time=round(total_waiting_time, 2),
            throughput=self._cumulative_throughput,
            current_phase=current_phase,
            current_phase_name=phase_name,
            co2_emission_proxy_mg=round(total_co2_mg, 2),
            queues_by_approach=queues_by_approach,
            waiting_time_by_approach=waiting_by_approach,
            vehicle_count_by_approach=vehicles_by_approach,
        )

    def get_aggregate_summary(self) -> AggregateMetrics:
        """Compute consolidated aggregate metrics summarizing the completed simulation run."""
        num_steps = len(self._step_queues)
        avg_queue = (sum(self._step_queues) / num_steps) if num_steps > 0 else 0.0
        max_queue = max(self._step_queues) if self._step_queues else 0
        avg_speed = (sum(self._step_speeds) / len(self._step_speeds)) if self._step_speeds else 0.0
        avg_wait = (sum(self._step_wait_times) / num_steps) if num_steps > 0 else 0.0
        total_wait = sum(self._step_wait_times)
        total_co2_kg = (sum(self._step_co2_mg) / 1_000_000.0)

        total_entered = len(self._all_seen_vehicles)
        avg_delay = (total_wait / total_entered) if total_entered > 0 else 0.0

        avg_q_approach: Dict[str, float] = {}
        max_q_approach: Dict[str, int] = {}
        for direction, q_list in self._step_queues_by_approach.items():
            avg_q_approach[direction] = round((sum(q_list) / len(q_list)) if q_list else 0.0, 2)
            max_q_approach[direction] = max(q_list) if q_list else 0

        return AggregateMetrics(
            total_simulation_steps=self._total_steps,
            total_simulation_time=self._last_sim_time,
            total_vehicles_served=self._cumulative_throughput,
            total_vehicles_entered=total_entered,
            average_queue=round(avg_queue, 2),
            max_queue=max_queue,
            average_waiting_time=round(avg_wait, 2),
            total_waiting_time=round(total_wait, 2),
            average_speed=round(avg_speed, 2),
            average_delay=round(avg_delay, 2),
            phase_changes=self._phase_changes,
            total_co2_emission_kg=round(total_co2_kg, 4),
            average_queue_by_approach=avg_q_approach,
            max_queue_by_approach=max_q_approach,
        )
