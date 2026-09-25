"""TraCI Controller Interface for Eclipse SUMO.

Handles process lifecycle management, TraCI socket communication,
phase control, state extraction, and safe cleanup for traffic simulations.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import sumolib
import traci

from simulation.metrics import MetricsCalculator, SimulationMetrics
from simulation.state import ApproachState, TrafficState

logger = logging.getLogger(__name__)


class TraCIController:
    """Manages the lifecycle of a SUMO / SUMO-GUI instance via TraCI.

    Provides high-level APIs for stepping physics, querying state vectors,
    controlling traffic signals, and extracting performance telemetry.
    """

    DEFAULT_SUMOCFG = Path(__file__).resolve().parent / "sumo" / "simulation.sumocfg"

    CANDIDATE_SUMO_PATHS = [
        Path(r"C:\Program Files (x86)\Eclipse\Sumo\bin"),
        Path(r"C:\Program Files\Eclipse\Sumo\bin"),
        Path(r"C:\Eclipse\Sumo\bin"),
    ]

    PHASE_MAP = {
        0: "NS_GREEN",
        1: "NS_YELLOW",
        2: "EW_GREEN",
        3: "EW_YELLOW",
    }

    def __init__(
        self,
        sumocfg_path: Optional[Path | str] = None,
        use_gui: bool = False,
        step_length: float = 1.0,
        tls_id: str = "center",
        seed: Optional[int] = 42,
    ) -> None:
        """Initialize TraCIController instance.

        Args:
            sumocfg_path: Path to .sumocfg configuration file.
            use_gui: Whether to launch SUMO-GUI instead of headless CLI sumo.
            step_length: Simulation step duration in seconds.
            tls_id: ID of the primary signalized junction traffic light.
            seed: Random seed for deterministic vehicle routing.
        """
        self.sumocfg_path = Path(sumocfg_path) if sumocfg_path else self.DEFAULT_SUMOCFG
        self.use_gui = use_gui
        self.step_length = step_length
        self.tls_id = tls_id
        self.seed = seed

        self._is_running = False
        self._current_step = 0
        self._sim_time = 0.0
        self._last_phase = 0
        self._time_since_phase_change = 0.0

        self._metrics_calculator = MetricsCalculator()
        self._current_metrics: Optional[SimulationMetrics] = None
        self._ensure_sumo_home()

    @classmethod
    def find_sumo_binary(cls, use_gui: bool = False) -> str:
        """Locate the SUMO or SUMO-GUI binary on Windows / host system.

        Args:
            use_gui: If True, search for sumo-gui.exe; otherwise sumo.exe.

        Returns:
            str: Absolute path to the resolved executable.

        Raises:
            FileNotFoundError: If SUMO binary cannot be located.
        """
        binary_name = "sumo-gui" if use_gui else "sumo"
        exe_name = f"{binary_name}.exe" if sys.platform == "win32" else binary_name

        # 1. Check SUMO_HOME environment variable
        sumo_home = os.environ.get("SUMO_HOME")
        if sumo_home:
            home_path = Path(sumo_home)
            candidate = home_path / "bin" / exe_name
            if candidate.is_file():
                return str(candidate)
            candidate_direct = home_path / exe_name
            if candidate_direct.is_file():
                return str(candidate_direct)

        # 2. Check standard Windows installation directories
        for search_dir in cls.CANDIDATE_SUMO_PATHS:
            candidate = search_dir / exe_name
            if candidate.is_file():
                return str(candidate)

        # 3. Check system PATH via shutil.which
        which_path = shutil.which(binary_name) or shutil.which(exe_name)
        if which_path:
            return which_path

        raise FileNotFoundError(
            f"Could not locate '{exe_name}'. Please ensure Eclipse SUMO is installed and "
            f"either SUMO_HOME is set or the installation bin folder is added to PATH."
        )

    def _ensure_sumo_home(self) -> None:
        """Ensure SUMO_HOME environment variable is set to prevent XML validation warnings."""
        if not os.environ.get("SUMO_HOME"):
            for search_dir in self.CANDIDATE_SUMO_PATHS:
                parent_dir = search_dir.parent
                if (parent_dir / "bin").is_dir():
                    os.environ["SUMO_HOME"] = str(parent_dir)
                    break

    def start_simulation(self, use_gui: Optional[bool] = None) -> None:
        """Launch the SUMO simulation process and connect TraCI.

        Args:
            use_gui: Override instance use_gui configuration if provided.
        """
        if self._is_running:
            logger.warning("Simulation is already running.")
            return

        if use_gui is not None:
            self.use_gui = use_gui

        if not self.sumocfg_path.is_file():
            raise FileNotFoundError(f"SUMO config file not found: {self.sumocfg_path}")

        binary_path = self.find_sumo_binary(self.use_gui)

        sumo_cmd = [
            binary_path,
            "-c", str(self.sumocfg_path.resolve()),
            "--step-length", str(self.step_length),
            "--no-step-log", "true",
            "--waiting-time-memory", "1000",
            "--time-to-teleport", "-1",
        ]

        if self.seed is not None:
            sumo_cmd.extend(["--seed", str(self.seed)])

        if self.use_gui:
            sumo_cmd.extend(["--start", "--quit-on-end", "true"])

        try:
            traci.start(sumo_cmd)
            self._is_running = True
            self._current_step = 0
            self._sim_time = float(traci.simulation.getTime())
            self._metrics_calculator.reset()
            self._last_phase = self.get_tls_phase()
            self._time_since_phase_change = 0.0
            logger.info("SUMO simulation started successfully via TraCI (%s).", "GUI" if self.use_gui else "CLI")
        except Exception as e:
            self._is_running = False
            logger.error("Failed to start SUMO simulation: %s", e)
            raise

    def step_simulation(self) -> TrafficState:
        """Advance the simulation by one time step and return the updated TrafficState.

        Returns:
            TrafficState: Snapshot of traffic state after step.
        """
        if not self._is_running:
            raise RuntimeError("Cannot step simulation: TraCI is not running.")

        traci.simulationStep()
        self._current_step += 1
        self._sim_time = float(traci.simulation.getTime())

        current_phase = self.get_tls_phase()
        if current_phase == self._last_phase:
            self._time_since_phase_change += self.step_length
        else:
            self._last_phase = current_phase
            self._time_since_phase_change = 0.0

        # Compute and record step metrics in metrics calculator
        self._current_metrics = self._metrics_calculator.compute(
            traci_module=traci,
            tls_id=self.tls_id,
            step=self._current_step,
            sim_time=self._sim_time,
            time_since_phase_change=self._time_since_phase_change,
        )

        return self.get_current_state()

    def get_tls_phase(self) -> int:
        """Get the current traffic light phase index of the central junction."""
        if not self._is_running:
            return 0
        try:
            return int(traci.trafficlight.getPhase(self.tls_id))
        except Exception:
            return 0

    def set_tls_phase(self, phase_index: int) -> None:
        """Set the traffic light phase of the central junction.

        Args:
            phase_index: Index of the target phase (0: NS_GREEN, 1: NS_YELLOW, 2: EW_GREEN, 3: EW_YELLOW).
        """
        if not self._is_running:
            raise RuntimeError("Cannot set TLS phase: Simulation is not running.")
        traci.trafficlight.setPhase(self.tls_id, phase_index)
        if phase_index != self._last_phase:
            self._last_phase = phase_index
            self._time_since_phase_change = 0.0

    def get_current_state(self) -> TrafficState:
        """Extract and return the instantaneous TrafficState representation."""
        if not self._is_running:
            return TrafficState()

        # Approach edges
        approach_configs = {
            "north": "N2C",
            "south": "S2C",
            "east": "E2C",
            "west": "W2C",
        }

        approach_states: Dict[str, ApproachState] = {}
        total_veh = 0
        total_queue = 0
        total_wait = 0.0
        total_speed = 0.0

        active_veh_ids = traci.vehicle.getIDList()
        total_active_vehicles = len(active_veh_ids)

        for veh_id in active_veh_ids:
            try:
                total_speed += traci.vehicle.getSpeed(veh_id)
                total_wait += traci.vehicle.getWaitingTime(veh_id)
            except Exception:
                continue

        avg_speed = (total_speed / total_active_vehicles) if total_active_vehicles > 0 else 0.0

        for direction, edge_id in approach_configs.items():
            try:
                veh_count = traci.edge.getLastStepVehicleNumber(edge_id)
                queue_len = traci.edge.getLastStepHaltingNumber(edge_id)
                wait_time = float(traci.edge.getWaitingTime(edge_id))
                mean_spd = float(traci.edge.getLastStepMeanSpeed(edge_id))
            except Exception:
                veh_count = 0
                queue_len = 0
                wait_time = 0.0
                mean_spd = 0.0

            approach_states[direction] = ApproachState(
                direction=direction,
                inflow_edge=edge_id,
                vehicle_count=veh_count,
                queue_length=queue_len,
                waiting_time=wait_time,
                mean_speed=round(mean_spd, 2),
            )
            total_queue += queue_len

        phase_idx = self.get_tls_phase()
        phase_name = self.PHASE_MAP.get(phase_idx, f"PHASE_{phase_idx}")

        return TrafficState(
            simulation_time=self._sim_time,
            step=self._current_step,
            north=approach_states.get("north", ApproachState(direction="north", inflow_edge="N2C")),
            south=approach_states.get("south", ApproachState(direction="south", inflow_edge="S2C")),
            east=approach_states.get("east", ApproachState(direction="east", inflow_edge="E2C")),
            west=approach_states.get("west", ApproachState(direction="west", inflow_edge="W2C")),
            total_vehicles=total_active_vehicles,
            total_queue=total_queue,
            total_waiting_time=round(total_wait, 2),
            average_speed=round(avg_speed, 2),
            current_phase=phase_idx,
            current_phase_name=phase_name,
            time_since_phase_change=round(self._time_since_phase_change, 1),
        )

    def get_metrics(self) -> SimulationMetrics:
        """Extract and compute consolidated simulation metrics."""
        if not self._is_running:
            return SimulationMetrics()

        if self._current_metrics is not None:
            return self._current_metrics

        self._current_metrics = self._metrics_calculator.compute(
            traci_module=traci,
            tls_id=self.tls_id,
            step=self._current_step,
            sim_time=self._sim_time,
            time_since_phase_change=self._time_since_phase_change,
        )
        return self._current_metrics

    def get_aggregate_metrics(self):
        """Retrieve aggregated summary metrics computed across the entire simulation run."""
        return self._metrics_calculator.get_aggregate_summary()

    def is_running(self) -> bool:
        """Check if TraCI simulation is actively running."""
        return self._is_running

    def close_simulation(self) -> None:
        """Safely terminate the simulation and close TraCI socket connection."""
        if not self._is_running:
            return

        try:
            traci.close()
            logger.info("TraCI connection closed successfully.")
        except Exception as e:
            logger.warning("TraCI close encountered non-fatal error: %s", e)
        finally:
            self._is_running = False

    def __enter__(self) -> TraCIController:
        self.start_simulation()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close_simulation()
