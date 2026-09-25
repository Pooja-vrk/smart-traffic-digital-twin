"""Unit and integration tests for congestion prediction module."""

from __future__ import annotations

import pytest
import numpy as np
import pymongo
from unittest.mock import Mock, patch, MagicMock

from prediction.config import PredictionConfig
from prediction.congestion import build_congestion_score, classify_congestion
from prediction.feature_engineering import (
    extract_features,
    get_feature_names,
    prepare_feature_vector,
    validate_no_future_leakage,
)
from prediction.target_builder import (
    create_training_pair,
    create_training_pairs_for_simulation,
    find_future_snapshot,
)
from prediction.model import BaselinePredictor, CongestionPredictionModel
from prediction.metrics import (
    calculate_classification_accuracy,
    calculate_regression_metrics,
    evaluate_predictions,
)
from prediction.predictor import CongestionPredictor, FeatureMetadata


class TestCongestionScore:
    """Tests for congestion score calculation."""

    def test_build_congestion_score_basic(self):
        """Test basic congestion score calculation."""
        snapshot = {
            "queues": {
                "north": 5,
                "south": 3,
                "east": 7,
                "west": 2,
                "total": 17,
            },
            "waiting": {"average_seconds": 15.0},
            "speed": {"average_mps": 8.0},
        }
        score = build_congestion_score(snapshot)
        assert 0 <= score <= 100
        assert isinstance(score, float)

    def test_build_congestion_score_max_queue(self):
        """Test congestion score with maximum queue."""
        snapshot = {
            "queues": {
                "north": 30,
                "south": 30,
                "east": 30,
                "west": 30,
                "total": 120,
            },
            "waiting": {"average_seconds": 120.0},
            "speed": {"average_mps": 0.0},
        }
        score = build_congestion_score(snapshot)
        assert score > 80  # Should be high congestion

    def test_build_congestion_score_free_flow(self):
        """Test congestion score with free flow conditions."""
        snapshot = {
            "queues": {
                "north": 0,
                "south": 0,
                "east": 0,
                "west": 0,
                "total": 0,
            },
            "waiting": {"average_seconds": 0.0},
            "speed": {"average_mps": 15.0},
        }
        score = build_congestion_score(snapshot)
        assert score < 20  # Should be free flow

    def test_build_congestion_score_invalid_negative(self):
        """Test that negative values raise ValueError."""
        snapshot = {
            "queues": {"north": -5, "south": 0, "east": 0, "west": 0, "total": -5},
            "waiting": {"average_seconds": 0.0},
            "speed": {"average_mps": 10.0},
        }
        with pytest.raises(ValueError):
            build_congestion_score(snapshot)


class TestCongestionClassification:
    """Tests for congestion level classification."""

    def test_classify_free_flow(self):
        """Test FREE_FLOW classification."""
        assert classify_congestion(10) == "FREE_FLOW"
        assert classify_congestion(20) == "FREE_FLOW"

    def test_classify_low(self):
        """Test LOW classification."""
        assert classify_congestion(21) == "LOW"
        assert classify_congestion(30) == "LOW"
        assert classify_congestion(40) == "LOW"

    def test_classify_moderate(self):
        """Test MODERATE classification."""
        assert classify_congestion(41) == "MODERATE"
        assert classify_congestion(50) == "MODERATE"
        assert classify_congestion(60) == "MODERATE"

    def test_classify_high(self):
        """Test HIGH classification."""
        assert classify_congestion(61) == "HIGH"
        assert classify_congestion(70) == "HIGH"
        assert classify_congestion(80) == "HIGH"

    def test_classify_severe(self):
        """Test SEVERE classification."""
        assert classify_congestion(81) == "SEVERE"
        assert classify_congestion(90) == "SEVERE"
        assert classify_congestion(100) == "SEVERE"

    def test_classify_invalid_range(self):
        """Test that out-of-range scores raise ValueError."""
        with pytest.raises(ValueError):
            classify_congestion(-1)
        with pytest.raises(ValueError):
            classify_congestion(101)


