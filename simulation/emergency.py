"""Emergency vehicle green corridor tracking, lifecycle management, and empirical evaluation.

Provides:
1. Grounded TraCI emergency vehicle kinematic tracking (stopline distance, ETA, approach).
2. Explicit 7-stage lifecycle state machine:
   IDLE -> DETECTED -> PRIORITY_REQUESTED -> PRIORITY_ACTIVE -> VEHICLE_PASSED -> RESTORING_NORMAL -> IDLE.
3. Graceful disappearance / teleportation recovery without deadlocks.
4. Empirical metric computation: travel time, intersection delay, time to priority,
   stopped waiting time, and priority duration.
"""

from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from simulation.state import EmergencyVehicleState

logger = logging.getLogger(__name__)

# Constants grounded in SUMO network geometry (simulation/sumo/intersection.net.xml)
APPROACH_INFLOW_EDGES = {
    "N2C": "north",
    "S2C": "south",
    "E2C": "east",
    "W2C": "west",
}

APPROACH_OUTFLOW_EDGES = {
    "C2S": "north",  # Traversed straight through from North
    "C2N": "south",  # Traversed straight through from South
    "C2W": "east",   # Traversed straight through from East
    "C2E": "west",   # Traversed straight through from West
}

INFLOW_EDGE_LENGTH_METERS = 289.60
INTERSECTION_CENTER_X = 300.0
INTERSECTION_CENTER_Y = 300.0
FREE_FLOW_SPEED_MPS = 22.22  # maxSpeed from scenario vType emergency_vehicle (80 km/h)
FREE_FLOW_TIME_SECONDS = round(INFLOW_EDGE_LENGTH_METERS / FREE_FLOW_SPEED_MPS, 2)  # ~13.03s


class EmergencyLifecycleState(str, enum.Enum):
    """Explicit 7-stage emergency vehicle corridor lifecycle."""
    IDLE = "IDLE"
    DETECTED = "DETECTED"
    PRIORITY_REQUESTED = "PRIORITY_REQUESTED"
    PRIORITY_ACTIVE = "PRIORITY_ACTIVE"
    VEHICLE_PASSED = "VEHICLE_PASSED"
    RESTORING_NORMAL = "RESTORING_NORMAL"


