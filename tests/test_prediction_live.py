"""Tests for Phase 3 Live Predictive Intelligence and Time-Aligned Verification."""

from __future__ import annotations

import math
import pytest
from unittest.mock import Mock, patch

from backend.schemas.traffic import PredictionLiveInfo, TrafficSnapshotResponse
from backend.services.telemetry_service import TelemetryService
from prediction.config import PredictionConfig
from prediction.live_evaluator import LiveForecastTracker, PendingForecast
from prediction.predictor import CongestionPredictor, predictor
from simulation.state import ApproachState, TrafficState, VehicleState


class TestLiveForecastTracker:
    """Unit tests for LiveForecastTracker."""

    def test_tracker_initialization(self):
        tracker = LiveForecastTracker(horizon_seconds=30.0, match_tolerance_seconds=1.0)
        assert tracker.horizon_seconds == 30.0
        assert tracker.match_tolerance_seconds == 1.0
        assert len(tracker.pending_forecasts) == 0
        assert tracker.evaluated_samples == 0

        metrics = tracker.get_metrics()
        assert metrics["evaluated_samples"] == 0
        assert metrics["live_mae"] is None
        assert metrics["live_rmse"] is None
        assert metrics["baseline_mae"] is None
        assert metrics["mae_improvement_pct"] is None

    def test_record_and_evaluate_matching(self):
        tracker = LiveForecastTracker(horizon_seconds=30.0, match_tolerance_seconds=1.0)

        # Record forecast at t=0.0 targeting t=30.0
        tracker.record_forecast(
            simulation_id="sim_test",
            step=0,
            simulation_time=0.0,
            predicted_score=25.0,
            baseline_score=10.0,
        )
        assert len(tracker.pending_forecasts) == 1

        # Evaluate at t=15.0: target is 30.0, should not match yet
        res = tracker.evaluate_step(
            simulation_id="sim_test",
            simulation_time=15.0,
            actual_score=15.0,
        )
        assert res is None
        assert tracker.evaluated_samples == 0

        # Evaluate at t=30.0: should match target_time=30.0!
        res = tracker.evaluate_step(
            simulation_id="sim_test",
            simulation_time=30.0,
            actual_score=24.0,  # actual observation
        )
        assert res is not None
        assert res["matched_issue_time"] == 0.0
        assert res["predicted_score"] == 25.0
        assert res["actual_score"] == 24.0
        assert res["model_abs_error"] == 1.0  # |25 - 24| = 1.0
        assert res["baseline_abs_error"] == 14.0  # |10 - 24| = 14.0

        assert tracker.evaluated_samples == 1
        metrics = tracker.get_metrics()
        assert metrics["evaluated_samples"] == 1
        assert metrics["live_mae"] == 1.0
        assert metrics["live_rmse"] == 1.0
        assert metrics["baseline_mae"] == 14.0
        assert metrics["mae_improvement_pct"] == round(((14.0 - 1.0) / 14.0) * 100, 1)

    def test_tracker_reset_on_new_simulation(self):
        tracker = LiveForecastTracker()
        tracker.record_forecast("sim_A", 1, 10.0, 30.0, 20.0)
        assert tracker.current_simulation_id == "sim_A"
        assert len(tracker.pending_forecasts) == 1

        # Recording for a new simulation id triggers a clean reset
        tracker.record_forecast("sim_B", 1, 5.0, 15.0, 10.0)
        assert tracker.current_simulation_id == "sim_B"
        assert len(tracker.pending_forecasts) == 1
        assert tracker.pending_forecasts[0].simulation_id == "sim_B"

    def test_stale_forecast_pruning(self):
        tracker = LiveForecastTracker(horizon_seconds=30.0, match_tolerance_seconds=1.0)
        tracker.record_forecast("sim_test", 0, 0.0, 20.0, 15.0)  # target = 30.0

        # Simulation jumps forward to t=50.0 (past target 30.0 + 5.0s tolerance)
        res = tracker.evaluate_step("sim_test", 50.0, 30.0)
        assert res is None
        # The stale forecast at target 30.0 should have been pruned
        assert len(tracker.pending_forecasts) == 0