class TestFeatureEngineering:
    """Tests for feature engineering."""

    def test_extract_basic_features(self):
        """Test extraction of basic features."""
        snapshot = {
            "queues": {"north": 5, "south": 3, "east": 7, "west": 2, "total": 17},
            "waiting": {"average_seconds": 15.0},
            "speed": {"average_mps": 8.0},
            "signal": {"phase_index": 0, "elapsed_seconds": 10.0},
            "controller": "adaptive",
            "simulation_time": 100.0,
        }
        features = extract_features(snapshot)

        assert "north_queue" in features
        assert "south_queue" in features
        assert "east_queue" in features
        assert "west_queue" in features
        assert "total_queue" in features
        assert "max_queue" in features
        assert "average_queue" in features
        assert "queue_imbalance" in features
        assert "average_waiting_time" in features
        assert "average_speed" in features
        assert "phase_index" in features
        assert "elapsed_green" in features
        assert "controller_fixed" in features
        assert "controller_adaptive" in features
        assert "controller_dqn" in features
        assert "simulation_time" in features

        assert features["total_queue"] == 17.0
        assert features["controller_adaptive"] == 1.0
        assert features["controller_fixed"] == 0.0

    def test_extract_features_with_lag(self):
        """Test extraction with historical lag features."""
        snapshot = {
            "queues": {"north": 5, "south": 3, "east": 7, "west": 2, "total": 17},
            "waiting": {"average_seconds": 15.0},
            "speed": {"average_mps": 8.0},
            "signal": {"phase_index": 0, "elapsed_seconds": 10.0},
            "controller": "adaptive",
            "simulation_time": 100.0,
        }

        historical = [
            {
                "queues": {"total": 15},
                "speed": {"average_mps": 9.0},
                "simulation_time": 99.0,
            },
            {
                "queues": {"total": 13},
                "speed": {"average_mps": 10.0},
                "simulation_time": 98.0,
            },
        ]

        features = extract_features(snapshot, historical_snapshots=historical)

        # Check lag features are present
        assert "queue_total_lag_1" in features
        assert "speed_lag_1" in features

    def test_get_feature_names(self):
        """Test that feature names are consistent."""
        names = get_feature_names()
        assert isinstance(names, list)
        assert len(names) > 0
        assert "total_queue" in names
        assert "average_speed" in names

    def test_prepare_feature_vector(self):
        """Test conversion of features to vector."""
        snapshot = {
            "queues": {"north": 5, "south": 3, "east": 7, "west": 2, "total": 17},
            "waiting": {"average_seconds": 15.0},
            "speed": {"average_mps": 8.0},
            "signal": {"phase_index": 0, "elapsed_seconds": 10.0},
            "controller": "adaptive",
            "simulation_time": 100.0,
        }
        features = extract_features(snapshot)
        vector = prepare_feature_vector(features)

        assert isinstance(vector, np.ndarray)
        assert vector.dtype == np.float32
        assert len(vector) == len(get_feature_names())

    def test_prepare_feature_vector_missing_feature(self):
        """Test that missing features raise ValueError."""
        features = {"total_queue": 10.0}  # Missing many required features
        with pytest.raises(ValueError, match="Missing required feature"):
            prepare_feature_vector(features)

    def test_validate_no_future_leakage(self):
        """Test validation for future data leakage."""
        snapshot = {
            "queues": {"north": 5, "south": 3, "east": 7, "west": 2, "total": 17},
            "waiting": {"average_seconds": 15.0},
            "speed": {"average_mps": 8.0},
            "signal": {"phase_index": 0, "elapsed_seconds": 10.0},
            "controller": "adaptive",
            "simulation_time": 100.0,
        }
        features = extract_features(snapshot)

        # Should pass validation
        assert validate_no_future_leakage(features, 100.0) is True

        # Should fail if simulation_time doesn't match
        features["simulation_time"] = 200.0
        assert validate_no_future_leakage(features, 100.0) is False


