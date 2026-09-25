"""Automated unit and integration tests for traffic signal controllers and baseline experiments."""

import json
import tempfile
from pathlib import Path
import pytest

from simulation.config import AdaptiveConfig, ExperimentConfig, FixedTimeConfig
from simulation.controllers.adaptive_controller import AdaptiveController
from simulation.controllers.base_controller import BaseController, SignalSafetyManager
from simulation.controllers.fixed_time_controller import FixedTimeController
from simulation.environment import TrafficSimulationEnvironment
from simulation.state import ApproachState, TrafficState


def test_fixed_time_controller_init():
    """Verify FixedTimeController initializes with default and custom configurations."""
    controller = FixedTimeController()
    assert controller.name == "Fixed-Time"
    assert controller.config.ns_green_seconds == 30.0

    custom_cfg = FixedTimeConfig(ns_green_seconds=45.0, ew_green_seconds=25.0)
    controller_custom = FixedTimeController(config=custom_cfg)
    assert controller_custom.config.ns_green_seconds == 45.0
    assert controller_custom.config.ew_green_seconds == 25.0


def test_adaptive_controller_init():
    """Verify AdaptiveController initializes with default and custom configurations."""
    controller = AdaptiveController()
    assert controller.name == "Rule-Based Adaptive"
    assert controller.config.min_green_seconds == 10.0
    assert controller.config.pressure_difference_threshold == 3

    custom_cfg = AdaptiveConfig(min_green_seconds=15.0, pressure_difference_threshold=5)
    controller_custom = AdaptiveController(config=custom_cfg)
    assert controller_custom.config.min_green_seconds == 15.0
    assert controller_custom.config.pressure_difference_threshold == 5


def test_safety_manager_min_green_enforcement():
    """Verify SignalSafetyManager blocks phase change requests before minimum green time expires."""
    safety_mgr = SignalSafetyManager(min_green_seconds=10.0, yellow_seconds=3.0)
    safety_mgr.reset(initial_phase=SignalSafetyManager.NS_GREEN)

    # Step 5 seconds requesting EW_GREEN (2) -> Should remain in NS_GREEN (0) because min green is 10s
    for _ in range(5):
        phase = safety_mgr.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0)
        assert phase == SignalSafetyManager.NS_GREEN
        assert not safety_mgr.is_in_transition

    # Step another 5 seconds (total 10s elapsed) requesting EW_GREEN (2) -> Should enter NS_YELLOW (1)
    phase = None
    for _ in range(5):
        phase = safety_mgr.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0)

    assert phase == SignalSafetyManager.NS_YELLOW
    assert safety_mgr.is_in_transition


def test_safety_manager_mandatory_yellow_transition():
    """Verify SignalSafetyManager enforces yellow duration before entering the target green phase."""
    safety_mgr = SignalSafetyManager(min_green_seconds=5.0, yellow_seconds=3.0)
    safety_mgr.reset(initial_phase=SignalSafetyManager.NS_GREEN)

    # Elapse 5 seconds to satisfy min green
    for _ in range(5):
        safety_mgr.step(requested_green_phase=SignalSafetyManager.NS_GREEN, step_length=1.0)

    # Request EW_GREEN -> Must enter NS_YELLOW (1)
    phase_t1 = safety_mgr.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0)
    assert phase_t1 == SignalSafetyManager.NS_YELLOW
    assert safety_mgr.is_in_transition

    # Yellow step 2
    phase_t2 = safety_mgr.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0)
    assert phase_t2 == SignalSafetyManager.NS_YELLOW

    # Yellow step 3 (transition ends)
    phase_t3 = safety_mgr.step(requested_green_phase=SignalSafetyManager.EW_GREEN, step_length=1.0)
    assert phase_t3 == SignalSafetyManager.EW_GREEN
    assert not safety_mgr.is_in_transition


