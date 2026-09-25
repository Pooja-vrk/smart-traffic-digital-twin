# AI-Driven Digital Twin for Smart City Traffic Flow Management

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.2%2B-EE4C2C.svg)](https://pytorch.org)
[![Eclipse SUMO](https://img.shields.io/badge/SUMO-1.19%2B-5C82A6.svg)](https://eclipse.dev/sumo/)
[![Status](https://img.shields.io/badge/Status-Step 7%20Completed-brightgreen.svg)](#project-development-phases)

---

## 1. Project Overview
The **AI-Driven Digital Twin for Smart City Traffic Flow Management** is an intelligent urban mobility platform. It pairs high-fidelity microscopic traffic simulation (Eclipse SUMO) with an AI decision-making engine (Deep Q-Networks), an asynchronous web backend (FastAPI + WebSockets), and high-throughput persistence (MongoDB) to create a synchronized, bi-directional digital twin of urban traffic intersections.

The system empowers municipal traffic authorities and urban engineers to observe, evaluate, forecast, and optimize traffic signal timing plans dynamically in response to real-time vehicular queues, waiting times, and approaching emergency vehicles.

---

## 2. Problem Statement
Rapid urbanization and rising vehicle density result in widespread traffic congestion, leading to:
- Excessive vehicle idling time and driver delay.
- Escalating carbon emissions ($CO_2$) and environmental degradation.
- Delayed emergency services and first-responder vehicles.
- Inefficiency of conventional Fixed-Time traffic controllers that fail to adapt to asymmetric and bursty traffic flow patterns.

---

## 3. Proposed Solution
This project implements a **Digital Twin Architecture**:
1. **Simulation & Mirroring**: Real-time microscopic traffic physics simulated in Eclipse SUMO and controlled via the Python TraCI API.
2. **Tri-Mode Traffic Control**: Seamless benchmarking and switching between **Fixed-Time**, **Rule-Based Adaptive**, and **Deep Q-Learning (DQN)** control policies.
3. **Telemetry & Synchronization**: Sub-second telemetry streaming over WebSockets from the simulation engine to an interactive operator web dashboard.
4. **Database & Persistence**: High-resolution time-series snapshots, signal decision audits, and aggregate performance metrics persisted in MongoDB with automatic index optimization.
5. **Predictive Analytics**: Machine learning models forecasting localized traffic buildup before severe bottlenecks form *(Planned)*.
6. **Emergency Vehicle Preemption**: Automated green corridor clearance for emergency vehicles.

---

## 4. Main Objectives
- Build a modular 4-way urban intersection digital twin in Eclipse SUMO.
- Implement and benchmark three signal control approaches (Fixed-Time, Adaptive, DQN).
- Train an autonomous reinforcement learning agent that significantly reduces mean vehicle waiting time and queue length.
- Deliver a real-time reactive web dashboard displaying live traffic telemetry, spatial queue maps, and performance KPIs.
- Persist high-resolution simulation telemetry, signal decisions, and run analytics in MongoDB.
- Align technological innovation with UN Sustainable Development Goals.

---

## 5. Core Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Micro-Simulation Engine** | Eclipse SUMO (Simulation of Urban MObility), TraCI Python Library |
| **AI / Reinforcement Learning** | PyTorch, NumPy, Pandas, Scikit-Learn |
| **Backend & APIs** | FastAPI, Uvicorn (ASGI), Pydantic, WebSockets |
| **Database & Persistence** | MongoDB, Motor (Async Driver), PyMongo |
| **Frontend Web Dashboard** | React, Vite, HTML5 Canvas / SVG, CSS3 *(Planned)* |
| **Testing & Tooling** | Pytest, Pytest-AsyncIO, HTTPX |

---

## 6. High-Level Architecture

```
+-------------------------------------------------------------------------+
|                        Frontend Operator Dashboard                      |
|  [Traffic Map]  [Signal Status]  [KPI Cards]  [Controller Controls]     |
+------------------------------------+------------------------------------+
                                     |  HTTP REST / WebSockets
+------------------------------------v------------------------------------+
|                         Backend (FastAPI Engine)                        |
|  [Traffic API]  [Simulation API]  [AI API]  [Analytics]  [WebSocket Mgr]|
+------------------+------------------------------+-----------------------+
                   |                              |
+------------------v--------------+  +------------v-----------------------+
|  Simulation (Eclipse SUMO)      |  |  AI & Decision Subsystem           |
|  - SUMO Network & Routes        |  |  - DQN Agent (PyTorch)             |
|  - TraCI Controller             |  |  - Rule-Based Adaptive Controller  |
|  - State Extractor & Metrics    |  |  - Fixed-Time Baseline Controller  |
+---------------------------------+  +------------------------------------+
                   |                              |
                   +--------------+---------------+
                                  |
                     +------------v-----------------------+
                     |  Database Persistence (MongoDB)    |
                     |  - intersections                   |
                     |  - simulation_runs                 |
                     |  - traffic_snapshots               |
                     |  - signal_decisions                |
                     +------------------------------------+
```

---

## 7. Digital Twin Workflow
1. **Physical/Simulated State Extraction**: TraCI extracts vehicle positions, lane queues, and speeds from SUMO at each tick.
2. **State Vector Encoding**: State parameters are normalized into continuous tensors.
3. **AI Evaluation & Action Selection**:
   - The selected controller (Fixed-Time / Adaptive / DQN) selects the optimal signal phase.
   - Safety constraints (minimum green time, yellow change intervals) are verified.
4. **Signal Actuation**: Action is executed back into SUMO via TraCI.
5. **Real-Time Streaming & Persistence**: Telemetry payload is pushed via WebSockets to the web dashboard and asynchronously persisted to MongoDB with zero-impact failure isolation.

---

## 8. Three Traffic Control Approaches

| Controller | Mechanism | Characteristics |
| :--- | :--- | :--- |
| **Fixed-Time** *(Baseline)* | Static cyclical phase schedule with preset timer splits. | Predictable, simple, but inefficient during irregular or asymmetric traffic surges. |
| **Rule-Based Adaptive** | Actuated logic dynamically extending green phases when queue thresholds are exceeded. | Responsive to local fluctuations; limited long-term optimization capability. |
| **DQN Reinforcement Learning** | Deep Q-Network trained via trial-and-error to maximize cumulative reward (delay minimization). | Learns complex nonlinear traffic dynamics; highly adaptive to multi-directional surges. |

---

## 9. Implemented AI State / Action / Reward Formulation

- **State Space ($S$)**: Continuous vector $\in \mathbb{R}^6$ containing normalized queue counts per approach (North, South, East, West), normalized current phase index, and normalized active green elapsed time.
- **Action Space ($A$)**: Discrete actions $\{0: \text{KEEP}, 1: \text{SWITCH\_NS}, 2: \text{SWITCH\_EW}\}$ subject to physical `SignalSafetyManager` constraints.
- **Reward Function ($R_t$)**: Step-to-step delta multi-objective reward:
  $$R_t = - 1.0 \cdot \text{Queue}_t - 0.5 \cdot \Delta\text{Wait}_t + 2.0 \cdot \Delta\text{Throughput}_t - 2.0 \cdot \text{SwitchPenalty}_t$$

---

## 10. Development Phases

| Phase | Description | Status |
| :--- | :--- | :---: |
| **Step 1** | Repository Setup, Scaffolding & Configuration | **Completed** |
| **Step 2** | SUMO Traffic Simulation & TraCI Integration | **Completed** |
| **Step 3** | Classical Controllers (Fixed-Time & Adaptive) | **Completed** |
| **Step 4** | DQN Agent Design, Training & Evaluation | **Completed** |
| **Step 5** | FastAPI Backend & WebSocket Telemetry Engine | **Completed** |
| **Step 6** | MongoDB Persistence & Digital Twin Data Layer | **Completed** |
| **Step 7** | Congestion Prediction & Advanced Analytics | *Infrastructure Complete* |
| **Step 8** | React Frontend Digital Twin Dashboard | *Planned* |
| **Step 9** | System Testing, Verification & Final Demo | *Planned* |

---

## 11. Database Setup & Seeding

1. Ensure MongoDB service is running locally (`mongodb://localhost:27017`) or configure `MONGODB_URI` in `.env`.
2. Seed the database and build indexes:
```powershell
python scripts/seed_database.py
```

---

## 12. Running the FastAPI Backend

Start the FastAPI application with live reload:
```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Access Interactive Documentation:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## 12. Repository Structure

```text
smart-traffic-digital-twin/
│
├── README.md                          # Project overview and documentation
├── requirements.txt                   # Python package dependencies
├── .env.example                       # Environment variable template
├── .gitignore                         # Version control ignore rules
│
├── docs/                              # Project specifications & architecture docs
│   ├── requirements.md
│   ├── architecture.md
│   ├── database-design.md
│   ├── ai-design.md
│   ├── api-spec.md
│   ├── testing-strategy.md
│   ├── implementation-plan.md
│   └── project-scope.md
│
├── backend/                           # FastAPI backend server
│   ├── __init__.py
│   ├── main.py                        # FastAPI entry point
│   ├── config/                        # Configuration & settings
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── api/                           # API routers
│   │   ├── __init__.py
│   │   ├── traffic.py
│   │   ├── simulation.py
│   │   ├── ai.py
│   │   ├── analytics.py
│   │   └── prediction.py
│   ├── models/                        # Pydantic schemas & DB models
│   │   └── __init__.py
│   ├── services/                      # Business logic & background tasks
│   │   └── __init__.py
│   └── websocket/                     # WebSocket connection manager
│       ├── __init__.py
│       └── manager.py
│
├── simulation/                        # SUMO simulation environment
│   ├── __init__.py
│   ├── sumo/                          # SUMO network and route definitions
│   ├── environment.py                 # Simulation environment interface
│   ├── state.py                       # Simulation state representation
│   ├── metrics.py                     # Performance metric calculations
│   └── traci_controller.py            # TraCI communication wrapper
│
├── ai/                                # Deep Reinforcement Learning subsystem
│   ├── __init__.py
│   ├── environment.py                 # RL environment wrapper (Gym-like)
│   ├── dqn_agent.py                   # Deep Q-Network agent implementation
│   ├── neural_network.py              # PyTorch Q-network architecture
│   ├── replay_buffer.py               # Experience replay buffer
│   ├── reward.py                      # Multi-objective reward computation
│   ├── train.py                       # DQN offline/online training pipeline
│   ├── evaluate.py                    # Model benchmarking and validation
│   └── models/                        # Saved neural network checkpoints
│
├── prediction/                        # Traffic congestion prediction
│   └── __init__.py
│
├── frontend/                          # React + Vite web dashboard (placeholder)
│
├── data/                              # Data storage for experiments
│   ├── raw/
│   ├── processed/
│   └── experiments/
│
├── tests/                             # Automated test suite
│   ├── __init__.py
│   ├── test_simulation.py
│   ├── test_ai.py
│   ├── test_api.py
│   └── test_metrics.py
│
└── scripts/                           # Utility scripts
    ├── __init__.py
    ├── setup.py
    ├── seed_database.py
    └── run_demo.py
```

---

## 14. Installation Prerequisites & Setup (Windows PowerShell)

### Prerequisites
1. **Python 3.10+**: Ensure Python is installed and added to the Windows `PATH`.
2. **Eclipse SUMO**: Install SUMO on Windows and set `SUMO_HOME` (e.g., `C:\Program Files (x86)\Eclipse\Sumo`).
3. **Node.js 18+ & npm**: Required for later frontend development.
4. **MongoDB**: Local Community Server (port 27017) or MongoDB Atlas URI.

### Environment Setup

1. **Create Python Virtual Environment**:
   ```powershell
   python -m venv .venv
   ```

2. **Activate Virtual Environment in Windows PowerShell**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies**:
   ```powershell
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   ```powershell
   Copy-Item .env.example .env
   ```

---

## 15. Future Scope
- **Multi-Intersection Network Coordination**: Extending DQN to multi-agent reinforcement learning (MARL) across interconnected junctions.
- **Pedestrian & Cyclist Integration**: Adding crosswalk demand and pedestrian safety priority logic.
- **V2X Communication**: Incorporating Connected and Autonomous Vehicle (CAV) telemetry streams.
- **Hardware Integration**: Ingesting real-world CCTV edge-computed vehicle count data.
