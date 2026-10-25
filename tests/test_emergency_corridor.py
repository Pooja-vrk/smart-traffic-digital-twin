"""Tests for Phase 4: Emergency Green Corridor Preemption.

Verifies:
1. Emergency vehicle TraCI detection, approach mapping, stopline distance, and safe ETA.
2. Explicit 7-stage lifecycle state machine transitions:
   IDLE -> DETECTED -> PRIORITY_REQUESTED -> PRIORITY_ACTIVE -> VEHICLE_PASSED -> RESTORING_NORMAL -> IDLE.
3. Premature disappearance / teleportation recovery without priority deadlock.
4. Signal safety enforcement: minimum green clearance, yellow transition clearance, and anti-cut-off max green hold.
5. Agentic traffic decision engine priority selection, safety validation, and grounded explainability.
6. Empirical metric calculations (travel time, free-flow time, intersection delay, time to priority).
7. End-to-end real SUMO simulation run with emergency vehicle preemption.
"""

from __future__ import annotations

import unittest.mock as mock
import pytest
from pathlib import Path

from simulation.agentic.engine import AgenticTrafficEngine
from simulation.agentic.models import ActionName, SafetyValidationStatus
from simulation.controllers.base_controller import (
    BaseController,
    EmergencyPriorityEvaluator,
    SignalSafetyManager,
)
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.emergency import (
    EmergencyCorridorTracker,
    EmergencyLifecycleState,
    FREE_FLOW_TIME_SECONDS,
    INFLOW_EDGE_LENGTH_METERS,
)
from simulation.environment import TrafficSimulationEnvironment
from simulation.scenario_generator import DirectionBias, ScenarioConfig, ScenarioDemandGenerator
from simulation.state import ApproachState, EmergencyVehicleState, TrafficState


class DummyTraCIModule:
    """Mock TraCI module for unit testing vehicle inspection."""

    def __init__(self, vehicles: dict | None = None):
        self.vehicles = vehicles or {}

    @property
    def vehicle(self):
        class VehicleAPI:
            def __init__(outer, data):
                outer.data = data

            def getIDList(outer):
                return list(outer.data.keys())

            def getTypeID(outer, vid):
                return outer.data[vid].get("vtype", "standard_car")

            def getVehicleClass(outer, vid):
                return outer.data[vid].get("vclass", "")

            def getPosition(outer, vid):
                return outer.data[vid].get("pos", (300.0, 300.0))

            def getAngle(outer, vid):
                return outer.data[vid].get("angle", 0.0)

            def getSpeed(outer, vid):
                return outer.data[vid].get("speed", 13.89)

            def getWaitingTime(outer, vid):
                return outer.data[vid].get("wait", 0.0)

            def getLaneID(outer, vid):
                return outer.data[vid].get("lane", "E2C_0")

            def getRoadID(outer, vid):
                return outer.data[vid].get("edge", "E2C")

            def getLanePosition(outer, vid):
                return outer.data[vid].get("lane_pos", 100.0)

            def getLength(outer, vid):
                return outer.data[vid].get("length", 6.5)

            def getWidth(outer, vid):
                return outer.data[vid].get("width", 2.2)

        return VehicleAPI(self.vehicles)


