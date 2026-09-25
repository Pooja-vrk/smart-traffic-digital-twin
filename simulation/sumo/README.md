# SUMO Simulation Foundation — 4-Way Urban Intersection

## 1. Overview & Digital Twin Concept
This directory contains the microscopic traffic simulation assets for the **AI-Driven Digital Twin for Smart City Traffic Flow Management** project.

The SUMO (Simulation of Urban MObility) environment serves as the foundational physical reality simulation layer for the Digital Twin architecture:

```text
+-------------------------------------------------------------+
|               Eclipse SUMO Traffic Simulation               |
|      (Vehicles, Lane Queues, Speeds, Traffic Light State)   |
+------------------------------+------------------------------+
                               |
                               v  TraCI Protocol (TCP / API)
+-------------------------------------------------------------+
|             Python TraCI Controller & Extractor             |
|                  (simulation/traci_controller.py)           |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|             Traffic State & Metric Aggregation              |
|           (simulation/state.py, simulation/metrics.py)      |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|        Signal Controller & SignalSafetyManager Layer        |
|  - Fixed-Time Controller (FixedTimeController)             |
|  - Rule-Based Adaptive Controller (AdaptiveController)       |
|  - Future Deep Q-Network Agent (Step 4)                     |
+-------------------------------------------------------------+
```

---

## 2. Intersection Geometry & Network Design

- **Topology**: Symmetrical 4-way urban crossroads with a central signalized junction (`center`).
- **Arm Lengths**: 300 meters per approach (North, South, East, West) providing ample spatial capacity to observe realistic queue formations and shockwave propagation.
- **Lane Allocation**: 2 lanes per approach (speed limit: 50 km/h / 13.89 m/s):
  - **Lane 0 (Outer)**: Right-turn and through traffic.
  - **Lane 1 (Inner)**: Through and left-turn traffic.

### Edge Mapping
| Approach | Inflow Edge (to Center) | Outflow Edge (from Center) | Incoming Lanes |
| :--- | :--- | :--- | :--- |
| **North** | `N2C` | `C2N` | `N2C_0`, `N2C_1` |
| **South** | `S2C` | `C2S` | `S2C_0`, `S2C_1` |
| **East** | `E2C` | `C2E` | `E2C_0`, `E2C_1` |
| **West** | `W2C` | `C2W` | `W2C_0`, `W2C_1` |

---

## 3. Signal Controllers & Safety Architecture

### 3.1. Standardized Queue Definition
Across all controllers and metrics calculations, a vehicle is strictly classified as **queued** if:
- It is located on an inflow approach edge (`N2C`, `S2C`, `E2C`, `W2C`).
- Its instantaneous speed is **$< 0.1 \text{ m/s}$** (halting threshold).

### 3.2. Signal Safety Manager (`SignalSafetyManager`)
Every control strategy (Fixed-Time, Adaptive, DQN) interfaces with `SignalSafetyManager`, which enforces:
1. **Minimum Green Time**: Green phases cannot be preempted before `min_green_seconds` (default: 10s).
2. **Maximum Green Time**: Green phases are capped at `max_green_seconds` (default: 60s) to prevent starvation.
3. **Mandatory Yellow Clearance**: Opposing green phases can never switch instantaneously; transitions require a full yellow clearance (default: 3s).
4. **Transition Sequence**:
   - `NS_GREEN (0)` $\rightarrow$ `NS_YELLOW (1)` $\rightarrow$ `EW_GREEN (2)`
   - `EW_GREEN (2)` $\rightarrow$ `EW_YELLOW (3)` $\rightarrow$ `NS_GREEN (0)`

### 3.3. Controller Algorithms
- **Fixed-Time (`FixedTimeController`)**: Deterministic time-split signal program cycling preset green/yellow phases.
- **Rule-Based Adaptive (`AdaptiveController`)**: Actuated logic computing real-time queue pressure ($Q_{\text{NS}} = Q_N + Q_S$, $Q_{\text{EW}} = Q_E + Q_W$) and switching when pressure differentials exceed a configurable threshold.

---

## 4. Traffic Demand & Flows

Traffic demand is defined deterministically in `routes.rou.xml` with realistic asymmetric flow rates:
- **North-South Corridor**: Moderate-heavy flow (750 veh/hr per direction).
- **East-West Corridor**: Moderate flow (450 veh/hr per direction).
- **Turning Movements**: Right turns (80–120 veh/hr) and left turns (70–100 veh/hr).
- **Vehicle Composition**: Standard passenger cars (`standard_car`) and heavy commercial vehicles (`heavy_vehicle`).

---

## 5. Experiment Execution Commands

```powershell
# Run Fixed-Time Controller experiment (500 steps)
python scripts/run_experiment.py --controller fixed --steps 500

# Run Adaptive Controller experiment (500 steps)
python scripts/run_experiment.py --controller adaptive --steps 500

# Run Side-by-Side Controller Benchmark Comparison
python scripts/compare_controllers.py --steps 500 --seed 42
```

---

## 6. File Manifest

- `intersection.nod.xml`: Node definitions (center junction and 4 peripheral nodes).
- `intersection.edg.xml`: Edge definitions with speed limits, lane counts, and priorities.
- `intersection.net.xml`: Generated road network compiled via SUMO `netconvert`.
- `routes.rou.xml`: Vehicle types, routes, and traffic flow schedules.
- `simulation.sumocfg`: Master SUMO configuration file.
- `gui-settings.xml`: Viewport and rendering settings for SUMO-GUI.
