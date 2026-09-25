# Database Design Document

## 1. Overview
The digital twin utilizes MongoDB (via Motor for async and PyMongo for sync operations) for high-throughput time-series telemetry storage, simulation run metadata, signal decision records, intersection topological profiles, and comparative analytics.

The database layer is designed with strict **failure isolation**: if MongoDB is unreachable or temporarily degraded, the micro-simulation engine (SUMO + TraCI) and WebSocket broadcast engine continue running uninterrupted.

---

## 2. Collections Schema Specification

### 2.1. `intersections`
Stores topological profiles, approach lane geometries, signal phase definitions, and hardware configuration for managed traffic junctions.

- `intersection_id` (String, Unique): Primary identifier (e.g., `"INT-001"`).
- `name` (String): Human-readable name (e.g., `"Main Street 4-Way Intersection"`).
- `type` (String): Topology type (`"4-way"`, `"3-way"`, etc.).
- `tls_id` (String): SUMO Traffic Light System ID (e.g., `"J1"`).
- `lanes` (Array of Objects):
  - `lane_id` (String): SUMO lane ID (e.g., `"N_in_0"`).
  - `direction` (String): Direction tag (`"north"`, `"south"`, `"east"`, `"west"`).
  - `type` (String): `"incoming"` or `"outgoing"`.
  - `length_m` (Number): Lane length in meters.
  - `speed_limit_mps` (Number): Maximum speed limit.
- `phases` (Array of Objects):
  - `index` (Number): Phase index (0–3).
  - `name` (String): e.g., `"NORTH_SOUTH_GREEN"`, `"NORTH_SOUTH_YELLOW"`.
  - `state` (String): TraCI light state string (e.g., `"GGggrrrrGGggrrrr"`).
  - `type` (String): `"green"` or `"yellow"`.
- `created_at` (ISODate): Creation timestamp.
- `updated_at` (ISODate): Last modification timestamp.

**Indexes**:
- `intersection_id` (Unique)

---

### 2.2. `simulation_runs`
Stores metadata, configuration, runtime lifecycle status, and aggregate traffic performance metrics for each simulation run.

- `simulation_id` (String, Unique): 8-character hex run identifier (e.g., `"e83b190f"`).
- `intersection_id` (String): Reference to intersection (e.g., `"INT-001"`).
- `controller` (String): Controller algorithm (`"dqn"`, `"adaptive"`, `"fixed"`).
- `controller_name` (String): Display name (e.g., `"DQN-ReinforcementLearning"`).
- `steps` (Number): Planned simulation step count.
- `seed` (Number): Deterministic random seed used.
- `status` (String): Lifecycle state (`"running"`, `"completed"`, `"stopped"`, `"failed"`).
- `started_at` (ISODate): Execution start timestamp.
- `completed_at` (ISODate | null): Execution end timestamp.
- `duration_seconds` (Number | null): Total wall-clock execution time.
- `metrics` (Object | null): Final aggregated traffic performance metrics:
  - `total_simulation_steps` (Number): Total simulation ticks executed.
  - `total_simulation_time` (Number): Simulation time in seconds.
  - `total_vehicles_served` (Number): Total completed trips.
  - `total_vehicles_entered` (Number): Total vehicles spawned.
  - `average_queue` (Number): Mean intersection queue across all approaches.
  - `max_queue` (Number): Maximum instantaneous queue observed.
  - `average_waiting_time` (Number): Mean accumulated vehicle waiting time (seconds).
  - `total_waiting_time` (Number): Cumulative vehicle waiting time.
  - `average_speed` (Number): Mean velocity (m/s).
  - `average_delay` (Number): Mean delay vs free-flow travel time.
  - `phase_changes` (Number): Total number of signal phase transitions.
  - `total_co2_emission_kg` (Number): Cumulative estimated CO2 output.
- `error` (String | null): Error message if run failed.

**Indexes**:
- `simulation_id` (Unique)
- `controller` + `completed_at` (Compound)
- `status` (Single field)

---

### 2.3. `traffic_snapshots`
Stores time-series snapshots of spatial traffic density, queue lengths, velocities, and delay metrics recorded at regular simulation intervals.

- `simulation_id` (String): Foreign reference to `simulation_runs`.
- `intersection_id` (String): Intersection identifier (`"INT-001"`).
- `step` (Number): Discrete simulation step.
- `simulation_time` (Number): Simulation elapsed seconds.
- `timestamp` (ISODate): Wall-clock timestamp.
- `controller` (String): Active controller name.
- `vehicles` (Object):
  - `total` (Number): Active vehicles in intersection.
  - `entered` (Number): Cumulative entered count.
  - `completed` (Number): Cumulative completed count.
- `queues` (Object):
  - `north`, `south`, `east`, `west` (Number): Lane-level queue lengths.
  - `total` (Number): Instantaneous sum of all queues.
  - `peak` (Number): Peak queue observed so far.