class TestTargetBuilder:
    """Tests for future target construction."""

    def test_find_future_snapshot_exact(self):
        """Test finding future snapshot at exact target time."""
        snapshots = [
            {"simulation_time": 0.0},
            {"simulation_time": 30.0},
            {"simulation_time": 60.0},
        ]
        future = find_future_snapshot(snapshots, 0.0, 30.0, 5.0)
        assert future is not None
        assert future["simulation_time"] == 30.0

    def test_find_future_snapshot_within_tolerance(self):
        """Test finding future snapshot within tolerance."""
        snapshots = [
            {"simulation_time": 0.0},
            {"simulation_time": 32.0},  # 2 seconds off from 30
        ]
        future = find_future_snapshot(snapshots, 0.0, 30.0, 5.0)
        assert future is not None
        assert future["simulation_time"] == 32.0

    def test_find_future_snapshot_beyond_tolerance(self):
        """Test that snapshots beyond tolerance are rejected."""
        snapshots = [
            {"simulation_time": 0.0},
            {"simulation_time": 40.0},  # 10 seconds off from 30
        ]
        future = find_future_snapshot(snapshots, 0.0, 30.0, 5.0)
        assert future is None

    def test_find_future_snapshot_none_available(self):
        """Test when no future snapshot is available."""
        snapshots = [{"simulation_time": 0.0}]
        future = find_future_snapshot(snapshots, 0.0, 30.0, 5.0)
        assert future is None

    def test_create_training_pair_success(self):
        """Test successful creation of training pair."""
        current = {
            "simulation_time": 0.0,
            "queues": {"total": 10},
            "waiting": {"average_seconds": 5.0},
            "speed": {"average_mps": 10.0},
        }
        all_snapshots = [
            current,
            {
                "simulation_time": 30.0,
                "queues": {"total": 15},
                "waiting": {"average_seconds": 8.0},
                "speed": {"average_mps": 8.0},
            },
        ]

        pair = create_training_pair(current, all_snapshots, 30.0, 5.0)
        assert pair is not None
        snapshot, target = pair
        assert snapshot == current
        assert 0 <= target <= 100

    def test_create_training_pair_no_future(self):
        """Test training pair creation when no future snapshot exists."""
        current = {"simulation_time": 0.0, "queues": {"total": 10}}
        all_snapshots = [current]

        pair = create_training_pair(current, all_snapshots, 30.0, 5.0)
        assert pair is None

    def test_create_training_pairs_for_simulation(self):
        """Test creating multiple training pairs for a simulation."""
        snapshots = [
            {"simulation_time": 0.0, "queues": {"total": 10}, "waiting": {"average_seconds": 5.0}, "speed": {"average_mps": 10.0}},
            {"simulation_time": 30.0, "queues": {"total": 15}, "waiting": {"average_seconds": 8.0}, "speed": {"average_mps": 8.0}},
            {"simulation_time": 60.0, "queues": {"total": 20}, "waiting": {"average_seconds": 12.0}, "speed": {"average_mps": 6.0}},
        ]

        pairs = create_training_pairs_for_simulation(snapshots, 30.0, 5.0)
        assert len(pairs) > 0
        # First snapshot should have a pair
        assert pairs[0][0]["simulation_time"] == 0.0


class TestModel:
    """Tests for ML model."""

    def test_model_initialization(self):
        """Test model initialization."""
        model = CongestionPredictionModel()
        assert model is not None
        assert not model.is_trained

    def test_model_training(self):
        """Test model training."""
        model = CongestionPredictionModel(n_estimators=10, max_depth=5, random_state=42)

        # Create dummy data
        X = np.random.rand(100, len(get_feature_names())).astype(np.float32)
        y = np.random.rand(100) * 100

        feature_names = get_feature_names()
        model.train(X, y, feature_names)

        assert model.is_trained
        assert model.feature_names == feature_names

    def test_model_prediction(self):
        """Test model prediction."""
        model = CongestionPredictionModel(n_estimators=10, max_depth=5, random_state=42)

        X_train = np.random.rand(100, len(get_feature_names())).astype(np.float32)
        y_train = np.random.rand(100) * 100
        model.train(X_train, y_train, get_feature_names())

        X_test = np.random.rand(10, len(get_feature_names())).astype(np.float32)
        predictions = model.predict(X_test)

        assert len(predictions) == 10
        assert all(0 <= p <= 100 for p in predictions)

    def test_model_prediction_untrained(self):
        """Test that prediction fails on untrained model."""
        model = CongestionPredictionModel()
        X = np.random.rand(10, len(get_feature_names())).astype(np.float32)

        with pytest.raises(RuntimeError, match="Model must be trained"):
            model.predict(X)

    def test_model_feature_importance(self):
        """Test getting feature importance."""
        model = CongestionPredictionModel(n_estimators=10, max_depth=5, random_state=42)

        X = np.random.rand(100, len(get_feature_names())).astype(np.float32)
        y = np.random.rand(100) * 100
        model.train(X, y, get_feature_names())

        importance = model.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) == len(get_feature_names())

    def test_baseline_predictor(self):
        """Test baseline predictor."""
        baseline = BaselinePredictor()

        # Features with current_congestion_score as last feature
        X = np.array([[1.0, 2.0, 3.0, 50.0], [1.0, 2.0, 3.0, 75.0]])

        predictions = baseline.predict(X)

        assert len(predictions) == 2
        assert predictions[0] == 50.0
        assert predictions[1] == 75.0


