"""Multi-Metric Adaptive Traffic Signal Optimization Engine.

Calculates optimal signal timing allocations by evaluating:
1. Halted queue lengths (spatial obstruction).
2. Accumulated delay / waiting time (temporal penalty).
3. Traffic density / active vehicle occupancy on inflow links.
4. Dynamic green split allocation between conflicting corridors subject to cycle constraints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from simulation.state import TrafficState

logger = logging.getLogger(__name__)


@dataclass
class CorridorDemandMetrics:
    """Multi-metric demand breakdown for a corridor (North-South or East-West)."""
    corridor: str
    queue_length: int
    waiting_time_seconds: float
    vehicle_count: int
    mean_speed_mps: float
    composite_pressure: float
    recommended_green_seconds: float


class AdaptiveSignalOptimizer:
    """Calculates multi-metric dynamic pressure and optimal green splits under cycle constraints."""

    def __init__(
        self,
        weight_queue: float = 1.0,
        weight_waiting: float = 0.5,
        weight_density: float = 0.3,
        reference_wait_seconds: float = 30.0,
        min_green_seconds: float = 10.0,
        max_green_seconds: float = 60.0,
        cycle_length_seconds: float = 60.0,
        yellow_seconds: float = 3.0,
    ) -> None:
        # Validate constructor parameters
        if weight_queue < 0.0 or weight_waiting < 0.0 or weight_density < 0.0:
            raise ValueError("Demand weights (weight_queue, weight_waiting, weight_density) must be non-negative (>= 0).")
        if reference_wait_seconds <= 0.0:
            raise ValueError(f"reference_wait_seconds ({reference_wait_seconds}) must be strictly positive (> 0).")
        if min_green_seconds <= 0.0:
            raise ValueError(f"min_green_seconds ({min_green_seconds}) must be strictly positive (> 0).")
        if max_green_seconds < min_green_seconds:
            raise ValueError(
                f"max_green_seconds ({max_green_seconds}) cannot be less than min_green_seconds ({min_green_seconds})."
            )
        if cycle_length_seconds <= 0.0:
            raise ValueError(f"cycle_length_seconds ({cycle_length_seconds}) must be strictly positive (> 0).")
        if yellow_seconds < 0.0:
            raise ValueError(f"yellow_seconds ({yellow_seconds}) must be non-negative (>= 0).")

        min_required_cycle = 2.0 * min_green_seconds + 2.0 * yellow_seconds
        if cycle_length_seconds < min_required_cycle:
            raise ValueError(
                f"cycle_length_seconds ({cycle_length_seconds}s) is too short for dual-corridor minimum green "
                f"(2 * {min_green_seconds}s) plus yellow clearance (2 * {yellow_seconds}s) = {min_required_cycle}s."
            )

        self.w_q = float(weight_queue)
        self.w_w = float(weight_waiting)
        self.w_d = float(weight_density)
        self.ref_wait = float(reference_wait_seconds)
        self.min_green = float(min_green_seconds)
        self.max_green = float(max_green_seconds)
        self.cycle_length = float(cycle_length_seconds)
        self.yellow = float(yellow_seconds)

    @property
    def available_green_budget(self) -> float:
        """Total green duration available for allocation in one complete cycle."""
        return max(2.0 * self.min_green, self.cycle_length - 2.0 * self.yellow)

    def evaluate_corridor_demand(self, state: TrafficState) -> Tuple[CorridorDemandMetrics, CorridorDemandMetrics]:
        """Compute multi-metric demand breakdown and internally consistent green splits.

        Returns:
            Tuple[CorridorDemandMetrics, CorridorDemandMetrics]: (ns_metrics, ew_metrics)
        """
        # North-South corridor measurements
        ns_q = (state.north.queue_length if state.north else 0) + (state.south.queue_length if state.south else 0)
        ns_wait = (state.north.waiting_time if state.north else 0.0) + (state.south.waiting_time if state.south else 0.0)
        ns_count = (state.north.vehicle_count if state.north else 0) + (state.south.vehicle_count if state.south else 0)
        ns_spd = ((state.north.mean_speed if state.north else 0.0) + (state.south.mean_speed if state.south else 0.0)) / 2.0

        # East-West corridor measurements
        ew_q = (state.east.queue_length if state.east else 0) + (state.west.queue_length if state.west else 0)
        ew_wait = (state.east.waiting_time if state.east else 0.0) + (state.west.waiting_time if state.west else 0.0)
        ew_count = (state.east.vehicle_count if state.east else 0) + (state.west.vehicle_count if state.west else 0)
        ew_spd = ((state.east.mean_speed if state.east else 0.0) + (state.west.mean_speed if state.west else 0.0)) / 2.0

        # Composite pressure formulation:
        # P = w_q * Queue + w_w * (Wait / RefWait) + w_d * VehicleCount
        ns_pressure = round(
            self.w_q * ns_q + self.w_w * (ns_wait / self.ref_wait) + self.w_d * ns_count,
            2
        )
        ew_pressure = round(
            self.w_q * ew_q + self.w_w * (ew_wait / self.ref_wait) + self.w_d * ew_count,
            2
        )

        total_pressure = ns_pressure + ew_pressure + 1e-4

        # Documented Cycle Split Constraint:
        # G_budget = CycleLength - 2 * Yellow
        # Green time is distributed proportionally to demand, strictly preserving:
        # 1. G_ns + G_ew <= G_budget (consistent cycle split)
        # 2. G_ns >= min_green, G_ew >= min_green
        # 3. G_ns <= max_green, G_ew <= max_green
        budget = self.available_green_budget
        ns_target = budget * (ns_pressure / total_pressure)

        # Clamp NS green between min_green and (budget - min_green), while respecting max_green
        ns_clamped = max(self.min_green, min(self.max_green, min(budget - self.min_green, ns_target)))
        ew_clamped = max(self.min_green, min(self.max_green, budget - ns_clamped))

        ns_target_green = round(ns_clamped, 1)
        ew_target_green = round(ew_clamped, 1)

        ns_metrics = CorridorDemandMetrics(
            corridor="NORTH_SOUTH",
            queue_length=ns_q,
            waiting_time_seconds=round(ns_wait, 1),
            vehicle_count=ns_count,
            mean_speed_mps=round(ns_spd, 2),
            composite_pressure=ns_pressure,
            recommended_green_seconds=ns_target_green,
        )

        ew_metrics = CorridorDemandMetrics(
            corridor="EAST_WEST",
            queue_length=ew_q,
            waiting_time_seconds=round(ew_wait, 1),
            vehicle_count=ew_count,
            mean_speed_mps=round(ew_spd, 2),
            composite_pressure=ew_pressure,
            recommended_green_seconds=ew_target_green,
        )

        return ns_metrics, ew_metrics

    def should_switch_phase(
        self,
        current_phase: int,
        elapsed_green: float,
        ns_metrics: CorridorDemandMetrics,
        ew_metrics: CorridorDemandMetrics,
        pressure_difference_threshold: float = 3.0,
    ) -> Tuple[bool, str]:
        """Determine whether active green phase should transition based on multi-metric optimization.

        Returns:
            Tuple[bool, str]: (should_switch, explanation_reason)
        """
        # If minimum green has not elapsed, never switch
        if elapsed_green < self.min_green:
            time_left = round(self.min_green - elapsed_green, 1)
            return False, f"Minimum green interval active ({time_left}s remaining)."

        is_ns = (current_phase == 0)  # NS_GREEN

        active_metrics = ns_metrics if is_ns else ew_metrics
        conflicting_metrics = ew_metrics if is_ns else ns_metrics

        active_name = "North-South" if is_ns else "East-West"
        conflicting_name = "East-West" if is_ns else "North-South"

        # 1. Ceiling check: Max green elapsed
        if elapsed_green >= self.max_green:
            return True, f"Maximum green ceiling reached ({self.max_green}s); transferring green to {conflicting_name}."

        # 2. Gap-out condition: Active corridor has cleared (queue=0, low vehicles) and conflicting has queues
        if active_metrics.queue_length == 0 and conflicting_metrics.queue_length >= 2 and elapsed_green >= self.min_green:
            return True, (
                f"Gap-out actuated: {active_name} queue cleared while {conflicting_name} has {conflicting_metrics.queue_length} queued vehicles; "
                f"early termination of green after {round(elapsed_green, 1)}s."
            )

        # 3. Dynamic recommended green split reached AND conflicting corridor has demand
        if elapsed_green >= active_metrics.recommended_green_seconds and conflicting_metrics.composite_pressure > 0.5:
            return True, (
                f"Multi-metric target green ({active_metrics.recommended_green_seconds}s) reached; "
                f"switching to {conflicting_name} corridor (pressure: {conflicting_metrics.composite_pressure})."
            )

        # 4. Dominant pressure difference condition
        pressure_diff = conflicting_metrics.composite_pressure - active_metrics.composite_pressure
        if pressure_diff >= pressure_difference_threshold:
            return True, (
                f"Multi-metric pressure differential: {conflicting_name} pressure ({conflicting_metrics.composite_pressure}) "
                f"exceeds {active_name} ({active_metrics.composite_pressure}) by {round(pressure_diff, 1)} (threshold: {pressure_difference_threshold})."
            )

        # Continue holding active green
        return False, (
            f"Extending {active_name} green corridor: multi-metric pressure ({active_metrics.composite_pressure}) "
            f"favors active phase ({round(elapsed_green, 1)}s elapsed)."
        )