class TestPredictLive:
    """Tests for live inference service."""

    @pytest.fixture(autouse=True)
    def setup_predictor(self):
        predictor.load_model()
        predictor.reset_live_tracker("test_sim_live")
        yield
        predictor.reset_live_tracker(None)

    def test_predict_live_produces_valid_forecast(self):
        snapshot = {
            "simulation_id": "test_sim_live",
            "simulation_time": 10.0,
            "step": 10,
            "controller": "fixed",
            "queues": {"north": 4, "south": 3, "east": 5, "west": 2, "total": 14},
            "waiting": {"average_seconds": 12.0, "total_seconds": 120.0},
            "speed": {"average_mps": 7.5},
            "signal": {"phase_index": 0, "elapsed_seconds": 15.0},
        }

        info = predictor.predict_live(
            snapshot=snapshot,
            simulation_id="test_sim_live",
            step=10,
            simulation_time=10.0,
        )

        assert isinstance(info, PredictionLiveInfo)
        assert info.model_available is True
        assert 0.0 <= info.predicted_score <= 100.0
        assert 0.0 <= info.current_score <= 100.0
        assert info.horizon_seconds == 30.0
        assert info.trend in {"INCREASING", "DECREASING", "STABLE"}

        # Empirical CI: lower <= upper
        if info.confidence_lower is not None and info.confidence_upper is not None:
            assert info.confidence_lower <= info.confidence_upper
            assert info.std_dev >= 0.0

    def test_predict_live_step_caching(self):
        snapshot = {
            "simulation_id": "test_sim_live",
            "simulation_time": 20.0,
            "step": 20,
            "controller": "fixed",
            "queues": {"north": 2, "south": 2, "east": 2, "west": 2, "total": 8},
            "waiting": {"average_seconds": 5.0, "total_seconds": 40.0},
            "speed": {"average_mps": 10.0},
            "signal": {"phase_index": 0, "elapsed_seconds": 5.0},
        }

        first_call = predictor.predict_live(
            snapshot=snapshot,
            simulation_id="test_sim_live",
            step=20,
            simulation_time=20.0,
        )

        second_call = predictor.predict_live(
            snapshot=snapshot,
            simulation_id="test_sim_live",
            step=20,
            simulation_time=20.0,
        )

        # Identical object returned from step cache without duplicate computation
        assert first_call is second_call

    def test_predict_live_fallback_on_unloaded_model(self):
        test_pred = CongestionPredictor()
        test_pred.is_loaded = False
        test_pred.model = None

        snapshot = {
            "simulation_id": "fallback_sim",
            "simulation_time": 5.0,
            "step": 5,
            "controller": "fixed",
            "queues": {"total": 10},
            "waiting": {"average_seconds": 5.0},
            "speed": {"average_mps": 8.0},
            "signal": {"phase_index": 0, "elapsed_seconds": 5.0},
        }

        # Mock load_model to return False
        with patch.object(test_pred, "load_model", return_value=False):
            info = test_pred.predict_live(
                snapshot=snapshot,
                simulation_id="fallback_sim",
                step=5,
                simulation_time=5.0,
            )

        assert isinstance(info, PredictionLiveInfo)
        assert info.model_available is False
        assert info.predicted_score == info.current_score

    def test_get_status_returns_feature_importances(self):
        status = predictor.get_status()
        assert status["model_available"] is True
        assert status["feature_count"] == 26
        assert status["prediction_horizon"] == 30.0
        assert "feature_importances" in status
        if status["feature_importances"]:
            assert isinstance(status["feature_importances"], dict)
            # Should have top features (e.g. queues, waiting time)
            assert len(status["feature_importances"]) > 0


class TestTelemetryServicePredictionIntegration:
    """Tests that TelemetryService incorporates live prediction telemetry into snapshots."""

    def test_create_snapshot_contains_prediction(self):
        state = TrafficState(
            simulation_time=15.0,
            step=15,
            current_phase=0,
            time_since_phase_change=10.0,
            north=ApproachState(direction="north", inflow_edge="N2C", queue_length=3, vehicle_count=5),
            south=ApproachState(direction="south", inflow_edge="S2C", queue_length=2, vehicle_count=4),
            east=ApproachState(direction="east", inflow_edge="E2C", queue_length=4, vehicle_count=6),
            west=ApproachState(direction="west", inflow_edge="W2C", queue_length=1, vehicle_count=3),
            total_queue=10,
            total_vehicles=18,
            average_speed=8.5,
            total_waiting_time=65.0,
            vehicles=[],
        )

        snapshot = TelemetryService.create_snapshot(
            state=state,
            metrics=None,
            controller=None,
            simulation_id="test_sim_telemetry",
            peak_queue=12,
        )

        assert isinstance(snapshot, TrafficSnapshotResponse)
        assert snapshot.prediction is not None
        assert isinstance(snapshot.prediction, PredictionLiveInfo)
        assert snapshot.prediction.horizon_seconds == 30.0
        assert snapshot.prediction.trend in {"INCREASING", "DECREASING", "STABLE"}

        # Verify serialization for WebSocket JSON payloads
        dumped = snapshot.model_dump()
        assert "prediction" in dumped
        assert dumped["prediction"]["horizon_seconds"] == 30.0