@dataclass
class EmergencyCorridorMetrics:
    """Empirical performance metrics for emergency vehicle traversal."""
    vehicle_id: str
    approach: str
    entry_time: float
    exit_time: float
    travel_time: float
    free_flow_time: float
    intersection_delay: float
    stopped_waiting_time: float
    time_to_priority_active: float
    priority_duration: float
    preemption_requested_step: Optional[int] = None
    priority_activated_step: Optional[int] = None
    passed_step: Optional[int] = None
    completed: bool = True
    disappeared_prematurely: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to serializable dictionary."""
        return {
            "vehicle_id": self.vehicle_id,
            "approach": self.approach,
            "entry_time": round(self.entry_time, 1),
            "exit_time": round(self.exit_time, 1),
            "travel_time": round(self.travel_time, 2),
            "free_flow_time": round(self.free_flow_time, 2),
            "intersection_delay": round(self.intersection_delay, 2),
            "stopped_waiting_time": round(self.stopped_waiting_time, 2),
            "time_to_priority_active": round(self.time_to_priority_active, 2),
            "priority_duration": round(self.priority_duration, 1),
            "completed": self.completed,
            "disappeared_prematurely": self.disappeared_prematurely,
        }


class EmergencyCorridorTracker:
    """Tracks emergency vehicle kinematic state, governs lifecycle transitions, and computes metrics."""

    def __init__(self) -> None:
        self.lifecycle_state = EmergencyLifecycleState.IDLE
        self.active_vehicle_id: Optional[str] = None
        self.vehicle_type: Optional[str] = None
        self.approach: Optional[str] = None
        self.entry_time: Optional[float] = None
        self.request_time: Optional[float] = None
        self.priority_active_time: Optional[float] = None
        self.passed_time: Optional[float] = None
        self.exit_time: Optional[float] = None
        self.priority_duration: float = 0.0
        self.last_waiting_time: float = 0.0

        self.last_known_distance: Optional[float] = None
        self.last_known_stopline_dist: Optional[float] = None
        self.last_known_speed: Optional[float] = None
        self.last_known_eta: Optional[float] = None
        self.disappeared_prematurely: bool = False
        self._metrics_recorded: bool = False
        self._restoring_steps: int = 0

        self._history_metrics: List[EmergencyCorridorMetrics] = []

    def reset(self) -> None:
        """Reset internal tracker state."""
        self.lifecycle_state = EmergencyLifecycleState.IDLE
        self.active_vehicle_id = None
        self.vehicle_type = None
        self.approach = None
        self.entry_time = None
        self.request_time = None
        self.priority_active_time = None
        self.passed_time = None
        self.exit_time = None
        self.priority_duration = 0.0
        self.last_waiting_time = 0.0
        self.last_known_distance = None
        self.last_known_stopline_dist = None
        self.last_known_speed = None
        self.last_known_eta = None
        self.disappeared_prematurely = False
        self._metrics_recorded = False
        self._restoring_steps = 0
        self._history_metrics.clear()

    def update_from_traci(
        self,
        traci_module: Any,
        sim_time: float,
        step_length: float = 1.0,
    ) -> EmergencyVehicleState:
        """Inspect TraCI vehicle state and return updated EmergencyVehicleState."""
        try:
            active_ids = traci_module.vehicle.getIDList()
        except Exception as exc:
            logger.warning("TraCI getIDList failed in EmergencyCorridorTracker: %s", exc)
            active_ids = []

        ev_id: Optional[str] = None
        ev_vtype: Optional[str] = None

        # Locate emergency vehicle in network
        for vid in active_ids:
            try:
                vtype = str(traci_module.vehicle.getTypeID(vid))
                try:
                    vclass = str(traci_module.vehicle.getVehicleClass(vid))
                except Exception:
                    vclass = ""
                if (
                    vclass == "emergency"
                    or "emergency" in vtype.lower()
                    or "ambulance" in vtype.lower()
                    or "fire" in vtype.lower()
                    or str(vid).startswith("EV_")
                    or str(vid) == "EV_01"
                ):
                    ev_id = str(vid)
                    ev_vtype = vtype
                    break
            except Exception:
                continue

        # ── Case A: Emergency vehicle actively detected in SUMO ────────────────
        if ev_id is not None:
            try:
                pos = traci_module.vehicle.getPosition(ev_id)
                ang = float(traci_module.vehicle.getAngle(ev_id))
                spd = float(traci_module.vehicle.getSpeed(ev_id))
                wait = float(traci_module.vehicle.getWaitingTime(ev_id))
                lane = str(traci_module.vehicle.getLaneID(ev_id))
                edge = str(traci_module.vehicle.getRoadID(ev_id))
                lane_pos = float(traci_module.vehicle.getLanePosition(ev_id))

                self.last_waiting_time = wait
                dist_to_center = math.hypot(float(pos[0]) - INTERSECTION_CENTER_X, float(pos[1]) - INTERSECTION_CENTER_Y)

                # Determine approach corridor and stop line distance
                approach: str
                dist_to_stopline: Optional[float] = None
                is_inside_junction = False
                is_passed = False

                if edge in APPROACH_INFLOW_EDGES:
                    approach = APPROACH_INFLOW_EDGES[edge]
                    dist_to_stopline = max(0.0, INFLOW_EDGE_LENGTH_METERS - lane_pos)
                elif edge.startswith(":") or edge == "center":
                    is_inside_junction = True
                    dist_to_stopline = None
                    # Heading heuristic if approach not yet registered
                    approach = self.approach or (
                        "north" if (135 <= ang <= 225) else ("south" if (ang <= 45 or ang >= 315) else ("east" if (225 < ang < 315) else "west"))
                    )
                elif edge in APPROACH_OUTFLOW_EDGES or edge.startswith("C2"):
                    is_passed = True
                    dist_to_stopline = None
                    approach = self.approach or APPROACH_OUTFLOW_EDGES.get(edge, "east")
                else:
                    dist_to_stopline = None
                    approach = self.approach or "east"

                self.approach = approach
                self.active_vehicle_id = ev_id
                self.vehicle_type = ev_vtype

                # Safe ETA calculation with low-speed handling
                if dist_to_stopline is not None and dist_to_stopline > 0.0:
                    if spd >= 1.0:
                        eta_seconds: Optional[float] = round(dist_to_stopline / spd, 1)
                    else:
                        eta_seconds = None  # Crawling or queued at red light
                else:
                    eta_seconds = None  # Inside junction, passed stopline, or unavailable

                self.last_known_distance = round(dist_to_center, 1)
                self.last_known_stopline_dist = round(dist_to_stopline, 1) if dist_to_stopline is not None else None
                self.last_known_speed = round(spd, 2)
                self.last_known_eta = eta_seconds

                # If the tracker has already completed this corridor traversal (IDLE), and the vehicle
                # is currently departing via junction or outflow edge, remain safely in IDLE with active=False.
                if self.lifecycle_state == EmergencyLifecycleState.IDLE and (is_passed or is_inside_junction):
                    travel_t = round(self.exit_time - self.entry_time, 2) if (self.exit_time is not None and self.entry_time is not None) else None
                    delay_t = max(0.0, round(travel_t - FREE_FLOW_TIME_SECONDS, 2)) if travel_t is not None else None
                    return EmergencyVehicleState(
                        active=False,
                        vehicle_id=ev_id,
                        vehicle_type=ev_vtype,
                        approach=approach,
                        state=EmergencyLifecycleState.IDLE.value,
                        lifecycle_state=EmergencyLifecycleState.IDLE.value,
                        speed=round(spd, 2),
                        distance=round(dist_to_center, 1),
                        distance_to_stopline=None,
                        eta_seconds=None,
                        lane_id=lane,
                        edge_id=edge,
                        priority_active=False,
                        priority_approved=False,
                        priority_requested=False,
                        current_action="NORMAL_CONTROL",
                        safety_status="NORMAL",
                        timestamp=sim_time,
                        entry_time=self.entry_time,
                        exit_time=self.exit_time,
                        travel_time=travel_t,
                        delay_seconds=delay_t,
                    )

                # ── Inflow Edge (Approaching) ──
                if not is_passed and not is_inside_junction:
                    if self.lifecycle_state in {EmergencyLifecycleState.IDLE, EmergencyLifecycleState.RESTORING_NORMAL}:
                        self.lifecycle_state = EmergencyLifecycleState.DETECTED
                        self.entry_time = sim_time
                        self.passed_time = None
                        self.exit_time = None
                        self.priority_duration = 0.0
                        self._metrics_recorded = False
                        self._restoring_steps = 0
                        logger.info("Emergency vehicle %s DETECTED on %s approach at t=%.1fs", ev_id, approach, sim_time)

                # ── Stopline Crossed (Inside Junction or Reached Outflow) ──
                elif is_inside_junction or is_passed:
                    if self.lifecycle_state in {
                        EmergencyLifecycleState.DETECTED,
                        EmergencyLifecycleState.PRIORITY_REQUESTED,
                        EmergencyLifecycleState.PRIORITY_ACTIVE,
                    }:
                        # Vehicle crosses stopline for the first time
                        self.lifecycle_state = EmergencyLifecycleState.VEHICLE_PASSED
                        self.passed_time = sim_time
                        self.exit_time = sim_time
                        self._record_final_metrics(completed=True)
                        self._restoring_steps = 0
                        logger.info("Emergency vehicle %s PASSED stopline at t=%.1fs", ev_id, sim_time)

                    elif self.lifecycle_state == EmergencyLifecycleState.VEHICLE_PASSED:
                        # Exactly one step in VEHICLE_PASSED, transition to RESTORING_NORMAL
                        self.lifecycle_state = EmergencyLifecycleState.RESTORING_NORMAL
                        self._restoring_steps = 1
                        logger.info("Emergency vehicle %s advancing to RESTORING_NORMAL at t=%.1fs", ev_id, sim_time)

                    elif self.lifecycle_state == EmergencyLifecycleState.RESTORING_NORMAL:
                        # Restoring step completed or vehicle reached outflow edge -> Transition to IDLE
                        self.lifecycle_state = EmergencyLifecycleState.IDLE
                        self.active_vehicle_id = None
                        self._restoring_steps = 0
                        logger.info("Emergency vehicle %s completed traversal; restoring to IDLE at t=%.1fs", ev_id, sim_time)
                        travel_t = round(self.exit_time - self.entry_time, 2) if (self.exit_time is not None and self.entry_time is not None) else None
                        delay_t = max(0.0, round(travel_t - FREE_FLOW_TIME_SECONDS, 2)) if travel_t is not None else None
                        return EmergencyVehicleState(
                            active=False,
                            vehicle_id=ev_id,
                            vehicle_type=ev_vtype,
                            approach=approach,
                            state=EmergencyLifecycleState.IDLE.value,
                            lifecycle_state=EmergencyLifecycleState.IDLE.value,
                            speed=round(spd, 2),
                            distance=round(dist_to_center, 1),
                            distance_to_stopline=None,
                            eta_seconds=None,
                            lane_id=lane,
                            edge_id=edge,
                            priority_active=False,
                            priority_approved=False,
                            priority_requested=False,
                            current_action="NORMAL_CONTROL",
                            safety_status="NORMAL",
                            timestamp=sim_time,
                            entry_time=self.entry_time,
                            exit_time=self.exit_time,
                            travel_time=travel_t,
                            delay_seconds=delay_t,
                        )

                # Travel time and delay calculations
                travel_time: Optional[float] = None
                delay_sec: Optional[float] = None
                if self.entry_time is not None:
                    end_t = self.exit_time if self.exit_time is not None else sim_time
                    travel_time = max(0.1, round(end_t - self.entry_time, 2))
                    delay_sec = max(0.0, round(travel_time - FREE_FLOW_TIME_SECONDS, 2))

                is_passed_or_restoring = self.lifecycle_state in {
                    EmergencyLifecycleState.VEHICLE_PASSED,
                    EmergencyLifecycleState.RESTORING_NORMAL,
                }
                is_prio_act = self.lifecycle_state == EmergencyLifecycleState.PRIORITY_ACTIVE
                is_prio_req = self.lifecycle_state in {
                    EmergencyLifecycleState.PRIORITY_REQUESTED,
                    EmergencyLifecycleState.PRIORITY_ACTIVE,
                }

                if is_passed_or_restoring:
                    safe_status = "NORMAL"
                    curr_action = "NORMAL_CONTROL"
                    status_reason = (
                        "Emergency vehicle passed intersection stopline; priority released."
                        if self.lifecycle_state == EmergencyLifecycleState.VEHICLE_PASSED
                        else "Restoring normal signal timing after emergency vehicle passage."
                    )
                elif is_prio_act:
                    safe_status = "PRIORITY_GRANTED"
                    curr_action = f"PRIORITY_{approach.upper()}_GREEN"
                    status_reason = "Emergency green corridor priority active."
                elif is_prio_req:
                    safe_status = "TRANSITIONING"
                    curr_action = f"REQUEST_{approach.upper()}_PRIORITY"
                    status_reason = "Emergency vehicle requesting green corridor priority."
                else:
                    safe_status = "NORMAL"
                    curr_action = "NORMAL_CONTROL"
                    status_reason = None

                # Build state snapshot
                return EmergencyVehicleState(
                    active=True,
                    vehicle_id=ev_id,
                    vehicle_type=ev_vtype,
                    approach=approach,
                    state=self.lifecycle_state.value,
                    distance=round(dist_to_center, 1),
                    distance_to_stopline=round(dist_to_stopline, 1) if dist_to_stopline is not None else None,
                    speed=round(spd, 2),
                    eta_seconds=eta_seconds,
                    lane_id=lane,
                    edge_id=edge,
                    waiting_time=round(wait, 1),
                    priority_requested=is_prio_req and not is_passed_or_restoring,
                    priority_approved=is_prio_act and not is_passed_or_restoring,
                    priority_active=is_prio_act and not is_passed_or_restoring,
                    priority_duration=round(self.priority_duration, 1),
                    lifecycle_state=self.lifecycle_state.value,
                    safety_status=safe_status,
                    current_action=curr_action,
                    reason=status_reason,
                    timestamp=sim_time,
                    entry_time=self.entry_time,
                    exit_time=self.exit_time,
                    travel_time=travel_time,
                    delay_seconds=delay_sec,
                )

            except Exception as exc:
                logger.error("Error inspecting emergency vehicle %s in TraCI: %s", ev_id, exc)
                return EmergencyVehicleState(active=True, vehicle_id=ev_id, state=self.lifecycle_state.value)

        # ── Case B: Emergency vehicle NOT found in TraCI ───────────────────────
        else:
            if self.lifecycle_state in {
                EmergencyLifecycleState.DETECTED,
                EmergencyLifecycleState.PRIORITY_REQUESTED,
                EmergencyLifecycleState.PRIORITY_ACTIVE,
            }:
                # Disappearance or teleportation recovery: Safely transition out to restore normal signals
                logger.warning(
                    "Emergency vehicle %s disappeared from simulation before passing; restoring normal control.",
                    self.active_vehicle_id,
                )
                self.disappeared_prematurely = True
                self.exit_time = sim_time
                self._record_final_metrics(completed=False)
                self.lifecycle_state = EmergencyLifecycleState.RESTORING_NORMAL
                self._restoring_steps = 1

                return EmergencyVehicleState(
                    active=False,
                    vehicle_id=self.active_vehicle_id,
                    state=EmergencyLifecycleState.RESTORING_NORMAL.value,
                    lifecycle_state=EmergencyLifecycleState.RESTORING_NORMAL.value,
                    safety_status="NORMAL",
                    current_action="NORMAL_CONTROL",
                    reason="Emergency vehicle disappeared; Safety Manager safely restored normal control.",
                    timestamp=sim_time,
                    entry_time=self.entry_time,
                    exit_time=self.exit_time,
                    priority_duration=round(self.priority_duration, 1),
                )

            elif self.lifecycle_state in {EmergencyLifecycleState.VEHICLE_PASSED, EmergencyLifecycleState.RESTORING_NORMAL}:
                # Vehicle departed simulation after completing traversal
                if not self._metrics_recorded and self.entry_time is not None:
                    self.exit_time = self.exit_time or self.passed_time or sim_time
                    self._record_final_metrics(completed=True)
                self.lifecycle_state = EmergencyLifecycleState.IDLE
                self.active_vehicle_id = None
                self._restoring_steps = 0

            return EmergencyVehicleState(
                active=False,
                state=EmergencyLifecycleState.IDLE.value,
                lifecycle_state=EmergencyLifecycleState.IDLE.value,
                timestamp=sim_time,
            )

    def on_priority_requested(self, sim_time: float) -> None:
        """Called when priority green corridor preemption is requested."""
        if self.lifecycle_state in {EmergencyLifecycleState.DETECTED, EmergencyLifecycleState.IDLE}:
            self.lifecycle_state = EmergencyLifecycleState.PRIORITY_REQUESTED
            if self.request_time is None:
                self.request_time = sim_time

    def on_priority_activated(self, sim_time: float, step_length: float = 1.0) -> None:
        """Called when priority green corridor has been safely actuated and is active."""
        if self.lifecycle_state in {EmergencyLifecycleState.DETECTED, EmergencyLifecycleState.PRIORITY_REQUESTED}:
            self.lifecycle_state = EmergencyLifecycleState.PRIORITY_ACTIVE
            if self.priority_active_time is None:
                self.priority_active_time = sim_time

        if self.lifecycle_state == EmergencyLifecycleState.PRIORITY_ACTIVE:
            self.priority_duration += step_length

    def _record_final_metrics(self, completed: bool = True) -> None:
        """Calculate and store empirical summary metrics for the finished emergency run."""
        if self.entry_time is None or self._metrics_recorded:
            return

        exit_t = self.exit_time if self.exit_time is not None else (self.passed_time or self.entry_time)
        travel_t = max(0.1, round(exit_t - self.entry_time, 2))
        delay_t = max(0.0, round(travel_t - FREE_FLOW_TIME_SECONDS, 2))
        time_to_p = (
            round(self.priority_active_time - self.request_time, 2)
            if (self.priority_active_time is not None and self.request_time is not None)
            else 0.0
        )

        metrics = EmergencyCorridorMetrics(
            vehicle_id=self.active_vehicle_id or "EV_01",
            approach=self.approach or "east",
            entry_time=self.entry_time,
            exit_time=exit_t,
            travel_time=travel_t,
            free_flow_time=FREE_FLOW_TIME_SECONDS,
            intersection_delay=delay_t,
            stopped_waiting_time=round(self.last_waiting_time, 2),
            time_to_priority_active=time_to_p,
            priority_duration=round(self.priority_duration, 1),
            completed=completed,
            disappeared_prematurely=self.disappeared_prematurely,
        )
        self._history_metrics.append(metrics)
        self._metrics_recorded = True

    def get_latest_metrics(self) -> Optional[Dict[str, Any]]:
        """Return latest recorded emergency corridor metrics."""
        if self._history_metrics:
            return self._history_metrics[-1].to_dict()
        elif self.entry_time is not None and self.active_vehicle_id is not None:
            # Active in-flight calculation
            exit_t = self.passed_time or self.entry_time
            travel_t = max(0.1, round(exit_t - self.entry_time, 2))
            delay_t = max(0.0, round(travel_t - FREE_FLOW_TIME_SECONDS, 2))
            return {
                "vehicle_id": self.active_vehicle_id,
                "approach": self.approach or "east",
                "entry_time": round(self.entry_time, 1),
                "exit_time": round(exit_t, 1),
                "travel_time": travel_t,
                "free_flow_time": FREE_FLOW_TIME_SECONDS,
                "intersection_delay": delay_t,
                "stopped_waiting_time": round(self.last_waiting_time, 2),
                "time_to_priority_active": round((self.priority_active_time or self.entry_time) - (self.request_time or self.entry_time), 2),
                "priority_duration": round(self.priority_duration, 1),
                "completed": self.passed_time is not None,
                "disappeared_prematurely": self.disappeared_prematurely,
            }
        return None
