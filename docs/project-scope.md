# Project Scope Document

## 1. Project Title
**AI-Driven Digital Twin for Smart City Traffic Flow Management**

## 2. Project Vision
To build a high-fidelity digital twin platform that mirrors physical urban intersection traffic dynamics in real-time, optimizes traffic light signal timings using Deep Q-Learning (DQN) and rule-based adaptive algorithms, predicts short-term congestion, and provides traffic operators with real-time analytics and what-if simulation capabilities.

## 3. In-Scope Deliverables
1. **Simulation Environment (Eclipse SUMO + TraCI)**:
   - High-fidelity 4-way intersection simulation model.
   - Dynamic vehicle generation, route definitions, and queue monitoring.
   - Emergency vehicle priority override simulation.
2. **Three Traffic Signal Control Paradigms**:
   - **Fixed-Time Baseline Controller**: Standard predefined cyclical green times.
   - **Rule-Based Adaptive Controller**: Actuated logic based on instantaneous queue lengths and wait thresholds.
   - **DQN Reinforcement Learning Agent**: Deep Q-Network optimizing phase duration/switching based on state vectors (queue lengths, waiting times, vehicle density).
3. **Congestion Prediction Subsystem**:
   - Machine learning-based short-term traffic volume and congestion index prediction.
4. **Backend Architecture (FastAPI & MongoDB)**:
   - RESTful API endpoints for traffic telemetry, controller switching, metrics, and simulation controls.
   - WebSocket streaming for real-time digital twin synchronization (sub-second telemetry updates).
   - Asynchronous data persistence via Motor / PyMongo.
5. **Interactive Frontend Web Dashboard (React + Vite)**:
   - Real-time digital twin intersection visualization.
   - Live traffic KPIs: Average Waiting Time, Queue Length, CO2 emissions proxy, Throughput.
   - Controller comparison & switching interface.
   - AI recommendation panel and What-If scenario triggers.
6. **Automated Testing Suite**:
   - Unit and integration tests covering simulation connectors, AI models, backend endpoints, and metrics calculation.

## 4. Out-of-Scope (Future Enhancements)
- Multi-intersection networked grid coordination (Phase 2).
- Direct hardware integration with physical roadside units (RSUs) / inductive loop sensors.
- V2X (Vehicle-to-Everything) 5G protocol simulation.

## 5. Alignment with Sustainable Development Goals (SDGs)
- **SDG 9 (Industry, Innovation, and Infrastructure)**: Upgrades urban transit infrastructure through intelligent AI automation.
- **SDG 11 (Sustainable Cities and Communities)**: Reduces urban traffic congestion, minimizes idling time, and improves mobility.
- **SDG 13 (Climate Action)**: Lowers vehicular carbon emissions and fuel waste caused by frequent stop-and-go congestion.