class TestEmergencyCorridorTracking:
    """Unit tests for TraCI emergency vehicle kinematic tracking and stopline distance."""

    def test_detection_and_inflow_approach_mapping(self):
        """Test emergency vehicle detection and approach corridor mapping across all 4 directions."""
        tracker = EmergencyCorridorTracker()

        # East corridor inflow
        mock_traci = DummyTraCIModule({
            "EV_01": {
                "vtype": "emergency_vehicle",
                "vclass": "emergency",
                "edge": "E2C",
                "lane": "E2C_0",
                "lane_pos": 189.60,
                "pos": (400.0, 300.0),
                "speed": 20.0,
                "wait": 0.0,
            }
        })
        st = tracker.update_from_traci(mock_traci, sim_time=15.0)
        assert st.active is True
        assert st.vehicle_id == "EV_01"
        assert st.approach == "east"
        assert st.distance_to_stopline == round(INFLOW_EDGE_LENGTH_METERS - 189.60, 1)  # 100.0m
        assert st.speed == 20.0
        assert st.eta_seconds == 5.0  # 100m / 20m/s
        assert st.lifecycle_state == EmergencyLifecycleState.DETECTED.value

    def test_low_speed_eta_handling(self):
        """Test that vehicle halted at red light has eta_seconds=None to avoid division-by-zero."""
        tracker = EmergencyCorridorTracker()
        mock_traci = DummyTraCIModule({
            "EV_01": {
                "vtype": "emergency_vehicle",
                "vclass": "emergency",
                "edge": "N2C",
                "lane": "N2C_0",
                "lane_pos": 280.0,
                "pos": (300.0, 320.0),
                "speed": 0.2,  # Halted / crawling
                "wait": 12.0,
            }
        })
        st = tracker.update_from_traci(mock_traci, sim_time=25.0)
        assert st.active is True
        assert st.speed == 0.2
        assert st.eta_seconds is None  # Safe handling for speed < 1.0 m/s
        assert st.distance_to_stopline == round(INFLOW_EDGE_LENGTH_METERS - 280.0, 1)

    def test_explicit_7_stage_lifecycle_transitions(self):
        """Test complete progression through IDLE -> DETECTED -> PRIORITY_REQUESTED -> PRIORITY_ACTIVE -> VEHICLE_PASSED -> RESTORING_NORMAL -> IDLE."""
        tracker = EmergencyCorridorTracker()
        assert tracker.lifecycle_state == EmergencyLifecycleState.IDLE

        # 1. Detection on inflow edge
        mock_traci_1 = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": "E2C", "lane_pos": 50.0, "speed": 15.0}
        })
        st1 = tracker.update_from_traci(mock_traci_1, sim_time=10.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.DETECTED

        # 2. Priority requested
        tracker.on_priority_requested(sim_time=11.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.PRIORITY_REQUESTED

        # 3. Priority green active
        tracker.on_priority_activated(sim_time=13.0, step_length=1.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.PRIORITY_ACTIVE
        assert tracker.priority_duration == 1.0

        # Another step in priority active
        tracker.on_priority_activated(sim_time=14.0, step_length=1.0)
        assert tracker.priority_duration == 2.0

        # 4. Vehicle enters junction stopline (:center internal edge)
        mock_traci_2 = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": ":center_6_0", "lane_pos": 5.0, "speed": 18.0}
        })
        st2 = tracker.update_from_traci(mock_traci_2, sim_time=15.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.VEHICLE_PASSED
        assert st2.distance_to_stopline is None
        assert st2.eta_seconds is None
        assert st2.priority_active is False

        # 5. Vehicle enters exit edge C2W -> RESTORING_NORMAL
        mock_traci_3 = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": "C2W", "lane_pos": 10.0, "speed": 20.0}
        })
        st3 = tracker.update_from_traci(mock_traci_3, sim_time=16.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.RESTORING_NORMAL
        assert st3.distance_to_stopline is None
        assert st3.eta_seconds is None
        assert st3.priority_active is False

        # 6. Next step after departure -> IDLE
        mock_traci_empty = DummyTraCIModule({})
        st4 = tracker.update_from_traci(mock_traci_empty, sim_time=17.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.IDLE
        assert st4.active is False

    def test_exit_timing_and_passage_detection_agreement(self):
        """Regression test: verify exit_time matches passed_time at VEHICLE_PASSED, and travel_time is frozen."""
        tracker = EmergencyCorridorTracker()

        # Enters inflow at t=6.0s
        tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "E2C", "lane_pos": 0.0, "speed": 20.0}}),
            sim_time=6.0,
        )
        assert tracker.entry_time == 6.0
        tracker.on_priority_requested(sim_time=7.0)
        tracker.on_priority_activated(sim_time=9.0)

        # Crosses stopline into junction at t=29.0s
        st_pass = tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": ":center_6_0", "lane_pos": 2.0, "speed": 20.0}}),
            sim_time=29.0,
        )
        assert tracker.lifecycle_state == EmergencyLifecycleState.VEHICLE_PASSED
        assert tracker.passed_time == 29.0
        assert tracker.exit_time == 29.0
        assert st_pass.travel_time == 23.0  # 29.0 - 6.0 = 23.0s
        assert st_pass.distance_to_stopline is None
        assert st_pass.eta_seconds is None

        # Next step t=30.0s in RESTORING_NORMAL
        st_res = tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "C2W", "lane_pos": 10.0, "speed": 20.0}}),
            sim_time=30.0,
        )
        assert tracker.lifecycle_state == EmergencyLifecycleState.RESTORING_NORMAL
        assert st_res.travel_time == 23.0  # Must be frozen at 23.0s, NOT drifting with sim_time!
        assert st_res.distance_to_stopline is None
        assert st_res.eta_seconds is None

        # Advance further: t=31.0s, t=40.0s (vehicle still traversing C2W)
        for t in range(31, 41):
            st_idle = tracker.update_from_traci(
                DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "C2W", "lane_pos": 10.0 + (t - 30) * 20.0, "speed": 20.0}}),
                sim_time=float(t),
            )
            assert tracker.lifecycle_state == EmergencyLifecycleState.IDLE
            assert st_idle.active is False
            assert st_idle.travel_time == 23.0

        metrics = tracker.get_latest_metrics()
        assert metrics is not None
        assert metrics["entry_time"] == 6.0
        assert metrics["exit_time"] == 29.0
        assert metrics["travel_time"] == 23.0
        assert metrics["completed"] is True

    def test_repeated_telemetry_after_passage_unavailable_distance_and_eta(self):
        """Regression test: verify distance_to_stopline and eta_seconds are None (not 0.0 or QUEUED) during/after passage."""
        tracker = EmergencyCorridorTracker()

        # Inflow approach
        st1 = tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "W2C", "lane_pos": 200.0, "speed": 20.0}}),
            sim_time=10.0,
        )
        assert st1.distance_to_stopline == round(INFLOW_EDGE_LENGTH_METERS - 200.0, 1)
        assert st1.eta_seconds is not None

        # Vehicle crosses stopline
        st2 = tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": ":center_2_0", "lane_pos": 5.0, "speed": 20.0}}),
            sim_time=15.0,
        )
        assert st2.state == "VEHICLE_PASSED"
        assert st2.distance_to_stopline is None
        assert st2.eta_seconds is None
        assert st2.priority_active is False
        assert st2.priority_requested is False

        # Restoring step
        st3 = tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "C2E", "lane_pos": 10.0, "speed": 20.0}}),
            sim_time=16.0,
        )
        assert st3.state == "RESTORING_NORMAL"
        assert st3.distance_to_stopline is None
        assert st3.eta_seconds is None
        assert st3.priority_active is False

    def test_lifecycle_completion_transitions_to_idle_while_vehicle_on_outflow_edge(self):
        """Regression test: verify tracker transitions to IDLE and remains active=False while EV continues on C2W."""
        tracker = EmergencyCorridorTracker()

        # Inflow approach
        tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "E2C", "lane_pos": 250.0, "speed": 20.0}}),
            sim_time=5.0,
        )
        tracker.on_priority_requested(sim_time=6.0)
        tracker.on_priority_activated(sim_time=8.0)

        # Cross stopline
        tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": ":center_6_0", "lane_pos": 5.0, "speed": 20.0}}),
            sim_time=10.0,
        )
        assert tracker.lifecycle_state == EmergencyLifecycleState.VEHICLE_PASSED

        # Step 11: Restoring normal
        tracker.update_from_traci(
            DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "C2W", "lane_pos": 10.0, "speed": 20.0}}),
            sim_time=11.0,
        )
        assert tracker.lifecycle_state == EmergencyLifecycleState.RESTORING_NORMAL

        # Steps 12-25: Vehicle continues along 289.6m C2W edge before leaving SUMO
        for t in range(12, 26):
            pos_m = 10.0 + (t - 11) * 20.0
            st = tracker.update_from_traci(
                DummyTraCIModule({"EV_01": {"vtype": "ambulance", "edge": "C2W", "lane_pos": pos_m, "speed": 20.0}}),
                sim_time=float(t),
            )
            assert tracker.lifecycle_state == EmergencyLifecycleState.IDLE
            assert st.active is False
            assert st.state == "IDLE"
            assert st.distance_to_stopline is None
            assert st.eta_seconds is None

        # Metrics recorded exactly once
        assert len(tracker._history_metrics) == 1

    def test_signal_restoration_releases_priority_without_deadlock(self):
        """Regression test: verify evaluator and safety manager cleanly resume normal control when EV passes."""
        safety = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
        safety.reset(initial_phase=SignalSafetyManager.EW_GREEN)

        # Vehicle passes: state is VEHICLE_PASSED
        passed_ev = EmergencyVehicleState(
            active=True,
            vehicle_id="EV_01",
            approach="east",
            state="VEHICLE_PASSED",
            distance_to_stopline=None,
            eta_seconds=None,
            priority_active=False,
            priority_requested=False,
        )
        t_state = TrafficState(emergency=passed_ev)
        target_phase, dec = EmergencyPriorityEvaluator.evaluate(t_state, safety)

        # Priority is released!
        assert target_phase is None
        assert dec["priority_active"] is False
        assert dec["priority_requested"] is False
        assert "cleared junction" in dec["reason"]

        # Normal controller (e.g. requesting NS_GREEN) can now actuate without deadlock
        # Advance 10s min green in EW_GREEN
        for _ in range(10):
            safety.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0)

        # Request NS_GREEN: transitions safely through EW_YELLOW to NS_GREEN
        p1 = safety.step(requested_green_phase=SignalSafetyManager.NS_GREEN, step_length=1.0, is_emergency=False)
        assert p1 == SignalSafetyManager.EW_YELLOW
        assert safety.is_in_transition is True
        safety.step(requested_green_phase=SignalSafetyManager.NS_GREEN, step_length=1.0, is_emergency=False)
        p3 = safety.step(requested_green_phase=SignalSafetyManager.NS_GREEN, step_length=1.0, is_emergency=False)
        assert p3 == SignalSafetyManager.NS_GREEN
        assert safety.is_in_transition is False

    def test_disappearance_teleportation_recovery(self):
        """Test graceful recovery when emergency vehicle teleports or disappears prematurely."""
        tracker = EmergencyCorridorTracker()

        # Vehicle active
        mock_active = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": "E2C", "lane_pos": 100.0, "speed": 15.0}
        })
        tracker.update_from_traci(mock_active, sim_time=10.0)
        tracker.on_priority_requested(sim_time=11.0)
        tracker.on_priority_activated(sim_time=12.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.PRIORITY_ACTIVE

        # Vehicle suddenly missing from TraCI
        mock_empty = DummyTraCIModule({})
        st_recovered = tracker.update_from_traci(mock_empty, sim_time=13.0)
        assert tracker.disappeared_prematurely is True
        assert st_recovered.active is False
        assert st_recovered.state == EmergencyLifecycleState.RESTORING_NORMAL.value

        # Following step restores IDLE
        tracker.update_from_traci(mock_empty, sim_time=14.0)
        assert tracker.lifecycle_state == EmergencyLifecycleState.IDLE


class TestEmergencySafetyManagerConstraints:
    """Tests guaranteeing that emergency priority strictly adheres to SignalSafetyManager rules."""

    def test_min_green_enforcement_during_emergency_preemption(self):
        """Verify that an emergency vehicle request CANNOT prematurely cut off conflicting green before min green."""
        safety = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
        safety.reset(initial_phase=SignalSafetyManager.NS_GREEN)

        # 2 seconds into NS_GREEN
        safety.step(requested_green_phase=SignalSafetyManager.NS_GREEN, step_length=2.0)
        assert safety.time_in_current_phase == 2.0

        # Emergency vehicle arrives on East corridor requesting EW_GREEN
        ev_state = EmergencyVehicleState(
            active=True,
            vehicle_id="EV_01",
            approach="east",
            state="APPROACHING",
            distance=200.0,
            distance_to_stopline=189.6,
        )
        traffic_state = TrafficState(emergency=ev_state)

        # Evaluator checks safety manager
        target_phase, decision = EmergencyPriorityEvaluator.evaluate(traffic_state, safety)
        assert target_phase == SignalSafetyManager.EW_GREEN
        assert decision["safety_status"] == "MIN_GREEN_HOLD"
        assert decision["priority_active"] is False

        # Attempt to step safety manager with requested emergency green phase
        safe_phase = safety.step(requested_green_phase=target_phase, step_length=1.0, is_emergency=True)
        # MUST remain NS_GREEN (phase 0) because min green (10s) is not satisfied!
        assert safe_phase == SignalSafetyManager.NS_GREEN

    def test_mandatory_yellow_clearance_enforcement(self):
        """Verify that transition to emergency green MUST pass through mandatory yellow clearance interval."""
        safety = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
        safety.reset(initial_phase=SignalSafetyManager.NS_GREEN)

        # Satisfy min green (advance 10 seconds)
        for _ in range(10):
            safety.step(requested_green_phase=SignalSafetyManager.NS_GREEN, step_length=1.0)
        assert safety.time_in_current_phase >= 10.0

        # Request emergency preemption to EW_GREEN
        phase_1 = safety.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0, is_emergency=True)
        # MUST enter NS_YELLOW (phase 1)
        assert phase_1 == SignalSafetyManager.NS_YELLOW
        assert safety.is_in_transition is True

        # Second step of yellow
        phase_2 = safety.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0, is_emergency=True)
        assert phase_2 == SignalSafetyManager.NS_YELLOW

        # Third step completes 3.0s yellow clearance -> enters EW_GREEN
        phase_3 = safety.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0, is_emergency=True)
        assert phase_3 == SignalSafetyManager.EW_GREEN
        assert safety.is_in_transition is False

    def test_max_green_does_not_cut_off_emergency_corridor(self):
        """Verify that standard 60-second max green does not prematurely cut off active emergency priority corridor."""
        safety = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0, max_green_seconds=60.0)
        safety.reset(initial_phase=SignalSafetyManager.EW_GREEN)

        # Advance 65 seconds under emergency hold (requested EW_GREEN, is_emergency=True)
        for _ in range(65):
            phase = safety.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0, is_emergency=True)
            assert phase == SignalSafetyManager.EW_GREEN
            assert safety.is_in_transition is False

        # If is_emergency is False, max green SHOULD force a transition to yellow
        phase_forced = safety.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0, is_emergency=False)
        assert phase_forced == SignalSafetyManager.EW_YELLOW
        assert safety.is_in_transition is True


