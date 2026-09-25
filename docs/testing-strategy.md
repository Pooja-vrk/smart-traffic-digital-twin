# Testing Strategy Document

## 1. Scope and Objectives
Ensure high reliability, mathematical correctness of traffic telemetry calculations, stability of reinforcement learning algorithms, and robust API endpoints.

## 2. Testing Levels

### 2.1. Unit & Integration Tests (`tests/`)
- `test_simulation.py` (6 tests): Validates binary resolution, asset existence, state extraction, and headless TraCI stepping.
- `test_controllers.py` (9 tests): Validates Fixed-Time, Adaptive, SignalSafetyManager transition enforcement, minimum green constraints, metric consistency, and experiment reproducibility.
- `test_ai.py` (9 tests): Validates DQN neural network architecture, replay buffer operations, $\epsilon$-greedy action selection, target network sync, reward calculator, checkpoint save/load, missing checkpoint error handling, RL environment stepping, and DQN controller safety manager integration.

### 2.2. Test Execution Command
```powershell
python -m pytest -v tests/
```

### 2.3. Current Status
- **24 of 24 tests passing (100% pass rate)**.