- `speed` (Object):
  - `average_mps` (Number): Mean speed across all active vehicles.
- `waiting` (Object):
  - `average_seconds` (Number): Mean waiting time of current active vehicles.
  - `total_seconds` (Number): Total waiting time.
- `signal` (Object):
  - `phase_index` (Number): Active phase index.
  - `phase_name` (String): Active phase name.
  - `state` (String): TraCI signal state character string.
  - `elapsed_seconds` (Number): Active green/yellow duration.
- `ai` (Object):
  - `action` (String): Action name (`"KEEP"`, `"SWITCH_NS"`, `"SWITCH_EW"`).
  - `action_id` (Number): Action index (0, 1, 2).
  - `requested_phase` (Number): Target phase requested by agent.
  - `approved` (Boolean): Safety manager compliance status.
  - `reason` (String): Decision rationale.

**Indexes**:
- `simulation_id` + `simulation_time` (Compound)
- `simulation_id` + `timestamp` (Compound)

---

### 2.4. `signal_decisions`
Stores discrete audit records for every signal change decision evaluated by Fixed-Time, Rule-Based Adaptive, or DQN controllers.

- `simulation_id` (String): Foreign reference to `simulation_runs`.
- `intersection_id` (String): Intersection identifier.
- `step` (Number): Simulation step index.
- `simulation_time` (Number): Simulation time in seconds.
- `timestamp` (ISODate): Record timestamp.
- `controller` (String): Algorithm making the decision.
- `current_phase` (Number): Phase index prior to decision.
- `action` (String): Action evaluated (`"KEEP"`, `"SWITCH_NS"`, `"SWITCH_EW"`).
- `action_id` (Number): Action integer code.
- `requested_phase` (Number): Requested target phase.
- `approved` (Boolean): Whether `SignalSafetyManager` authorized the transition.
- `reason` (String): Textual justification (e.g., minimum green violated, DQN policy, pressure actuated).
- `state_vector` (Array of Numbers | null): Normalized 6-dimensional input vector for DQN.
- `q_values` (Array of Numbers | null): Predicted Q-values across actions (if DQN).

**Indexes**:
- `simulation_id` + `simulation_time` (Compound)

---

### 2.5. `congestion_predictions`
Stores congestion prediction results generated by the ML prediction service.

- `prediction_id` (String, Unique): Primary identifier for the prediction.
- `simulation_id` (String): Reference to simulation run (if applicable).
- `intersection_id` (String): Intersection identifier.
- `timestamp` (ISODate): Wall-clock timestamp when prediction was made.
- `simulation_time` (Number): Simulation time at prediction moment.
- `horizon_seconds` (Number): Prediction horizon in seconds (e.g., 30).
- `current_congestion_score` (Number): Current congestion score (0-100).
- `predicted_congestion_score` (Number): Predicted future congestion score (0-100).
- `congestion_level` (String): Predicted congestion level (FREE_FLOW, LOW, MODERATE, HIGH, SEVERE).
- `model_name` (String): Name of the model used for prediction.
- `feature_version` (String): Version of feature engineering pipeline.

**Indexes**:
- `simulation_id` + `simulation_time` (Compound)
- `timestamp` (Single field)
- `intersection_id` + `timestamp` (Compound)

---

## 3. Database Repositories & Access Layer

The database operations are encapsulated in `backend/database/repositories/`:
1. `IntersectionRepository`: Default intersection seeding, retrieval, and updating.
2. `SimulationRepository`: Lifecycle tracking (`create_run`, `update_run`, `get_run`, `list_runs`), and analytics aggregations (`get_analytics_summary`, `get_controller_comparison`).
3. `TrafficRepository`: High-throughput time-series persistence (`insert_snapshot`, `batch_insert_snapshots`, `get_snapshots_by_simulation`).
4. `SignalRepository`: Signal decision logging (`insert_decision`, `get_decisions_by_simulation`).
5. `PredictionRepository`: Congestion prediction results persistence (`insert_prediction`, `get_predictions`).

---

## 4. Analytical Aggregation Pipelines

### 4.1. Comparative Performance Aggregation
Used by `GET /api/analytics/controller-comparison` to aggregate completed simulation runs grouped by controller algorithm:
```javascript
db.simulation_runs.aggregate([
  { $match: { status: "completed", metrics: { $ne: null } } },
  {
    $group: {
      _id: "$controller",
      total_runs: { $sum: 1 },
      avg_vehicles_served: { $avg: "$metrics.total_vehicles_served" },
      avg_queue: { $avg: "$metrics.average_queue" },
      avg_waiting_time: { $avg: "$metrics.average_waiting_time" },
      avg_speed: { $avg: "$metrics.average_speed" },
      avg_co2_kg: { $avg: "$metrics.total_co2_emission_kg" }
    }
  }
])
```