def test_adaptive_controller_pressure_decision():
    """Verify AdaptiveController decisions respond properly to queue differentials."""
    controller = AdaptiveController(
        config=AdaptiveConfig(min_green_seconds=5.0, pressure_difference_threshold=3)
    )

    state = TrafficState()
    # Initial state: heavy NS traffic, low EW traffic -> Should want NS_GREEN
    state.north.queue_length = 8
    state.south.queue_length = 6
    state.east.queue_length = 1
    state.west.queue_length = 0

    target_phase = controller.decide_target_phase(state)
    assert target_phase == SignalSafetyManager.NS_GREEN

    # Simulate EW surge exceeding threshold (EW=12, NS=2 -> delta = 10 >= 3)
    state.north.queue_length = 1
    state.south.queue_length = 1
    state.east.queue_length = 7
    state.west.queue_length = 5

    # Satisfy elapsed green time in safety manager
    controller.safety_manager.time_in_current_phase = 6.0

    target_phase_surge = controller.decide_target_phase(state)
    assert target_phase_surge == SignalSafetyManager.EW_GREEN


def test_headless_fixed_time_simulation():
    """Verify FixedTimeController executes cleanly in headless SUMO simulation."""
    controller = FixedTimeController(
        config=FixedTimeConfig(ns_green_seconds=15.0, ns_yellow_seconds=3.0, ew_green_seconds=15.0, ew_yellow_seconds=3.0)
    )
    env = TrafficSimulationEnvironment(use_gui=False, seed=42, controller=controller)

    try:
        env.start()
        for _ in range(40):
            env.step()

        metrics = env.get_metrics()
        aggregate = env.get_aggregate_metrics()

        assert aggregate.total_simulation_steps == 40
        assert aggregate.total_vehicles_entered > 0
        assert aggregate.average_speed >= 0.0
        assert controller.phase_change_count > 0, "Fixed-time controller should have cycled phases"
    finally:
        env.close()


def test_headless_adaptive_simulation():
    """Verify AdaptiveController executes cleanly in headless SUMO simulation."""
    controller = AdaptiveController(
        config=AdaptiveConfig(min_green_seconds=10.0, max_green_seconds=30.0, yellow_seconds=3.0, pressure_difference_threshold=2)
    )
    env = TrafficSimulationEnvironment(use_gui=False, seed=42, controller=controller)

    try:
        env.start()
        for _ in range(40):
            env.step()

        metrics = env.get_metrics()
        aggregate = env.get_aggregate_metrics()

        assert aggregate.total_simulation_steps == 40
        assert aggregate.total_vehicles_entered > 0
        assert aggregate.average_queue >= 0.0
    finally:
        env.close()


def test_experiment_reproducibility():
    """Verify identical seeds and configurations produce identical aggregate metrics."""
    seed = 123
    steps = 40

    # Run 1
    c1 = FixedTimeController(config=FixedTimeConfig(ns_green_seconds=15.0, ns_yellow_seconds=3.0, ew_green_seconds=15.0, ew_yellow_seconds=3.0))
    env1 = TrafficSimulationEnvironment(use_gui=False, seed=seed, controller=c1)
    try:
        env1.start()
        for _ in range(steps):
            env1.step()
        agg1 = env1.get_aggregate_metrics()
    finally:
        env1.close()

    # Run 2
    c2 = FixedTimeController(config=FixedTimeConfig(ns_green_seconds=15.0, ns_yellow_seconds=3.0, ew_green_seconds=15.0, ew_yellow_seconds=3.0))
    env2 = TrafficSimulationEnvironment(use_gui=False, seed=seed, controller=c2)
    try:
        env2.start()
        for _ in range(steps):
            env2.step()
        agg2 = env2.get_aggregate_metrics()
    finally:
        env2.close()

    assert agg1.total_vehicles_served == agg2.total_vehicles_served
    assert agg1.total_vehicles_entered == agg2.total_vehicles_entered
    assert agg1.total_queue == agg2.total_queue if hasattr(agg1, "total_queue") else True
    assert agg1.average_queue == agg2.average_queue
    assert agg1.total_waiting_time == agg2.total_waiting_time


def test_experiment_results_json_serialization():
    """Verify experiment output serializes cleanly to JSON."""
    agg = TrafficSimulationEnvironment(use_gui=False, seed=42).get_aggregate_metrics()
    payload = {
        "run_id": "test_run_01",
        "controller": "fixed",
        "aggregate_metrics": agg.to_dict(),
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
        json.dump(payload, tmp_file, indent=2)
        tmp_path = Path(tmp_file.name)

    assert tmp_path.is_file()
    with open(tmp_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["run_id"] == "test_run_01"
    assert "average_queue" in loaded["aggregate_metrics"]
    tmp_path.unlink()