class TestMetrics:
    """Tests for evaluation metrics."""

    def test_regression_metrics(self):
        """Test regression metric calculation."""
        y_true = np.array([10.0, 20.0, 30.0, 40.0])
        y_pred = np.array([12.0, 18.0, 32.0, 38.0])

        metrics = calculate_regression_metrics(y_true, y_pred)

        assert "mae" in metrics
        assert "rmse" in metrics
        assert "r2" in metrics
        assert metrics["mae"] >= 0
        assert metrics["rmse"] >= 0

    def test_classification_accuracy(self):
        """Test classification accuracy calculation."""
        y_true = np.array([10.0, 30.0, 50.0, 70.0, 90.0])
        y_pred = np.array([12.0, 28.0, 52.0, 68.0, 88.0])

        accuracy = calculate_classification_accuracy(y_true, y_pred)

        assert 0 <= accuracy <= 1
        assert accuracy > 0.5  # Should be reasonably accurate

    def test_evaluate_predictions(self):
        """Test full evaluation pipeline."""
        y_true = np.array([10.0, 20.0, 30.0, 40.0])
        y_pred_ml = np.array([12.0, 18.0, 32.0, 38.0])
        y_pred_baseline = np.array([10.0, 20.0, 30.0, 40.0])  # Perfect baseline

        metrics = evaluate_predictions(y_true, y_pred_ml, y_pred_baseline)

        assert metrics.mae >= 0
        assert metrics.rmse >= 0
        assert metrics.baseline_mae >= 0
        assert metrics.baseline_rmse >= 0


class TestPredictor:
    """Tests for predictor service."""

    def test_predictor_initialization(self):
        """Test predictor initialization."""
        predictor = CongestionPredictor()
        assert not predictor.is_loaded
        assert predictor.model is None

    def test_predictor_status(self):
        """Test predictor status."""
        predictor = CongestionPredictor()
        status = predictor.get_status()

        assert "model_available" in status
        assert status["model_available"] is False

    def test_predict_without_model(self):
        """Test that prediction fails without loaded model."""
        predictor = CongestionPredictor()
        snapshot = {
            "queues": {"total": 10},
            "waiting": {"average_seconds": 5.0},
            "speed": {"average_mps": 10.0},
        }

        with pytest.raises(RuntimeError, match="Model is not loaded"):
            predictor.predict(snapshot)

    @patch("prediction.predictor.joblib.load")
    @patch("prediction.predictor.Path.exists")
    def test_predictor_load_model(self, mock_exists, mock_load):
        """Test model loading."""
        mock_exists.return_value = True
        mock_load.return_value = Mock()

        predictor = CongestionPredictor()
        with patch("builtins.open", create=True) as mock_open:
            import json
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                "feature_names": get_feature_names(),
                "feature_version": "1.0",
                "target_definition": "congestion_score_0_100",
                "prediction_horizon": 30.0,
                "model_name": "RandomForestRegressor",
                "model_parameters": {},
                "training_timestamp": "2024-01-01T00:00:00Z",
                "dataset_size": 100,
                "random_seed": 42,
            })

            success = predictor.load_model()
            assert success is True