class TestAgenticEngineEmergencyIntegration:
    """Tests integrating emergency preemption into the complete 7-stage AgenticTrafficEngine."""

    def test_agentic_engine_emergency_override_and_explainability(self):
        """Test that AgenticTrafficEngine selects REQUEST_EMERGENCY_PRIORITY and produces grounded explanation."""
        controller = FixedTimeController()
        safety = SignalSafetyManager()
        engine = AgenticTrafficEngine(controller=controller, safety_manager=safety)

        # Construct state with emergency vehicle approaching from East
        ev = EmergencyVehicleState(
            active=True,
            vehicle_id="EV_01",
            approach="east",
            state="DETECTED",
            distance=150.0,
            distance_to_stopline=139.6,
            speed=18.0,
            eta_seconds=7.8,
        )
        state = TrafficState(
            simulation_time=20.0,
            step=20,
            current_phase=SignalSafetyManager.NS_GREEN,
            time_since_phase_change=15.0,
            emergency=ev,
        )

        mock_traci = mock.MagicMock()
        mock_traci.step_length = 1.0

        val_phase, decision = engine.step(state, mock_traci)
        assert decision.requested_action == ActionName.REQUEST_EMERGENCY_PRIORITY.value
        assert decision.requested_phase == SignalSafetyManager.EW_GREEN
        assert "EV_01" in decision.decision_reason
        assert "EAST" in decision.decision_reason


