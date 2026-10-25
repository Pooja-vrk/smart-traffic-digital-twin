"""Base controller abstract class and signal transition safety manager.

Defines the standard interface for all signal control strategies (Fixed-Time,
Adaptive, DQN) and provides strict safety enforcement for traffic light transitions.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from simulation.state import TrafficState

logger = logging.getLogger(__name__)


class SignalSafetyManager:
    """State machine ensuring safe traffic light phase transitions.

    Guarantees:
    1. Minimum green time enforcement (no premature phase changes).
    2. Mandatory yellow clearance intervals between conflicting green phases.
    3. No unsafe direct Green-to-Green transitions (e.g. NS_GREEN -> EW_GREEN).
    4. Anti-oscillation protection.
    """

    # Phase mappings
    NS_GREEN = 0
    NS_YELLOW = 1
    EW_GREEN = 2
    EW_YELLOW = 3

    GREEN_PHASES = {NS_GREEN, EW_GREEN}
    YELLOW_PHASES = {NS_YELLOW, EW_YELLOW}

    PHASE_NAMES = {
        NS_GREEN: "NS_GREEN",
        NS_YELLOW: "NS_YELLOW",
        EW_GREEN: "EW_GREEN",
        EW_YELLOW: "EW_YELLOW",
    }

    def __init__(
        self,
        min_green_seconds: float = 10.0,
        yellow_seconds: float = 3.0,
        max_green_seconds: float = 60.0,
    ) -> None:
        self.min_green_seconds = min_green_seconds
        self.yellow_seconds = yellow_seconds
        self.max_green_seconds = max_green_seconds

        self.current_phase = self.NS_GREEN
        self.time_in_current_phase = 0.0
        self.is_in_transition = False
        self.target_green_phase = self.NS_GREEN
        self.transition_time_remaining = 0.0

    def reset(self, initial_phase: int = NS_GREEN) -> None:
        """Reset safety state machine."""
        self.current_phase = initial_phase
        self.time_in_current_phase = 0.0
        self.is_in_transition = False
        self.target_green_phase = initial_phase
        self.transition_time_remaining = 0.0

    def step(
        self,
        requested_green_phase: int,
        step_length: float = 1.0,
        is_emergency: bool = False,
    ) -> int:
        """Process requested green phase and return the legally safe phase to apply.

        Args:
            requested_green_phase: Target green phase index (NS_GREEN=0 or EW_GREEN=2).
            step_length: Time step in seconds.
            is_emergency: If True, indicates emergency priority active (prevents premature max-green truncation).

        Returns:
            int: Legally safe phase index (0, 1, 2, or 3).
        """
        # If currently executing a mandatory yellow transition
        if self.is_in_transition:
            self.transition_time_remaining -= step_length
            self.time_in_current_phase += step_length

            if self.transition_time_remaining <= 0.0:
                # Transition complete: switch to target green phase
                self.current_phase = self.target_green_phase
                self.time_in_current_phase = 0.0
                self.is_in_transition = False
                logger.debug("Transition finished. Entered green phase: %s", self.PHASE_NAMES.get(self.current_phase))
            return self.current_phase

        # Currently in a steady green phase (NS_GREEN or EW_GREEN)
        self.time_in_current_phase += step_length

        # Check if caller wants to switch green phases or if max green was exceeded
        # In emergency priority, max green does not prematurely truncate active priority corridor
        wants_change = (requested_green_phase != self.current_phase)
        max_green_exceeded = False if is_emergency else (self.time_in_current_phase >= self.max_green_seconds)

        if (wants_change or max_green_exceeded) and (self.time_in_current_phase >= self.min_green_seconds):
            # Safe to initiate transition
            if self.current_phase == self.NS_GREEN:
                self.current_phase = self.NS_YELLOW
                self.target_green_phase = self.EW_GREEN
            elif self.current_phase == self.EW_GREEN:
                self.current_phase = self.EW_YELLOW
                self.target_green_phase = self.NS_GREEN

            self.is_in_transition = True
            self.transition_time_remaining = self.yellow_seconds - step_length
            self.time_in_current_phase = step_length
            logger.debug("Initiating yellow transition to %s", self.PHASE_NAMES.get(self.target_green_phase))

        return self.current_phase


class EmergencyPriorityEvaluator:
    """Evaluates real-time emergency vehicle state and governs signal priority under safety constraints."""

    VALID_EV_ACTIVE_STATES = {
        "DETECTED",
        "PRIORITY_REQUESTED",
        "PRIORITY_ACTIVE",
        "APPROACHING",
        "INSIDE_JUNCTION",
    }

    @staticmethod
    def evaluate(state: TrafficState, safety_manager: SignalSafetyManager) -> Tuple[Optional[int], Dict[str, Any]]:
        """Evaluate whether emergency vehicle demands priority green and determine safe target corridor.

        Returns:
            Tuple[Optional[int], Dict[str, Any]]:
                - target_green_phase: 0 (NS_GREEN) or 2 (EW_GREEN) if priority is requested, or None.
                - decision_info: Dict containing priority flags, safety status, action, and grounded reason.
        """
        ev = state.emergency
        if not ev or not ev.active or ev.state not in EmergencyPriorityEvaluator.VALID_EV_ACTIVE_STATES:
            is_cleared = (ev and ev.active and ev.state in {"VEHICLE_PASSED", "PASSED", "RESTORING_NORMAL"})
            return None, {
                "priority_requested": False,
                "priority_approved": False,
                "priority_active": False,
                "safety_status": "NORMAL",
                "current_action": "NORMAL_CONTROL",
                "reason": "Emergency vehicle cleared junction; normal traffic control active." if is_cleared else "No emergency vehicle requiring priority clearance.",
            }

        # Determine target green corridor for the emergency approach
        # North / South approach -> NS_GREEN (phase 0)
        # East / West approach   -> EW_GREEN (phase 2)
        if ev.approach in {"north", "south"}:
            target_phase = SignalSafetyManager.NS_GREEN
            target_name = "NORTH_SOUTH"
        else:
            target_phase = SignalSafetyManager.EW_GREEN
            target_name = "EAST_WEST"

        current_phase = safety_manager.current_phase
        is_transitioning = safety_manager.is_in_transition

        dist_str = (
            f"{ev.distance_to_stopline:.1f}m to stopline"
            if getattr(ev, "distance_to_stopline", None) is not None
            else (f"{ev.distance:.1f}m to center" if ev.distance is not None else "")
        )
        eta_str = f", ETA {ev.eta_seconds:.1f}s" if getattr(ev, "eta_seconds", None) is not None else ""
        kinematics_desc = f" ({dist_str}{eta_str})" if dist_str else ""

        # Evaluate safety constraints
        if current_phase == target_phase and not is_transitioning:
            return target_phase, {
                "priority_requested": True,
                "priority_approved": True,
                "priority_active": True,
                "safety_status": "PRIORITY_GRANTED",
                "current_action": f"PRIORITY_{target_name}_GREEN",
                "reason": f"Emergency vehicle {ev.vehicle_id} on {ev.approach.upper()} corridor{kinematics_desc}; priority green granted and holding.",
            }
        elif is_transitioning:
            return target_phase, {
                "priority_requested": True,
                "priority_approved": False,
                "priority_active": False,
                "safety_status": "TRANSITIONING",
                "current_action": f"SAFE_YELLOW_TRANSITION_TO_{target_name}",
                "reason": f"Emergency vehicle {ev.vehicle_id} on {ev.approach.upper()}{kinematics_desc}; Safety Manager clearing yellow interval ({safety_manager.transition_time_remaining:.1f}s remaining).",
            }
        elif safety_manager.time_in_current_phase < safety_manager.min_green_seconds:
            time_left = safety_manager.min_green_seconds - safety_manager.time_in_current_phase
            return target_phase, {
                "priority_requested": True,
                "priority_approved": False,
                "priority_active": False,
                "safety_status": "MIN_GREEN_HOLD",
                "current_action": "MIN_GREEN_SAFETY_HOLD",
                "reason": f"Emergency vehicle {ev.vehicle_id} detected on {ev.approach.upper()}{kinematics_desc}; Safety Manager enforcing minimum green clearance ({time_left:.1f}s remaining).",
            }
        else:
            return target_phase, {
                "priority_requested": True,
                "priority_approved": True,
                "priority_active": False,
                "safety_status": "INITIATING_TRANSITION",
                "current_action": f"REQUEST_{target_name}_PRIORITY",
                "reason": f"Emergency vehicle {ev.vehicle_id} on {ev.approach.upper()}{kinematics_desc}; Safety Manager initiating transition to {target_name} corridor.",
            }


class BaseController(ABC):
    """Abstract Base Class for all traffic signal controllers."""

    def __init__(
        self,
        name: str,
        tls_id: str = "center",
        safety_manager: Optional[SignalSafetyManager] = None,
        enable_emergency_priority: bool = True,
    ) -> None:
        self.name = name
        self.tls_id = tls_id
        self.safety_manager = safety_manager or SignalSafetyManager()
        self.enable_emergency_priority = enable_emergency_priority
        self.phase_change_count = 0
        self._last_applied_phase: Optional[int] = None

    def reset(self) -> None:
        """Reset controller internal state."""
        self.safety_manager.reset()
        self.phase_change_count = 0
        self._last_applied_phase = None

    @abstractmethod
    def decide_target_phase(self, state: TrafficState) -> int:
        """Determine desired target green phase given the current traffic state.

        Args:
            state: Instantaneous traffic state from TraCI.

        Returns:
            int: Desired green phase (0 for NS_GREEN, 2 for EW_GREEN).
        """
        pass

    def step(self, state: TrafficState, traci_controller: Any) -> int:
        """Execute one control step, enforce safety, and actuate phase on TraCI.

        Args:
            state: Current traffic state.
            traci_controller: TraCI controller instance.

        Returns:
            int: Applied signal phase index.
        """
        # 1. Controller's normal traffic decision
        desired_green = self.decide_target_phase(state)

        # 2. Emergency priority evaluation
        is_ev = False
        ev_decision: Dict[str, Any] = {}
        if self.enable_emergency_priority:
            ev_target_green, ev_decision = EmergencyPriorityEvaluator.evaluate(state, self.safety_manager)
            if ev_target_green is not None:
                desired_green = ev_target_green
                is_ev = True

        if state.emergency and state.emergency.active:
            state.emergency.priority_requested = ev_decision.get("priority_requested", False)
            state.emergency.priority_approved = ev_decision.get("priority_approved", False)
            state.emergency.priority_active = ev_decision.get("priority_active", False)
            state.emergency.safety_status = ev_decision.get("safety_status", "NORMAL")
            state.emergency.current_action = ev_decision.get("current_action", "NORMAL_CONTROL")
            state.emergency.reason = ev_decision.get("reason")

        # 3. Enforce Safety Manager transition constraints
        safe_phase = self.safety_manager.step(
            desired_green,
            step_length=traci_controller.step_length,
            is_emergency=is_ev,
        )

        if self._last_applied_phase is not None and safe_phase != self._last_applied_phase:
            self.phase_change_count += 1

        self._last_applied_phase = safe_phase
        traci_controller.set_tls_phase(safe_phase)
        return safe_phase

    def get_stats(self) -> Dict[str, Any]:
        """Return controller operational statistics."""
        return {
            "controller_name": self.name,
            "phase_change_count": self.phase_change_count,
            "current_phase": self.safety_manager.current_phase,
            "time_in_current_phase": round(self.safety_manager.time_in_current_phase, 1),
            "is_in_transition": self.safety_manager.is_in_transition,
        }