class TestFeatureMetadata:
    """Tests for feature metadata."""

    def test_feature_metadata_to_dict(self):
        """Test metadata serialization."""
        metadata = FeatureMetadata(
            feature_names=["a", "b", "c"],
            feature_version="1.0",
            target_definition="test",
            prediction_horizon=30.0,
            model_name="TestModel",
            model_parameters={},
            training_timestamp="2024-01-01T00:00:00Z",
            dataset_size=100,
            random_seed=42,
        )

        data = metadata.to_dict()
        assert data["feature_names"] == ["a", "b", "c"]
        assert data["feature_version"] == "1.0"

    def test_feature_metadata_from_dict(self):
        """Test metadata deserialization."""
        data = {
            "feature_names": ["a", "b", "c"],
            "feature_version": "1.0",
            "target_definition": "test",
            "prediction_horizon": 30.0,
            "model_name": "TestModel",
            "model_parameters": {},
            "training_timestamp": "2024-01-01T00:00:00Z",
            "dataset_size": 100,
            "random_seed": 42,
        }

        metadata = FeatureMetadata.from_dict(data)
        assert metadata.feature_names == ["a", "b", "c"]
        assert metadata.feature_version == "1.0"


class TestDataLeakagePrevention:
    """Tests for data leakage prevention."""

    def test_no_future_queue_in_features(self):
        """Test that future queue values are not in features."""
        snapshot = {
            "queues": {"total": 10},
            "waiting": {"average_seconds": 5.0},
            "speed": {"average_mps": 10.0},
            "simulation_time": 100.0,
        }

        features = extract_features(snapshot)

        # Ensure no future time information
        assert features["simulation_time"] == 100.0

        # No negative lags (which would indicate future data)
        for key, value in features.items():
            if "lag" in key:
                assert value >= 0, f"Negative lag value detected: {key}={value}"


class TestInsufficientDataHandling:
    """Tests for handling insufficient data scenarios."""

    @patch("prediction.data_loader.db_manager")
    def test_data_loader_no_mongodb(self, mock_db_manager):
        """Test data loader when MongoDB is unavailable."""
        mock_db_manager.is_available = False

        from prediction.data_loader import DataLoader

        loader = DataLoader()
        with pytest.raises(RuntimeError, match="MongoDB is not available"):
            loader.load_historical_data()

    @patch("prediction.data_loader.db_manager")
    def test_data_loader_no_simulation_runs(self, mock_db_manager):
        """Test data loader when no simulation runs exist."""
        mock_db_manager.is_available = True
        mock_db_manager.sync_db = Mock()
        # Mock the find() and sort() chain
        mock_cursor = Mock()
        mock_cursor.sort.return_value.limit.return_value = []
        mock_db_manager.sync_db.simulation_runs.find.return_value = mock_cursor

        from prediction.data_loader import DataLoader

        loader = DataLoader()
        with pytest.raises(RuntimeError, match="No simulation runs found"):
            loader.load_historical_data()


class TestConfiguration:
    """Tests for configuration settings."""

    def test_prediction_horizon(self):
        """Test prediction horizon configuration."""
        assert PredictionConfig.PREDICTION_HORIZON_SECONDS == 30.0

    def test_congestion_thresholds(self):
        """Test congestion threshold configuration."""
        thresholds = PredictionConfig.CONGESTION_THRESHOLDS
        assert thresholds["FREE_FLOW"] == 20
        assert thresholds["SEVERE"] == 100

    def test_data_sufficiency_thresholds(self):
        """Test data sufficiency thresholds."""
        assert PredictionConfig.MIN_SIMULATION_RUNS >= 1
        assert PredictionConfig.MIN_SNAPSHOTS >= 1
        assert PredictionConfig.MIN_TRAINING_SAMPLES >= 1

    def test_train_test_split_ratios(self):
        """Test train/test split ratios sum to 1.0."""
        total = (
            PredictionConfig.TRAIN_RATIO +
            PredictionConfig.VALIDATION_RATIO +
            PredictionConfig.TEST_RATIO
        )
        assert abs(total - 1.0) < 0.01