class TestEmergencyEmpiricalMetrics:
    """Tests empirical metric calculations grounded in SUMO network geometry."""

    def test_metrics_calculation(self):
        """Test computation of travel time, intersection delay, and priority activation time."""
        tracker = EmergencyCorridorTracker()

        # Vehicle enters at t=15.0s
        mock_inflow = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": "E2C", "lane_pos": 0.0, "speed": 22.22}
        })
        tracker.update_from_traci(mock_inflow, sim_time=15.0)
        assert tracker.entry_time == 15.0

        tracker.on_priority_requested(sim_time=16.0)
        tracker.on_priority_activated(sim_time=19.0, step_length=1.0)  # 3s yellow clearance

        # Vehicle crosses stopline at t=28.0s (13.0s traversal)
        mock_junction = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": ":center_6_0", "lane_pos": 10.0, "speed": 22.22}
        })
        tracker.update_from_traci(mock_junction, sim_time=28.0)

        # Vehicle enters exit edge C2W at t=29.0s -> RESTORING_NORMAL
        mock_exit = DummyTraCIModule({
            "EV_01": {"vtype": "emergency_vehicle", "edge": "C2W", "lane_pos": 20.0, "speed": 22.22}
        })
        tracker.update_from_traci(mock_exit, sim_time=29.0)

        metrics = tracker.get_latest_metrics()
        assert metrics is not None
        assert metrics["vehicle_id"] == "EV_01"
        assert metrics["entry_time"] == 15.0
        assert metrics["exit_time"] == 28.0
        assert metrics["travel_time"] == 13.0  # 28.0 - 15.0 = 13.0s (stopline crossing traversal)
        assert metrics["free_flow_time"] == FREE_FLOW_TIME_SECONDS  # 13.03s
        assert metrics["intersection_delay"] == 0.0  # 13.0s <= 13.03s free flow
        assert metrics["time_to_priority_active"] == 3.0  # 19 - 16


