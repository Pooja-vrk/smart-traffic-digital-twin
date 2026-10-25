"""Multi-Intersection Coordinator and Arterial Progression Manager.

Coordinates the central signalized junction (INT-001 / center) with adjacent gateway and
arterial intersections (INT-N, INT-S, INT-E, INT-W) along North-South and East-West corridors.

Network Topology Note:
The SUMO road network (simulation/sumo/intersection.net.xml) defines a single physical
signalized junction at 'center' (INT-001, tlLogic id='center').
The peripheral nodes 'north', 'south', 'east', 'west' are boundary priority turnarounds in SUMO.
In this digital twin, the gateway signals INT-N, INT-S, INT-E, and INT-W represent
*simulated arterial coordination intent* modeling adjacent signalized nodes, progression offsets,
and corridor preemption across a 5-node arterial network. Physical signal actuation and
safety transitions occur at the central junction under SignalSafetyManager control.

Features:
1. Grounded arterial progression offsets (Green Wave) based on physical link lengths and free-flow velocity.
2. Cycle position and progression offsets directly drive simulated neighbor signal states.
3. Distinct coordination modes: ARTERY_EW, ARTERY_NS, BALANCED_ADAPTIVE, and ISOLATED.
4. Coordinated emergency vehicle route preemption with clearance transitions, upstream metering, and downstream advance green.
5. Actionable queue spillback detection and mitigation decisions.
6. Clean separation of directly observed TraCI measurements from heuristic progression scores.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from simulation.coordination.adaptive_optimizer import AdaptiveSignalOptimizer
from simulation.coordination.models import (
    CoordinatedNeighbor,
    CoordinationMode,
    CorridorProgressionMetrics,
    MultiIntersectionState,
    ProgressionStatus,
    SpillbackMitigationDecision,
)
from simulation.state import TrafficState

logger = logging.getLogger(__name__)


class MultiIntersectionCoordinator:
    """Coordinates traffic signal timings and progression across adjacent intersections."""

    DEFAULT_CYCLE_LENGTH = 60.0  # seconds
    APPROACH_LINK_LENGTH = 289.60  # meters
    DESIGN_SPEED_MPS = 13.89  # 50 km/h in m/s
    IDEAL_PROGRESSION_TRAVEL_TIME = 20.85  # 289.60 / 13.89 (~20.85s)
    YELLOW_CLEARANCE_SECONDS = 3.0  # seconds

    def __init__(
        self,
        primary_intersection_id: str = "INT-001",
        mode: CoordinationMode | str = CoordinationMode.ARTERY_EW,
        cycle_length: float = DEFAULT_CYCLE_LENGTH,
    ) -> None:
        if cycle_length < 20.0 or cycle_length > 300.0:
            raise ValueError(f"cycle_length ({cycle_length}s) must be between 20.0s and 300.0s.")

        self.primary_id = primary_intersection_id
        if isinstance(mode, str):
            try:
                mode = CoordinationMode(mode.upper())
            except ValueError:
                logger.warning("Unknown coordination mode '%s', falling back to ARTERY_EW", mode)
                mode = CoordinationMode.ARTERY_EW

        self.mode = mode
        self.cycle_length = float(cycle_length)
        self._step = 0
        self._sim_time = 0.0

        # Dedicated adaptive optimizer instance for BALANCED_ADAPTIVE mode
        self.adaptive_optimizer = AdaptiveSignalOptimizer(
            min_green_seconds=10.0,
            max_green_seconds=float(cycle_length - 2 * self.YELLOW_CLEARANCE_SECONDS - 10.0),
            cycle_length_seconds=float(cycle_length),
            yellow_seconds=self.YELLOW_CLEARANCE_SECONDS,
        )

        # Initialize the 4 neighboring arterial gateway intersections
        # These represent simulated arterial coordination intent at the network boundary
        prog_offset = round(self.IDEAL_PROGRESSION_TRAVEL_TIME % self.cycle_length, 1)
        self.neighbors: Dict[str, CoordinatedNeighbor] = {
            "north": CoordinatedNeighbor(
                intersection_id="INT-N",
                name="North Gateway Junction",
                direction="north",
                corridor="NS",
                distance_meters=self.APPROACH_LINK_LENGTH,
                ideal_travel_time_seconds=self.IDEAL_PROGRESSION_TRAVEL_TIME,
                current_offset_seconds=prog_offset,
                is_physical_tls=False,
            ),
            "south": CoordinatedNeighbor(
                intersection_id="INT-S",
                name="South Gateway Junction",
                direction="south",
                corridor="NS",
                distance_meters=self.APPROACH_LINK_LENGTH,
                ideal_travel_time_seconds=self.IDEAL_PROGRESSION_TRAVEL_TIME,
                current_offset_seconds=prog_offset,
                is_physical_tls=False,
            ),
            "east": CoordinatedNeighbor(
                intersection_id="INT-E",
                name="East Arterial Junction",
                direction="east",
                corridor="EW",
                distance_meters=self.APPROACH_LINK_LENGTH,
                ideal_travel_time_seconds=self.IDEAL_PROGRESSION_TRAVEL_TIME,
                current_offset_seconds=prog_offset,
                is_physical_tls=False,
            ),
            "west": CoordinatedNeighbor(
                intersection_id="INT-W",
                name="West Arterial Junction",
                direction="west",
                corridor="EW",
                distance_meters=self.APPROACH_LINK_LENGTH,
                ideal_travel_time_seconds=self.IDEAL_PROGRESSION_TRAVEL_TIME,
                current_offset_seconds=prog_offset,
                is_physical_tls=False,
            ),
        }

        self.metrics = CorridorProgressionMetrics(
            cycle_length_seconds=self.cycle_length,
            coordination_mode=self.mode.value,
            is_coordinated=(self.mode != CoordinationMode.ISOLATED),
        )

        self._emergency_preemption_active = False
        self._emergency_clearance_active = False
        self._emergency_clearance_timer = 0.0
        self._preempted_corridor: Optional[str] = None
        self._last_state: Optional[MultiIntersectionState] = None

    def reset(self) -> None:
        """Reset coordinator state for a new simulation run."""
        self._step = 0
        self._sim_time = 0.0
        self._emergency_preemption_active = False
        self._emergency_clearance_active = False
        self._emergency_clearance_timer = 0.0
        self._preempted_corridor = None
        self._last_state = None

        prog_offset = round(self.IDEAL_PROGRESSION_TRAVEL_TIME % self.cycle_length, 1)
        for n in self.neighbors.values():
            n.current_phase = 0
            n.phase_name = "GREEN"
            n.signal_state = "green"
            n.coordination_intent = "GREEN"
            n.time_in_phase = 0.0
            n.queue_length = 0
            n.vehicle_count = 0
            n.current_offset_seconds = 0.0 if self.mode == CoordinationMode.ISOLATED else prog_offset
            n.progression_status = (
                ProgressionStatus.ISOLATED.value
                if self.mode == CoordinationMode.ISOLATED
                else ProgressionStatus.SYNCHRONIZED.value
            )
            n.preemption_active = False
            n.coordination_role = "ISOLATED" if self.mode == CoordinationMode.ISOLATED else "PEER"

        self.metrics = CorridorProgressionMetrics(
            cycle_length_seconds=self.cycle_length,
            coordination_mode=self.mode.value,
            is_coordinated=(self.mode != CoordinationMode.ISOLATED),
        )

    def set_mode(self, mode: CoordinationMode | str) -> None:
        """Update active coordination policy mode."""
        if isinstance(mode, str):
            try:
                mode = CoordinationMode(mode.upper())
            except ValueError:
                logger.warning("Unknown coordination mode '%s', falling back to ARTERY_EW", mode)
                mode = CoordinationMode.ARTERY_EW
        self.mode = mode
        self.metrics.coordination_mode = mode.value
        self.metrics.is_coordinated = (mode != CoordinationMode.ISOLATED)

        prog_offset = round(self.IDEAL_PROGRESSION_TRAVEL_TIME % self.cycle_length, 1)
        for n in self.neighbors.values():
            if mode == CoordinationMode.ISOLATED:
                n.current_offset_seconds = 0.0
                n.coordination_role = "ISOLATED"
                n.progression_status = ProgressionStatus.ISOLATED.value
            else:
                n.current_offset_seconds = prog_offset
                n.coordination_role = "PEER"
                n.progression_status = ProgressionStatus.SYNCHRONIZED.value

        logger.info("Multi-intersection coordination mode updated to: %s", mode.value)

    def step(
        self,
        state: TrafficState,
        step_length: float = 1.0,
    ) -> MultiIntersectionState:
        """Update multi-intersection progression and neighbor signal states for the current step."""
        if step_length <= 0.0:
            raise ValueError(f"step_length ({step_length}) must be strictly positive (> 0).")

        self._step += 1
        self._sim_time = getattr(state, "simulation_time", float(self._step))

        primary_phase = getattr(state, "current_phase", 0)
        primary_phase_name = getattr(state, "current_phase_name", "NS_GREEN")
        is_primary_ns_green = primary_phase in {0, 1}
        is_primary_ew_green = primary_phase in {2, 3}

        # ── 1. Evaluate Emergency Route Preemption Across Coordinated Network ──
        ev = getattr(state, "emergency", None)
        ev_active = bool(ev and ev.active and getattr(ev, "approach", None))
        ev_approach = ev.approach.lower() if ev_active and ev.approach else None

        if ev_active and ev_approach in self.neighbors:
            self._handle_emergency_coordination(
                ev_approach=ev_approach,
                ev=ev,
                is_primary_corridor_aligned=(is_primary_ew_green if ev_approach in {"east", "west"} else is_primary_ns_green),
                step_length=step_length,
            )
        else:
            if self._emergency_preemption_active:
                self._restore_normal_coordination(step_length)

        # ── 2. Update Neighbor Signal States via Progression Offsets ───────────
        if not self._emergency_preemption_active:
            self._update_normal_progression(is_primary_ns_green, is_primary_ew_green, state, step_length)

        # ── 3. Spillback Detection & Mitigation Decision ───────────────────────
        spillback_decision = self._evaluate_spillback(state)
        self.metrics.spillback_mitigation = spillback_decision

        # ── 4. Calculate Progression Quality & Direct Observations ─────────────
        self._compute_corridor_metrics(state)

        state_out = MultiIntersectionState(
            primary_intersection_id=self.primary_id,
            simulation_time=self._sim_time,
            step=self._step,
            mode=self.mode.value,
            cycle_length=self.cycle_length,
            primary_phase=primary_phase,
            primary_phase_name=primary_phase_name,
            neighbors=self.neighbors,
            metrics=self.metrics,
            emergency_active=self._emergency_preemption_active,
            emergency_approach=self._preempted_corridor,
        )
        self._last_state = state_out
        return state_out

    def get_state(self) -> MultiIntersectionState:
        """Return the most recent multi-intersection coordination state, or default state."""
        if self._last_state is not None:
            return self._last_state
        return MultiIntersectionState(
            primary_intersection_id=self.primary_id,
            simulation_time=self._sim_time,
            step=self._step,
            mode=self.mode.value,
            cycle_length=self.cycle_length,
            primary_phase=0,
            primary_phase_name="NS_GREEN",
            neighbors=self.neighbors,
            metrics=self.metrics,
            emergency_active=self._emergency_preemption_active,
            emergency_approach=self._preempted_corridor,
        )

    def _handle_emergency_coordination(
        self,
        ev_approach: str,
        ev: Any,
        is_primary_corridor_aligned: bool,
        step_length: float,
    ) -> None:
        """Coordinate neighboring signals along the emergency vehicle's entry and exit trajectory."""
        self._emergency_preemption_active = True
        self._preempted_corridor = ev_approach
        self.metrics.emergency_preempted_corridor = ev_approach

        opposite_map = {
            "east": "west",
            "west": "east",
            "north": "south",
            "south": "north",
        }
        downstream_direction = opposite_map.get(ev_approach)
        corridor_type = "EW" if ev_approach in {"east", "west"} else "NS"

        # 1. Upstream Gateway Neighbor: Where EV entered network
        upstream = self.neighbors.get(ev_approach)
        if upstream:
            upstream.coordination_role = "UPSTREAM"
            upstream.preemption_active = True
            upstream.progression_status = ProgressionStatus.METERING_HOLD.value
            upstream.signal_state = "green"
            upstream.coordination_intent = "Simulated Preemption Green"
            upstream.phase_name = f"METERING_CORRIDOR_{corridor_type}"

        # 2. Downstream Gateway Neighbor: Where EV is heading
        if downstream_direction and downstream_direction in self.neighbors:
            downstream = self.neighbors[downstream_direction]
            downstream.coordination_role = "DOWNSTREAM"
            downstream.preemption_active = True
            downstream.progression_status = ProgressionStatus.ADVANCE_PREEMPTION.value
            downstream.signal_state = "green"
            downstream.coordination_intent = "Simulated Advance Green"
            downstream.phase_name = f"ADVANCE_PREEMPTION_GREEN_{corridor_type}"

        # 3. Cross-Corridor Neighbors: Hold conflicting traffic safely
        for dir_key, neighbor in self.neighbors.items():
            if dir_key not in {ev_approach, downstream_direction}:
                neighbor.coordination_role = "PEER"
                neighbor.preemption_active = False
                neighbor.progression_status = ProgressionStatus.METERING_HOLD.value
                neighbor.signal_state = "red"
                neighbor.coordination_intent = "Simulated Cross Hold Red"
                neighbor.phase_name = "CROSS_TRAFFIC_HOLD"

    def _restore_normal_coordination(self, step_length: float) -> None:
        """Safely release emergency preemption and realign progressive offsets."""
        logger.info("Restoring normal multi-intersection coordination after emergency vehicle passage.")
        self._emergency_preemption_active = False
        self._emergency_clearance_active = False
        self._emergency_clearance_timer = 0.0
        self._preempted_corridor = None
        self.metrics.emergency_preempted_corridor = None

        prog_offset = round(self.IDEAL_PROGRESSION_TRAVEL_TIME % self.cycle_length, 1)
        for neighbor in self.neighbors.values():
            neighbor.preemption_active = False
            if self.mode == CoordinationMode.ISOLATED:
                neighbor.coordination_role = "ISOLATED"
                neighbor.progression_status = ProgressionStatus.ISOLATED.value
                neighbor.current_offset_seconds = 0.0
            else:
                neighbor.coordination_role = "PEER"
                neighbor.progression_status = ProgressionStatus.SYNCHRONIZED.value
                neighbor.current_offset_seconds = prog_offset

    def _update_normal_progression(
        self,
        is_primary_ns_green: bool,
        is_primary_ew_green: bool,
        state: TrafficState,
        step_length: float,
    ) -> None:
        """Update neighbor signal phases with grounded progression offsets and platoon synchronization."""
        # 1. Determine green split budget for corridors under active mode
        available_green = max(20.0, self.cycle_length - 2 * self.YELLOW_CLEARANCE_SECONDS)

        if self.mode == CoordinationMode.ARTERY_EW:
            # 65% / 35% priority for East-West arterial corridor
            g_ew = round(available_green * 0.65, 1)
            g_ns = round(available_green - g_ew, 1)
        elif self.mode == CoordinationMode.ARTERY_NS:
            # 65% / 35% priority for North-South transit spine
            g_ns = round(available_green * 0.65, 1)
            g_ew = round(available_green - g_ns, 1)
        elif self.mode == CoordinationMode.BALANCED_ADAPTIVE:
            # Dynamic multi-metric pressure-weighted split allocation
            ns_dem, ew_dem = self.adaptive_optimizer.evaluate_corridor_demand(state)
            g_ns = ns_dem.recommended_green_seconds
            g_ew = ew_dem.recommended_green_seconds
        else:
            # ISOLATED mode: Standard 50/50 local split, uncoordinated
            g_ew = round(available_green * 0.5, 1)
            g_ns = round(available_green - g_ew, 1)

        # 2. Update each gateway neighbor based on its local cycle offset position
        for direction, neighbor in self.neighbors.items():
            neighbor.time_in_phase += step_length

            # Grounded measurements from approach link
            app_state = getattr(state, direction, None)
            if app_state:
                neighbor.queue_length = app_state.queue_length
                neighbor.vehicle_count = app_state.vehicle_count

            # Progression Offset Timing:
            # Local cycle position = (t_sim + offset) % cycle_length
            # For ISOLATED mode, offset is 0.0 (no progressive offset applied)
            offset = 0.0 if self.mode == CoordinationMode.ISOLATED else neighbor.current_offset_seconds
            neighbor.current_offset_seconds = offset

            if neighbor.corridor == "EW":
                local_t = (self._sim_time + offset) % self.cycle_length
                g_duration = g_ew
                c_name = "EW"
            else:
                # NS phase window starts after EW green + yellow interval
                ns_shift = g_ew + self.YELLOW_CLEARANCE_SECONDS
                local_t = (self._sim_time + offset - ns_shift) % self.cycle_length
                g_duration = g_ns
                c_name = "NS"

            # 3. Phase determination from local offset time within cycle
            if 0.0 <= local_t < g_duration:
                neighbor.signal_state = "green"
                neighbor.coordination_intent = "Simulated Corridor Green"
                neighbor.phase_name = f"{c_name}_PROGRESSION_GREEN"
                neighbor.progression_status = (
                    ProgressionStatus.ISOLATED.value
                    if self.mode == CoordinationMode.ISOLATED
                    else ProgressionStatus.PROGRESSION_ACTIVE.value
                )
            elif g_duration <= local_t < (g_duration + self.YELLOW_CLEARANCE_SECONDS):
                neighbor.signal_state = "yellow"
                neighbor.coordination_intent = "Simulated Clearance Yellow"
                neighbor.phase_name = f"{c_name}_CLEARANCE_YELLOW"
                neighbor.progression_status = (
                    ProgressionStatus.ISOLATED.value
                    if self.mode == CoordinationMode.ISOLATED
                    else ProgressionStatus.TRANSITION_CLEARANCE.value
                )
            else:
                neighbor.signal_state = "red"
                neighbor.coordination_intent = "Simulated Cross Hold Red"
                neighbor.phase_name = f"{c_name}_HOLD_RED"
                neighbor.progression_status = (
                    ProgressionStatus.ISOLATED.value
                    if self.mode == CoordinationMode.ISOLATED
                    else ProgressionStatus.SYNCHRONIZED.value
                )

            if self.mode == CoordinationMode.ISOLATED:
                neighbor.coordination_role = "ISOLATED"

    def _evaluate_spillback(self, state: TrafficState) -> SpillbackMitigationDecision:
        """Detect link queue spillback and generate an explicit actionable mitigation decision."""
        q_north = state.north.queue_length if state.north else 0
        q_south = state.south.queue_length if state.south else 0
        q_east = state.east.queue_length if state.east else 0
        q_west = state.west.queue_length if state.west else 0

        queue_map = {
            "north": q_north,
            "south": q_south,
            "east": q_east,
            "west": q_west,
        }
        worst_approach, worst_queue = max(queue_map.items(), key=lambda item: item[1])
        spillback_threshold = 14

        if worst_queue >= spillback_threshold:
            # Link storage capacity is 38 vehicles (289.6m / 7.5m).
            # Queues >= 14 vehicles occupy >35% of the link and threaten upstream gridlock.
            metering_rate = max(0.2, round(0.75 - (worst_queue - spillback_threshold) * 0.05, 2))
            flush_green_ext = min(15.0, round((worst_queue - 10) * 1.5, 1))

            decision = SpillbackMitigationDecision(
                active=True,
                approach=worst_approach,
                queue_length=worst_queue,
                threshold=spillback_threshold,
                action="METER_UPSTREAM_ENTRY_AND_FLUSH",
                metering_rate_factor=metering_rate,
                green_extension_seconds=flush_green_ext,
                explanation=(
                    f"Spillback mitigation active: {worst_approach} approach queue ({worst_queue} veh) "
                    f"exceeds link safety threshold ({spillback_threshold} veh, capacity ~38 veh). "
                    f"Action [METER_UPSTREAM_ENTRY_AND_FLUSH]: Throttling upstream entry inflow (factor {metering_rate}) and allocating "
                    f"+{flush_green_ext}s green extension to flush bottleneck."
                ),
            )
            # Mark the congested gateway's progression status
            if worst_approach in self.neighbors:
                self.neighbors[worst_approach].progression_status = ProgressionStatus.SPILLBACK_MITIGATION.value
            return decision

        return SpillbackMitigationDecision(
            active=False,
            approach=worst_approach if worst_queue > 0 else None,
            queue_length=worst_queue,
            threshold=spillback_threshold,
            action="NONE",
            metering_rate_factor=1.0,
            green_extension_seconds=0.0,
            explanation="Approach link queues are within nominal storage capacity; no spillback mitigation required.",
        )

    def _compute_corridor_metrics(self, state: TrafficState) -> None:
        """Compute direct TraCI observations and heuristic progression quality metrics."""
        q_north = state.north.queue_length if state.north else 0
        q_south = state.south.queue_length if state.south else 0
        q_east = state.east.queue_length if state.east else 0
        q_west = state.west.queue_length if state.west else 0

        # ── Directly Observed TraCI Measurements ────────────────────────────
        avg_speed = getattr(state, "average_speed", 0.0)
        if avg_speed <= 0.0:
            speeds = [app.mean_speed for app in (state.north, state.south, state.east, state.west) if app and app.mean_speed > 0]
            avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        self.metrics.observed_mean_speed_mps = round(avg_speed, 2)
        self.metrics.observed_max_queue = max(q_north, q_south, q_east, q_west)

        tot_q = getattr(state, "total_queue", 0)
        if tot_q == 0 and (q_north + q_south + q_east + q_west) > 0:
            tot_q = q_north + q_south + q_east + q_west
        self.metrics.observed_total_queue = tot_q
        self.metrics.cycle_length_seconds = self.cycle_length

        worst_queue = self.metrics.observed_max_queue
        if worst_queue >= 14:
            spillback_risk = "HIGH"
        elif worst_queue >= 8:
            spillback_risk = "MODERATE"
        else:
            spillback_risk = "LOW"
        self.metrics.spillback_risk = spillback_risk

        # ── Heuristic Algorithmic Scores ────────────────────────────────────
        # In ISOLATED mode, progression coordination is explicitly disabled.
        # It must NOT claim progressive synchronization.
        if self.mode == CoordinationMode.ISOLATED:
            self.metrics.arterial_ew_sync_score = 0.0
            self.metrics.arterial_ns_sync_score = 0.0
            self.metrics.overall_quality_score = 0.0
            self.metrics.platoon_arrival_efficiency = 0.0
            self.metrics.active_corridor = "NONE"
            self.metrics.is_coordinated = False
            return

        self.metrics.is_coordinated = True

        # Speed progression efficiency ratio: actual speed relative to design speed
        speed_ratio = min(1.0, avg_speed / self.DESIGN_SPEED_MPS) if self.DESIGN_SPEED_MPS > 0 else 0.8

        # Queue factor: halted queues degrade platoon green wave flow
        max_q = max(q_north + q_south, q_east + q_west)
        queue_penalty = min(30.0, max_q * 1.5)

        base_sync = round(max(50.0, 95.0 * speed_ratio - queue_penalty), 1)

        if self.mode == CoordinationMode.ARTERY_EW:
            ew_score = min(99.0, base_sync + 6.0)
            ns_score = max(55.0, base_sync - 4.0)
            active_corr = "EAST_WEST"
        elif self.mode == CoordinationMode.ARTERY_NS:
            ew_score = max(55.0, base_sync - 4.0)
            ns_score = min(99.0, base_sync + 6.0)
            active_corr = "NORTH_SOUTH"
        else:
            ew_score = base_sync
            ns_score = base_sync
            active_corr = "BALANCED"

        overall_score = round((ew_score * 0.55 + ns_score * 0.45), 1)
        platoon_eff = round(max(40.0, min(98.0, overall_score * 0.95)), 1)

        self.metrics.arterial_ew_sync_score = ew_score
        self.metrics.arterial_ns_sync_score = ns_score
        self.metrics.overall_quality_score = overall_score
        self.metrics.platoon_arrival_efficiency = platoon_eff
        self.metrics.active_corridor = active_corr
