# AI & Reinforcement Learning Design Document

## 1. Deep Q-Network (DQN) Formulation

The traffic signal control task is framed as a discrete-time Markov Decision Process (MDP):

### 1.1. State Space (\(S\))
A continuous normalized vector of dimension 6 representing the intersection's immediate traffic condition:
1. `queue_north`: Halted vehicles on Northbound incoming approach ($N / 30.0$).
2. `queue_south`: Halted vehicles on Southbound incoming approach ($N / 30.0$).
3. `queue_east`: Halted vehicles on Eastbound incoming approach ($N / 30.0$).
4. `queue_west`: Halted vehicles on Westbound incoming approach ($N / 30.0$).
5. `current_phase`: Active phase index normalized ($p / 3.0$, where 0 = NS Green, 1 = NS Yellow, 2 = EW Green, 3 = EW Yellow).
6. `elapsed_green`: Time spent in active green phase normalized ($t / 60.0$).

### 1.2. Action Space (\(A\))
Discrete action set selecting target signal phase configurations:
- `Action 0`: **KEEP** — Maintain current green phase.
- `Action 1`: **SWITCH_NS** — Request North-South Green Phase (Phase 0: `GrGr`).
- `Action 2`: **SWITCH_EW** — Request East-West Green Phase (Phase 2: `rGrG`).

*Note: All actions are mediated by the `SignalSafetyManager`, which strictly guarantees minimum green times ($10\text{s}$), maximum green times ($60\text{s}$), and mandatory yellow transitions ($3\text{s}$).*

### 1.3. Reward Function (\(R\))
Multi-objective step-to-step delta reward function computed every decision step ($5\text{s}$):
\[
R_t = - w_q \cdot \text{Queue}_t - w_w \cdot \Delta\text{Wait}_t + w_{tp} \cdot \Delta\text{Throughput}_t - w_s \cdot \text{SwitchPenalty}_t
\]
Where:
- $w_q = 1.0$: Weight on total queued vehicles across all approaches.
- $w_w = 0.5$: Weight on step-to-step change in cumulative waiting time ($\Delta\text{Wait}_t = W_t - W_{t-1}$).
- $w_{tp} = 2.0$: Positive bonus per vehicle successfully completing travel through the intersection.
- $w_s = 2.0$: Penalty applied if a phase switch is triggered.

---

## 2. Neural Network Architecture

- **PyTorch MLP (`DeepQNetwork`)**:
  - Input Layer: 6 features
  - Hidden Layer 1: Linear(6, 128) + ReLU
  - Hidden Layer 2: Linear(128, 128) + ReLU
  - Output Layer: Linear(128, 3) (Q-values for actions [0, 1, 2])
- **Weight Initialization**: Kaiming / He normal initialization for linear layers, zero biases.
- **Optimization**: Adam optimizer ($\text{lr} = 1 \times 10^{-3}$) with Smooth L1 (Huber) Loss and gradient norm clipping at $1.0$.

---

## 3. Training Hyperparameters

| Hyperparameter | Value | Description |
| :--- | :--- | :--- |
| Replay Buffer Capacity | 50,000 | FIFO experience memory |
| Batch Size | 64 | Minibatch size sampled uniformly |
| Discount Factor ($\gamma$) | 0.95 | Bellman equation discount factor |
| Learning Rate ($\alpha$) | 0.001 | Adam optimizer learning rate |
| Initial Epsilon ($\epsilon_{\text{start}}$) | 1.0 | Initial exploration rate |
| Minimum Epsilon ($\epsilon_{\text{min}}$) | 0.05 | Terminal exploration floor |
| Epsilon Decay Rate | 0.995 | Multiplicative decay per episode |
| Target Network Sync Interval | 10 episodes | Hard copy from online to target network |
| Decision Step Interval ($\Delta t_{\text{action}}$) | 5.0 seconds | Frequency of RL decision making |
| Episode Duration | 300 seconds | Simulation horizon per training episode |
| Total Episodes | 35 | Training duration |

---

## 4. Empirical Evaluation & Benchmark Results (300s, Seed=42)

| Metric | Fixed-Time Baseline | Rule-Based Adaptive | DQN Controller (RL) |
| :--- | :---: | :---: | :---: |
| **Throughput (veh completed)** | 206 | 220 | **223** (+8.3% vs Fixed) |
| **Vehicles Entered** | 275 | 275 | 275 (Identical demand) |
| **Average Queue Length (veh)** | 11.43 | 3.50 | **3.99** (-65.1% vs Fixed) |
| **Peak Queue Length (veh)** | 28 | 12 | **12** (-57.1% vs Fixed) |
| **Average Waiting Time (s)** | 130.35 s | 17.64 s | **19.39 s** (-85.1% vs Fixed) |
| **Total Cumulative Wait (s)** | 39,104.0 s | 5,293.0 s | **5,818.0 s** (-85.1% vs Fixed) |
| **Average Delay per Vehicle** | 142.20 s/veh | 19.25 s/veh | **21.16 s/veh** (-85.1% vs Fixed) |
| **Average Speed (m/s)** | 8.62 m/s | 10.38 m/s | **10.14 m/s** (+17.6% vs Fixed) |
| **CO2 Emissions Proxy (kg)** | 33.67 kg | 29.92 kg | **30.78 kg** (-8.6% vs Fixed) |

