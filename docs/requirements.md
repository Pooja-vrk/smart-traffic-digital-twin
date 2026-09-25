# System Requirements Specification

## 1. Functional Requirements (FR)
- **FR-1: Traffic Simulation**: The system shall execute high-fidelity micro-simulations of intersection traffic using Eclipse SUMO via TraCI.
- **FR-2: Tri-Mode Signal Control**: The system shall support switching between Fixed-Time, Rule-Based Adaptive, and Deep Q-Network (DQN) AI controllers.
- **FR-3: Real-Time State Extraction**: The system shall extract vehicular queues, speeds, lane densities, and accumulated wait times at every simulation step.
- **FR-4: Telemetry Streaming**: The backend shall broadcast real-time simulation metrics via WebSockets at 1–5 Hz.
- **FR-5: Congestion Prediction**: The system shall forecast downstream congestion likelihood using historic and real-time state features.
- **FR-6: Emergency Override**: The system shall detect approaching emergency vehicles and preempt current signal phases.
- **FR-7: Persistence**: Simulation runs, controller decisions, and aggregated metrics shall be persisted to MongoDB.
- **FR-8: Operator Dashboard**: The web UI shall display live intersection animations, metrics charts, mode switches, and what-if controls.

## 2. Non-Functional Requirements (NFR)
- **NFR-1 (Performance)**: WebSocket telemetry latency < 100ms.
- **NFR-2 (Maintainability)**: Clean modular separation among `simulation/`, `ai/`, `backend/`, `frontend/`, and `prediction/`.
- **NFR-3 (Reproducibility)**: Deterministic simulation seeding for benchmarking controllers.
- **NFR-4 (Platform Compatibility)**: Full support for Windows OS with PowerShell setup workflows.
- **NFR-5 (Test Coverage)**: Automated test suite validating core mathematical metrics and API contracts.