class TestEmergencyRealSumoSimulation:
    """End-to-end integration tests with real SUMO simulation."""

    @pytest.mark.parametrize("approach,expected_green", [
        ("east", SignalSafetyManager.EW_GREEN),
        ("west", SignalSafetyManager.EW_GREEN),
        ("north", SignalSafetyManager.NS_GREEN),
        ("south", SignalSafetyManager.NS_GREEN),
    ])
    def test_real_sumo_all_four_approaches(self, approach: str, expected_green: int):
        """Run an end-to-end SUMO simulation pass for each supported inflow approach."""
        cfg = ScenarioConfig(
            name=f"Emergency Preemption Test {approach.upper()}",
            density="medium",
            multiplier=1.0,
            direction_bias=DirectionBias(north=25, south=25, east=25, west=25),
            duration=40,
            seed=42,
            emergency_vehicle=True,
            emergency_approach=approach,
            emergency_vehicle_type="ambulance",
            emergency_step=5,
        )
        _, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(cfg)

        controller = FixedTimeController()
        env = TrafficSimulationEnvironment(
            sumocfg_path=sumocfg_path,
            use_gui=False,
            step_length=1.0,
            seed=42,
            controller=controller,
            enable_emergency_priority=True,
        )

        try:
            env.start()
            ev_detected = False
            priority_active = False
            correct_green_held = False

            for _ in range(1, 40):
                state = env.step()
                if state.emergency and state.emergency.active:
                    ev_detected = True
                    assert state.emergency.approach == approach
                    if state.emergency.priority_active:
                        priority_active = True
                        if state.current_phase == expected_green:
                            correct_green_held = True

            ev_metrics = env.get_emergency_metrics()

            assert ev_detected is True, f"Emergency vehicle was not detected on {approach} approach"
            assert priority_active is True, f"Emergency priority corridor was not activated on {approach} approach"
            assert correct_green_held is True, f"Phase {expected_green} was not held for {approach} approach"
            assert ev_metrics is not None, f"Emergency metrics were not captured for {approach} approach"
            assert ev_metrics["vehicle_id"] == "EV_01"
            assert ev_metrics["approach"] == approach
            assert ev_metrics["travel_time"] > 10.0, f"Travel time {ev_metrics['travel_time']}s is suspiciously short"
        finally:
            env.close()

    @pytest.mark.parametrize("vehicle_type", ["ambulance", "fire_engine", "emergency_vehicle"])
    def test_real_sumo_vehicle_types(self, vehicle_type: str):
        """Verify that ambulance, fire_engine, and generic emergency_vehicle are all recognized by TraCI."""
        cfg = ScenarioConfig(
            name=f"Emergency Vehicle Type Test ({vehicle_type})",
            density="low",
            duration=35,
            seed=42,
            emergency_vehicle=True,
            emergency_approach="east",
            emergency_vehicle_type=vehicle_type,
            emergency_step=5,
        )
        _, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(cfg)

        controller = FixedTimeController()
        env = TrafficSimulationEnvironment(
            sumocfg_path=sumocfg_path,
            use_gui=False,
            step_length=1.0,
            seed=42,
            controller=controller,
            enable_emergency_priority=True,
        )

        try:
            env.start()
            ev_detected = False
            for _ in range(1, 35):
                state = env.step()
                if state.emergency and state.emergency.active:
                    ev_detected = True
                    break

            assert ev_detected is True, f"Vehicle type {vehicle_type} was not detected by TraCI"
        finally:
            env.close()

    def test_real_sumo_exit_edge_travel_time_preservation(self):
        """Regression test: verify that reaching the exit edge does not re-trigger DETECTED or reset entry_time."""
        cfg = ScenarioConfig(
            name="Exit Edge Integrity Test",
            density="medium",
            duration=40,
            seed=42,
            emergency_vehicle=True,
            emergency_approach="north",
            emergency_vehicle_type="ambulance",
            emergency_step=5,
        )
        _, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(cfg)

        controller = FixedTimeController()
        env = TrafficSimulationEnvironment(
            sumocfg_path=sumocfg_path,
            use_gui=False,
            step_length=1.0,
            seed=42,
            controller=controller,
            enable_emergency_priority=True,
        )

        try:
            env.start()
            entry_time_observed = None
            for _ in range(1, 40):
                state = env.step()
                if state.emergency and state.emergency.active and entry_time_observed is None:
                    entry_time_observed = state.simulation_time

            metrics = env.get_emergency_metrics()
            assert metrics is not None
            assert metrics["entry_time"] is not None
            assert metrics["entry_time"] <= entry_time_observed + 1.0
            assert metrics["travel_time"] >= 12.0
            assert metrics["exit_time"] > metrics["entry_time"]
        finally:
            env.close()

    def test_real_sumo_disabled_priority_normal_operation(self):
        """Verify normal controller operates without priority override when enable_emergency_priority=False."""
        cfg = ScenarioConfig(
            name="Disabled Priority Test",
            density="medium",
            duration=35,
            seed=42,
            emergency_vehicle=True,
            emergency_approach="east",
            emergency_vehicle_type="ambulance",
            emergency_step=5,
        )
        _, sumocfg_path = ScenarioDemandGenerator.generate_scenario_files(cfg)

        controller = FixedTimeController()
        env = TrafficSimulationEnvironment(
            sumocfg_path=sumocfg_path,
            use_gui=False,
            step_length=1.0,
            seed=42,
            controller=controller,
            enable_emergency_priority=False,
        )

        try:
            env.start()
            priority_activated_any = False
            for _ in range(1, 35):
                state = env.step()
                if state.emergency and state.emergency.priority_active:
                    priority_activated_any = True

            assert priority_activated_any is False, "Priority was activated despite enable_emergency_priority=False"
        finally:
            env.close()

    def test_emergency_presets_registered(self):
        """Verify that all 4 approach presets are properly registered in SCENARIO_PRESETS."""
        from backend.services.scenario_manager import SCENARIO_PRESETS

        preset_ids = {p.id for p in SCENARIO_PRESETS}
        assert "emergency_east" in preset_ids
        assert "emergency_west" in preset_ids
        assert "emergency_north" in preset_ids
        assert "emergency_south" in preset_ids

        for app_name in ["east", "west", "north", "south"]:
            p = next(x for x in SCENARIO_PRESETS if x.id == f"emergency_{app_name}")
            assert p.emergency_vehicle is True
            assert p.emergency_approach == app_name
            assert p.emergency_vehicle_type in ["ambulance", "fire_engine", "emergency_vehicle"]
            assert p.emergency_step is not None
