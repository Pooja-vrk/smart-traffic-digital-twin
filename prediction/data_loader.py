"""Data loader for historical traffic data from MongoDB."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pymongo

from backend.database.connection import db_manager
from prediction.config import PredictionConfig
from prediction.feature_engineering import extract_features, get_feature_names, prepare_feature_vector
from prediction.target_builder import create_training_pairs_for_simulation

logger = logging.getLogger(__name__)


class DatasetStatistics:
    """Statistics about the loaded dataset."""

    def __init__(
        self,
        num_simulation_runs: int,
        num_snapshots: int,
        num_training_samples: int,
        time_coverage: Tuple[float, float],
        controller_distribution: Dict[str, int],
        missing_values: Dict[str, int],
        feature_count: int,
        target_distribution: Dict[str, int],
    ):
        self.num_simulation_runs = num_simulation_runs
        self.num_snapshots = num_snapshots
        self.num_training_samples = num_training_samples
        self.time_coverage = time_coverage
        self.controller_distribution = controller_distribution
        self.missing_values = missing_values
        self.feature_count = feature_count
        self.target_distribution = target_distribution

    def to_dict(self) -> Dict:
        """Convert statistics to dictionary."""
        return {
            "num_simulation_runs": self.num_simulation_runs,
            "num_snapshots": self.num_snapshots,
            "num_training_samples": self.num_training_samples,
            "time_coverage": {
                "min_seconds": self.time_coverage[0],
                "max_seconds": self.time_coverage[1],
            },
            "controller_distribution": self.controller_distribution,
            "missing_values": self.missing_values,
            "feature_count": self.feature_count,
            "target_distribution": self.target_distribution,
        }


class DataLoader:
    """Loads and prepares historical traffic data for prediction training."""

    def __init__(self):
        self._snapshots_by_simulation: Dict[str, List[Dict]] = {}
        self._statistics: Optional[DatasetStatistics] = None

    def load_historical_data(
        self,
        status: str = "completed",
        limit_simulations: Optional[int] = None,
    ) -> DatasetStatistics:
        """
        Load historical traffic snapshots from MongoDB.

        Args:
            status: Filter simulation runs by status (default: "completed").
            limit_simulations: Maximum number of simulation runs to load (None = all).

        Returns:
            DatasetStatistics object with information about loaded data.

        Raises:
            RuntimeError: If MongoDB is unavailable or no data found.
        """
        if not db_manager.is_available or db_manager.sync_db is None:
            raise RuntimeError("MongoDB is not available. Cannot load historical data.")

        logger.info("Loading historical traffic data from MongoDB...")

        # Get simulation runs
        query = {"status": status}
        simulation_runs = list(
            db_manager.sync_db.simulation_runs.find(
                query,
                {"_id": 0, "simulation_id": 1, "controller": 1},
            )
            .sort([("started_at", pymongo.DESCENDING)])
            .limit(limit_simulations or 1000)
        )

        if not simulation_runs:
            raise RuntimeError(f"No simulation runs found with status '{status}'")

        logger.info("Found %d simulation runs", len(simulation_runs))

        # Load snapshots for each simulation
        total_snapshots = 0
        controller_counts: Dict[str, int] = {}
        time_min = float("inf")
        time_max = float("-inf")

        for run in simulation_runs:
            sim_id = run["simulation_id"]
            controller = run.get("controller", "unknown")
            controller_counts[controller] = controller_counts.get(controller, 0) + 1

            snapshots = list(
                db_manager.sync_db.traffic_snapshots.find(
                    {"simulation_id": sim_id},
                    {"_id": 0},
                )
                .sort([("simulation_time", pymongo.ASCENDING)])
            )

            if snapshots:
                self._snapshots_by_simulation[sim_id] = snapshots
                total_snapshots += len(snapshots)

                # Track time coverage
                for snap in snapshots:
                    sim_time = snap.get("simulation_time", 0.0)
                    time_min = min(time_min, sim_time)
                    time_max = max(time_max, sim_time)

        if total_snapshots == 0:
            raise RuntimeError("No traffic snapshots found in MongoDB")

        logger.info(
            "Loaded %d snapshots from %d simulation runs",
            total_snapshots,
            len(self._snapshots_by_simulation)
        )

        # Build training pairs
        training_pairs = self._build_training_pairs()

        # Calculate target distribution
        target_distribution = self._calculate_target_distribution(training_pairs)

        # Store statistics
        self._statistics = DatasetStatistics(
            num_simulation_runs=len(self._snapshots_by_simulation),
            num_snapshots=total_snapshots,
            num_training_samples=len(training_pairs),
            time_coverage=(time_min, time_max),
            controller_distribution=controller_counts,
            missing_values={},  # TODO: Implement missing value tracking
            feature_count=len(get_feature_names()),
            target_distribution=target_distribution,
        )

        return self._statistics

    def _build_training_pairs(self) -> List[Tuple[Dict, float]]:
        """Build training pairs from loaded snapshots."""
        all_pairs = []

        for sim_id, snapshots in self._snapshots_by_simulation.items():
            pairs = create_training_pairs_for_simulation(snapshots)
            all_pairs.extend([(snap, target) for snap, target in pairs])

        logger.info("Built %d total training pairs", len(all_pairs))
        return all_pairs

    def _calculate_target_distribution(self, training_pairs: List[Tuple[Dict, float]]) -> Dict[str, int]:
        """Calculate distribution of target congestion scores."""
        from prediction.congestion import classify_congestion

        distribution = {
            "FREE_FLOW": 0,
            "LOW": 0,
            "MODERATE": 0,
            "HIGH": 0,
            "SEVERE": 0,
        }

        for _, target_score in training_pairs:
            level = classify_congestion(target_score)
            distribution[level] = distribution.get(level, 0) + 1

        return distribution

    def check_data_sufficiency(self) -> Tuple[bool, str]:
        """
        Check if sufficient data is available for training.

        Returns:
            Tuple of (is_sufficient, message).
        """
        if self._statistics is None:
            return False, "No statistics available. Data not loaded."

        stats = self._statistics

        checks = [
            (stats.num_simulation_runs >= PredictionConfig.MIN_SIMULATION_RUNS,
             f"Need at least {PredictionConfig.MIN_SIMULATION_RUNS} simulation runs, have {stats.num_simulation_runs}"),
            (stats.num_snapshots >= PredictionConfig.MIN_SNAPSHOTS,
             f"Need at least {PredictionConfig.MIN_SNAPSHOTS} snapshots, have {stats.num_snapshots}"),
            (stats.num_training_samples >= PredictionConfig.MIN_TRAINING_SAMPLES,
             f"Need at least {PredictionConfig.MIN_TRAINING_SAMPLES} training samples, have {stats.num_training_samples}"),
        ]

        failed_checks = [msg for passed, msg in checks if not passed]

        if failed_checks:
            return False, "; ".join(failed_checks)

        return True, "Data sufficiency checks passed"

    def prepare_dataset(
        self,
        random_state: int = None,
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Prepare feature matrix and target vector for training.

        Args:
            random_state: Random seed for train/test split (uses config default if None).

        Returns:
            Tuple of (X, y, feature_names) where:
                X: Feature matrix (n_samples, n_features)
                y: Target vector (n_samples,)
                feature_names: List of feature names

        Raises:
            RuntimeError: If data is insufficient or not loaded.
        """
        if random_state is None:
            random_state = PredictionConfig.RANDOM_STATE

        # Check data sufficiency
        is_sufficient, message = self.check_data_sufficiency()
        if not is_sufficient:
            raise RuntimeError(f"Insufficient training data: {message}")

        # Build training pairs
        training_pairs = self._build_training_pairs()

        # Group by simulation ID for proper splitting
        pairs_by_simulation: Dict[str, List[Tuple[Dict, float]]] = {}
        for snap, target in training_pairs:
            sim_id = snap.get("simulation_id", "unknown")
            if sim_id not in pairs_by_simulation:
                pairs_by_simulation[sim_id] = []
            pairs_by_simulation[sim_id].append((snap, target))

        # Split simulations into train/validation/test
        sim_ids = list(pairs_by_simulation.keys())
        np.random.seed(random_state)
        np.random.shuffle(sim_ids)

        n_sims = len(sim_ids)
        n_train = int(n_sims * PredictionConfig.TRAIN_RATIO)
        n_val = int(n_sims * PredictionConfig.VALIDATION_RATIO)

        train_sims = sim_ids[:n_train]
        val_sims = sim_ids[n_train:n_train + n_val]
        test_sims = sim_ids[n_train + n_val:]

        logger.info(
            "Split %d simulations: %d train, %d validation, %d test",
            n_sims, len(train_sims), len(val_sims), len(test_sims)
        )

        # Extract features and targets for training set
        X_train, y_train = self._extract_features_targets(pairs_by_simulation, train_sims)
        X_val, y_val = self._extract_features_targets(pairs_by_simulation, val_sims)
        X_test, y_test = self._extract_features_targets(pairs_by_simulation, test_sims)

        # Combine train and validation for final training
        X = np.vstack([X_train, X_val])
        y = np.concatenate([y_train, y_val])

        logger.info(
            "Final dataset: %d training samples, %d test samples",
            len(X), len(X_test)
        )

        # Store test set for evaluation
        self._X_test = X_test
        self._y_test = y_test

        return X, y, get_feature_names()

    def _extract_features_targets(
        self,
        pairs_by_simulation: Dict[str, List[Tuple[Dict, float]]],
        sim_ids: List[str],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Extract features and targets for specified simulations."""
        features_list = []
        targets_list = []

        for sim_id in sim_ids:
            if sim_id not in pairs_by_simulation:
                continue

            # Get all snapshots for this simulation for historical context
            all_snapshots = self._snapshots_by_simulation.get(sim_id, [])
            sorted_snapshots = sorted(all_snapshots, key=lambda s: s.get("simulation_time", 0.0))

            for snap, target in pairs_by_simulation[sim_id]:
                # Find historical snapshots before current time
                current_time = snap.get("simulation_time", 0.0)
                historical = [s for s in sorted_snapshots if s.get("simulation_time", 0.0) < current_time]

                # Extract features with historical context
                features = extract_features(snap, historical_snapshots=historical)
                feature_vector = prepare_feature_vector(features)

                features_list.append(feature_vector)
                targets_list.append(target)

        if not features_list:
            return np.array([]), np.array([])

        return np.array(features_list), np.array(targets_list)

    def get_test_set(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Return the held-out test set for evaluation."""
        if hasattr(self, '_X_test') and hasattr(self, '_y_test'):
            return self._X_test, self._y_test
        return None

    def get_statistics(self) -> Optional[DatasetStatistics]:
        """Return dataset statistics."""
        return self._statistics
