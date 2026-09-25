# API Specification Document

## 1. REST Endpoints

### 1.1. Health Check
- **Endpoint**: `GET /api/health`
- **Description**: Verifies backend health and SUMO binary availability without starting a simulation.
- **Response** (`200 OK`):
  ```json
  {
    "status": "ok",
    "service": "smart-traffic-digital-twin",
    "version": "1.0.0",
    "sumo_available": true
  }
  ```

---

### 1.2. Controller Management
- **Endpoint**: `GET /api/controllers`
- **Description**: Returns all supported traffic controllers and DQN model availability.
- **Response** (`200 OK`):
  ```json
  [
    {
      "id": "fixed",
      "name": "Fixed-Time",
      "type": "baseline",
      "available": true,
      "model_path": null
    },
    {
      "id": "adaptive",
      "name": "Rule-Based Adaptive",
      "type": "adaptive",
      "available": true,
      "model_path": null
    },
    {
      "id": "dqn",
      "name": "Deep Q-Network",
      "type": "reinforcement_learning",
      "available": true,
      "model_path": "ai/models/dqn_traffic_controller.pt"
    }
  ]
  ```

---

### 1.3. Simulation Lifecycle Controls

#### Start Simulation
- **Endpoint**: `POST /api/simulation/start`
- **Request Body**:
  ```json
  {
    "controller": "dqn",
    "steps": 300,
    "seed": 42,
    "gui": false
  }
  ```
- **Responses**:
  - `200 OK`:
    ```json
    {
      "status": "started",
      "simulation_id": "9e685319",
      "controller": "dqn",
      "steps": 300,
      "seed": 42
    }
    ```
  - `409 Conflict`: Simulation already running.
  - `422 Unprocessable Entity`: Invalid controller or step parameters.
  - `503 Service Unavailable`: DQN checkpoint missing.

#### Stop Simulation
- **Endpoint**: `POST /api/simulation/stop`
- **Response** (`200 OK`):
  ```json
  {
    "status": "stopped",
    "simulation_id": "9e685319"
  }
  ```

#### Simulation Status
- **Endpoint**: `GET /api/simulation/status`
- **Response** (`200 OK`):
  ```json
  {
    "running": true,
    "status": "running",
    "simulation_id": "9e685319",
    "controller": "dqn",
    "seed": 42,
    "current_step": 125,
    "total_steps": 300,
    "simulation_time": 125.0,
    "error": null
  }
  ```

#### Simulation Result
- **Endpoint**: `GET /api/simulation/result`
- **Response** (`200 OK`):
  ```json
  {
    "simulation_id": "9e685319",
    "controller": "dqn",
    "seed": 42,
    "steps": 300,
    "status": "completed",
    "metrics": {
      "total_simulation_steps": 300,
      "total_simulation_time": 300.0,
      "total_vehicles_served": 223,
      "total_vehicles_entered": 275,
      "average_queue": 3.99,
      "max_queue": 12,
      "average_waiting_time": 19.39,
      "total_waiting_time": 5818.0,
      "average_speed": 10.14,
      "average_delay": 21.16,
      "phase_changes": 50,
      "total_co2_emission_kg": 30.78
    }
  }
  ```
  *(Returns `404 Not Found` if no completed run exists).*

---

### 1.4. Current Traffic Telemetry
- **Endpoint**: `GET /api/traffic/current`
- **Response** (`200 OK`):
  ```json
  {
    "simulation_id": "9e685319",
    "simulation_time": 125.0,
    "step": 125,
    "controller": "DQN-ReinforcementLearning",
    "vehicles": {
      "total": 37,
      "entered": 121,
      "completed": 84
    },
    "queues": {
      "north": 4,
      "south": 3,
      "east": 7,
      "west": 2,
      "total": 16,
      "peak": 18
    },
    "speed": {
      "average_mps": 9.8
    },
    "waiting": {
      "average_seconds": 12.4,
      "total_seconds": 456.0
    },
    "signal": {
      "phase_index": 0,
      "phase_name": "NORTH_SOUTH_GREEN",
      "state": "green",
      "elapsed_seconds": 18.0
    },
    "ai": {
      "action": "KEEP",
      "action_id": 0,
      "requested_phase": 0,
      "approved": true,
      "reason": "DQN policy selected action KEEP"
    }
  }
  ```

---

### 1.5. Simulation History & Queries

#### List Simulation History
- **Endpoint**: `GET /api/simulation/history`
- **Query Parameters**: `skip` (int, default 0), `limit` (int, default 20), `controller` (string, optional)
- **Response** (`200 OK`): Array of simulation summary objects.

#### Get Simulation Run Details
- **Endpoint**: `GET /api/simulation/{simulation_id}`
- **Response** (`200 OK`): Full simulation run record with metrics or `404 Not Found`.

#### Get Historical Telemetry Snapshots
- **Endpoint**: `GET /api/simulation/{simulation_id}/snapshots`
- **Query Parameters**: `skip` (int, default 0), `limit` (int, default 100)
- **Response** (`200 OK`): Array of time-series traffic snapshot records.

#### Get Historical Signal Decisions
- **Endpoint**: `GET /api/simulation/{simulation_id}/decisions`
- **Query Parameters**: `skip` (int, default 0), `limit` (int, default 100)
- **Response** (`200 OK`): Array of discrete signal actuation decision audit records.

---

### 1.6. Analytics & Performance Benchmarks

#### Overall Analytics Summary
- **Endpoint**: `GET /api/analytics/summary`
- **Response** (`200 OK`): Aggregated statistics across all historical simulation runs.

