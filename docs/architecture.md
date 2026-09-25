# System Architecture Document

## 1. High-Level Architecture Overview

The system follows a multi-tier modular architecture bridging physical/simulated traffic physics, AI decision engines, asynchronous backend services, and a modern web dashboard.

```
+-------------------------------------------------------------------------+
|                              Frontend (React + Vite)                    |
|  [Traffic Twin Map]  [Signal Monitor]  [KPI Cards]  [Controller Switch] |
+------------------------------------+------------------------------------+
                                     |  HTTP REST / WebSockets
+------------------------------------v------------------------------------+
|                         Backend (FastAPI Engine)                        |
|  [Health]  [Controllers]  [Simulation REST]  [Traffic REST]  [WebSocket]|
+------------------------------------+------------------------------------+
                                     |
                        +------------v------------+
                        |    SimulationManager    |
                        | (Non-blocking Worker)   |
                        +------------+------------+
                                     |
           +-------------------------+-------------------------+
           |                                                   |
+----------v----------------------+         +------------------v------------------+
|  Simulation Layer (Eclipse SUMO)|         |   Telemetry & Streaming Layer       |
|  - TrafficSimulationEnvironment |         |   - TelemetryService (DTO mapping)  |
|  - TraCIController (Socket)     |         |   - WebSocketManager (Broadcasts)   |
|  - Controllers: Fixed/Adapt/DQN |         +-------------------------------------+
|  - SignalSafetyManager (Safety) |
|  - State & Metrics Extractor    |
+---------------------------------+
```

## 2. Component Breakdown

1. **Simulation Layer (`simulation/`)**: Wraps TraCI to control SUMO, step physics, inject vehicles, switch traffic light phases, and compute micro-metrics.
2. **AI Layer (`ai/`)**: Houses the Deep Q-Network agent (`DQNAgent`), PyTorch neural network policy model (`DeepQNetwork`), experience replay buffer (`ReplayBuffer`), multi-objective reward calculator (`RewardCalculator`), and inference controller (`DQNController`).
3. **Backend Service (`backend/`)**:
   - **FastAPI Engine (`backend/main.py`)**: Asynchronous web server hosting REST APIs and WebSocket endpoints with CORS middleware and lifecycle management.
   - **SimulationManager (`backend/services/simulation_manager.py`)**: Singleton coordinator executing SUMO in non-blocking daemon threads, enforcing single-simulation concurrency (HTTP 409 protection), handling graceful stops, and caching latest snapshots and results in memory.
   - **TelemetryService (`backend/services/telemetry_service.py`)**: Serializes instantaneous `SimulationState` and `SimulationMetrics` into standardized JSON-safe API DTOs and WebSocket packets with AI decision metadata.
   - **WebSocketManager (`backend/websocket/manager.py`)**: Connection manager maintaining active client sockets, handling client pings, and broadcasting real-time packets (`simulation_started`, `traffic_update`, `simulation_completed`, `simulation_stopped`, `simulation_error`).
4. **Data Persistence Layer (`backend/database/`)**:
   - **Database Manager (`backend/database/connection.py`)**: Asynchronous (Motor) and Synchronous (PyMongo) MongoDB driver integration with ping health verification and idempotent index creation.
   - **Repositories (`backend/database/repositories/`)**:
     - `IntersectionRepository`: Topology profiles, lane geometry, and signal phase configurations (`intersections`).
     - `SimulationRepository`: Run lifecycles, configuration parameters, and aggregate KPI storage (`simulation_runs`).
     - `TrafficRepository`: High-resolution time-series spatial queue, velocity, and delay snapshots (`traffic_snapshots`).
     - `SignalRepository`: Full audit logging of controller decisions, Q-values, safety validations, and switch rationales (`signal_decisions`).
     - `PredictionRepository`: Congestion prediction results and forecast metadata (`congestion_predictions`).
   - **Persistence Service (`backend/services/persistence_service.py`)**: Non-blocking, failure-isolated data ingestion pipeline shielding core SUMO/TraCI physics and WebSocket delivery from database latency or connection anomalies.
5. **Prediction Layer (`prediction/`)**:
   - **Congestion Score (`prediction/congestion.py`)**: Explainable 0-100 congestion score calculation and classification.
   - **Feature Engineering (`prediction/feature_engineering.py`)**: Extraction of current and temporal lag features from traffic snapshots.
   - **Target Builder (`prediction/target_builder.py`)**: Construction of future congestion targets with proper horizon handling.
   - **Data Loader (`prediction/data_loader.py`)**: MongoDB historical data loading with simulation-run-based train/test splitting.
   - **ML Model (`prediction/model.py`)**: RandomForestRegressor for congestion prediction with baseline comparison.
   - **Predictor Service (`prediction/predictor.py`)**: Real-time prediction service with model loading and feature validation.
   - **Training Pipeline (`prediction/train.py`)**: End-to-end model training with evaluation and persistence.
   - **Evaluation (`prediction/evaluate.py`)**: Model evaluation metrics and benchmarking.
6. **Presentation Layer (`frontend/`)**: Single-page application rendering live digital twin visuals and traffic analytics.

## 3. Simulation Execution & Concurrency Model
- **Non-blocking Execution**: TraCI socket communication is isolated inside a dedicated background worker thread (`sim-worker-<id>`).
- **Single-Simulation Concurrency**: Only one active simulation is permitted at any time. Any concurrent start request is rejected with HTTP 409 Conflict.
- **Graceful Stop & Shutdown**: Controlled via thread-safe `threading.Event`. TraCI is closed cleanly on completion or stop request, leaving zero orphan processes.
- **Resilient Persistence**: Database errors are logged without interrupting the simulation runtime.