---

## 5. Congestion Prediction (Step 7)

### 5.1. Prediction Objective

The congestion prediction module forecasts future traffic congestion levels using historical simulation data stored in MongoDB. The system answers:

"Based on the current traffic state, what congestion level is likely to occur approximately 30 simulation seconds in the future?"

### 5.2. Congestion Score Definition

An explainable congestion score from 0-100 is calculated from traffic snapshot fields:

**Components:**
- Total queue length (60% weight)
- Average queue length (20% weight)
- Average waiting time (15% weight)
- Inverse of average speed (5% weight)

**Classification Thresholds:**
- 0–20: FREE_FLOW
- 21–40: LOW
- 41–60: MODERATE
- 61–80: HIGH
- 81–100: SEVERE

### 5.3. Feature Engineering

**Current Features (available at prediction time):**
- Queue metrics: north, south, east, west, total, max, average, imbalance
- Waiting time: average_waiting_time
- Speed: average_speed
- Signal: phase_index, elapsed_green
- Controller: one-hot encoded (fixed, adaptive, dqn)
- Simulation time
- Current congestion score

**Temporal Lag Features:**
- Queue total lag: 1, 2, 3 steps back
- Queue total delta: 1, 3 steps
- Speed lag: 1, 2, 3 steps back
- Speed delta: 1 step

### 5.4. Target Construction

For each snapshot at time t:
- **Features**: Traffic information available at t
- **Target**: Congestion score at t + 30 seconds (with ±5 second tolerance)

Future target is only created when a valid future snapshot exists. No artificial future labels are created.

### 5.5. Data Leakage Prevention

**Allowed in features:**
- Current values
- Previous values
- Previous trends
- Current signal state
- Historical values before t

**Forbidden in features:**
- Future queue
- Future speed
- Future throughput
- Future signal phase
- Future congestion score

Automated tests verify that future information cannot enter the feature vector.

### 5.6. Train/Test Split Strategy

**Simulation-Run-Based Splitting:**
- 70% simulation runs → training
- 15% simulation runs → validation
- 15% simulation runs → test

This prevents temporal leakage by avoiding snapshots from the same simulation run appearing in both training and test sets.

**Random Seed:** 42 for reproducibility

### 5.7. Model Architecture

**Model Type:** RandomForestRegressor (scikit-learn)

**Parameters:**
- n_estimators: 200
- max_depth: 12
- random_state: 42
- n_jobs: -1 (parallel processing)

**Baseline:** Current congestion score (predicts future equals current)

### 5.8. Evaluation Metrics

**Regression Metrics:**
- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- R² (coefficient of determination)

**Classification Metrics:**
- Congestion level classification accuracy

**Comparison:** ML model vs baseline to demonstrate improvement.

### 5.9. Model Persistence

**Artifacts:**
- Model: `prediction/models/congestion_model.joblib` (joblib)
- Metadata: `prediction/models/feature_metadata.json`

**Metadata includes:**
- Feature names and version
- Target definition
- Prediction horizon
- Model name and parameters
- Training timestamp
- Dataset size
- Random seed

### 5.10. Prediction Service

**Real-time Prediction:**
- Load trained model and metadata
- Validate feature ordering
- Prepare input from current traffic state
- Generate prediction with confidence bounds
- Classify predicted congestion level

**API Endpoints:**
- `GET /api/prediction/status` - Model availability and metadata
- `POST /api/prediction/train` - Train/retrain model
- `GET /api/prediction/current` - Predict from latest traffic state
- `POST /api/prediction/predict` - Predict from custom features
- `GET /api/prediction/history` - Retrieve prediction history

### 5.11. MongoDB Collection

**Collection:** `congestion_predictions`

**Fields:**
- prediction_id
- simulation_id
- intersection_id
- timestamp
- simulation_time
- horizon_seconds
- current_congestion_score
- predicted_congestion_score
- congestion_level
- model_name
- feature_version

**Indexes:**
- simulation_id + simulation_time
- timestamp
- intersection_id + timestamp

### 5.12. Limitations

This is a prototype prediction layer demonstrated on simulated traffic data. It is not claimed to represent real-world city traffic without calibration using real traffic data.

**Data Requirements:**
- Minimum 3 simulation runs
- Minimum 300 snapshots
- Minimum 100 training samples

**Current Status:**
- Infrastructure: **Complete** - All prediction components, APIs, and tests are implemented and verified.
- Model Training: **Deferred** - Current MongoDB dataset contains 110 snapshots with 0 valid training pairs (simulation duration too short for 30-second horizon).
- When sufficient historical data becomes available (longer simulations or more runs), the training pipeline is ready to execute with: `python -m prediction.train`

If insufficient data exists, training is deferred with clear reporting rather than fabricating metrics.