#### Controller Comparison Analytics
- **Endpoint**: `GET /api/analytics/controller-comparison`
- **Response** (`200 OK`): Grouped benchmark comparison across `fixed`, `adaptive`, and `dqn` controllers.

---

### 1.7. Congestion Prediction Endpoints

#### Prediction Model Status
- **Endpoint**: `GET /api/prediction/status`
- **Description**: Check if a trained prediction model is available and get metadata.
- **Response** (`200 OK`):
  ```json
  {
    "model_available": true,
    "model_name": "RandomForestRegressor",
    "prediction_horizon": 30.0,
    "feature_count": 27,
    "last_training_time": "2024-01-15T10:30:00Z",
    "feature_version": "1.0"
  }
  ```

#### Train Prediction Model
- **Endpoint**: `POST /api/prediction/train`
- **Request Body**:
  ```json
  {
    "horizon_seconds": 30,
    "random_state": 42
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "success": true,
    "message": "Model training completed successfully",
    "dataset_statistics": {
      "num_simulation_runs": 5,
      "num_snapshots": 1500,
      "num_training_samples": 1200
    },
    "model_info": {
      "model_type": "RandomForestRegressor",
      "n_estimators": 200,
      "max_depth": 12
    },
    "evaluation_metrics": {
      "ml_model": {
        "mae": 5.23,
        "rmse": 7.45,
        "r2": 0.82
      },
      "baseline": {
        "mae": 8.91,
        "rmse": 11.23,
        "r2": 0.65
      }
    }
  }
  ```

#### Current Congestion Prediction
- **Endpoint**: `GET /api/prediction/current`
- **Description**: Predict future congestion using the latest available traffic state.
- **Response** (`200 OK`):
  ```json
  {
    "predicted_congestion_score": 45.3,
    "congestion_level": "MODERATE",
    "prediction_horizon": 30.0,
    "model_name": "RandomForestRegressor",
    "model_available": true,
    "baseline_score": 38.7,
    "current_congestion_score": 38.7
  }
  ```

#### Custom Prediction
- **Endpoint**: `POST /api/prediction/predict`
- **Request Body**:
  ```json
  {
    "snapshot": {
      "queues": {"north": 5, "south": 3, "east": 7, "west": 2, "total": 17},
      "waiting": {"average_seconds": 15.0},
      "speed": {"average_mps": 8.0},
      "signal": {"phase_index": 0, "elapsed_seconds": 10.0},
      "controller": "adaptive",
      "simulation_time": 100.0
    },
    "historical_snapshots": [...]
  }
  ```
- **Response** (`200 OK`): Similar to current prediction endpoint.

#### Prediction History
- **Endpoint**: `GET /api/prediction/history`
- **Query Parameters**: `limit` (int, default 100)
- **Response** (`200 OK`): Array of prediction records.

---

### 1.8. Advanced Analytics Endpoints

#### Congestion Distribution
- **Endpoint**: `GET /api/analytics/congestion-distribution`
- **Query Parameters**: `simulation_id` (optional), `limit` (int, default 1000)
- **Response** (`200 OK`):
  ```json
  {
    "congestion_levels": {
      "FREE_FLOW": 45,
      "LOW": 120,
      "MODERATE": 85,
      "HIGH": 30,
      "SEVERE": 10
    },
    "total_snapshots": 290,
    "percentage_distribution": {
      "FREE_FLOW": 15.5,
      "LOW": 41.4,
      "MODERATE": 29.3,
      "HIGH": 10.3,
      "SEVERE": 3.5
    }
  }
  ```

#### Traffic Trends
- **Endpoint**: `GET /api/analytics/traffic-trends`
- **Query Parameters**: `simulation_id` (optional), `limit` (int, default 300)
- **Response** (`200 OK`):
  ```json
  {
    "simulation_id": "e83b190f",
    "trends": [
      {
        "simulation_time": 0.0,
        "queue": 5.0,
        "speed": 12.5,
        "throughput": 0,
        "waiting_time": 2.3,
        "congestion_score": 15.2
      },
      ...
    ],
    "count": 300
  }
  ```

#### Detailed Controller Performance
- **Endpoint**: `GET /api/analytics/controller-performance`
- **Response** (`200 OK`):
  ```json
  {
    "controllers": {
      "fixed": {
        "runs_count": 10,
        "throughput": 206.5,
        "average_queue": 11.43,
        "peak_queue": 28.0,
        "average_wait": 130.35,
        "average_delay": 142.20,
        "average_speed": 8.62,
        "phase_changes": 50.0,
        "estimated_co2_kg": 33.67
      },
      ...
    },
    "comparison_summary": {
      "best_throughput_controller": "dqn",
      "lowest_queue_controller": "adaptive",
      "lowest_wait_controller": "adaptive",
      "highest_speed_controller": "adaptive"
    }
  }
  ```

---

## 2. WebSocket Telemetry Stream

- **Channel**: `WS /ws/traffic`
- **Packet Structure**:
  ```json
  {
    "type": "traffic_update",
    "timestamp": "2026-09-10T14:05:00.441362+00:00",
    "simulation_id": "9e685319",
    "data": { ... }
  }
  ```
- **Supported Event Types**:
  1. `status_update`: Sent immediately on client connect.
  2. `simulation_started`: Emitted when simulation launches.
  3. `traffic_update`: Streamed per simulation step with full snapshot.
  4. `simulation_completed`: Emitted on normal completion with final aggregate metrics.
  5. `simulation_stopped`: Emitted on user stop request.
  6. `simulation_error`: Emitted on runtime failure.
  7. `ping` / `pong`: Heartbeat channel.

