"""Scenario Demand Generator for Eclipse SUMO Digital Twin.

Generates reproducible, deterministic SUMO route (.rou.xml) and configuration
(.sumocfg) files based on parametric traffic demand specifications.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SUMO_DIR = Path(__file__).resolve().parent / "sumo"
SCENARIOS_DIR = SUMO_DIR / "scenarios"


@dataclass
class DirectionBias:
    """Directional traffic distribution percentages (must sum to 100)."""
    north: float = 25.0
    south: float = 25.0
    east: float = 25.0
    west: float = 25.0

    def validate(self) -> None:
        """Validate directional distribution sums to 100% within tolerance."""
        total = self.north + self.south + self.east + self.west
        if not (99.0 <= total <= 101.0):
            raise ValueError(f"Direction percentages must sum to 100%. Current sum: {total:.1f}%")
        for direction, val in [("north", self.north), ("south", self.south), ("east", self.east), ("west", self.west)]:
            if val < 0.0 or val > 100.0:
                raise ValueError(f"Direction '{direction}' percentage must be between 0 and 100. Got: {val}")

    def to_dict(self) -> Dict[str, float]:
        return {
            "north": round(self.north, 1),
            "south": round(self.south, 1),
            "east": round(self.east, 1),
            "west": round(self.west, 1),
        }


@dataclass
class ScenarioConfig:
    """Parametric scenario specification."""
    name: str = "Balanced Traffic"
    density: str = "medium"  # low, medium, high, very_high, custom
    multiplier: float = 1.0  # 0.2x to 3.0x
    direction_bias: DirectionBias = field(default_factory=DirectionBias)
    duration: int = 300  # seconds
    seed: int = 42
    emergency_vehicle: bool = False
    emergency_approach: str = "east"  # 'north', 'south', 'east', 'west'
    emergency_step: int = 15
    emergency_vehicle_type: str = "ambulance"  # 'ambulance', 'fire_engine', 'emergency_vehicle'

    DENSITY_MULTIPLIERS = {
        "low": 0.5,
        "medium": 1.0,
        "high": 1.5,
        "very_high": 2.0,
    }

    BASE_TOTAL_HOURLY_VEHICLES: int = 2400

    def get_effective_multiplier(self) -> float:
        """Get the effective demand multiplier."""
        if self.density in self.DENSITY_MULTIPLIERS:
            return self.DENSITY_MULTIPLIERS[self.density]
        return max(0.2, min(3.0, self.multiplier))

    def compute_hash(self) -> str:
        """Compute unique deterministic hash for scenario parameters."""
        data = {
            "density": self.density,
            "multiplier": round(self.get_effective_multiplier(), 3),
            "direction_bias": self.direction_bias.to_dict(),
            "duration": self.duration,
            "seed": self.seed,
            "emergency_vehicle": self.emergency_vehicle,
            "emergency_approach": self.emergency_approach,
            "emergency_step": self.emergency_step,
            "emergency_vehicle_type": self.emergency_vehicle_type,
        }
        raw = json.dumps(data, sort_keys=True)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "density": self.density,
            "multiplier": round(self.get_effective_multiplier(), 2),
            "direction_bias": self.direction_bias.to_dict(),
            "duration": self.duration,
            "seed": self.seed,
            "emergency_vehicle": self.emergency_vehicle,
            "emergency_approach": self.emergency_approach,
            "emergency_step": self.emergency_step,
            "emergency_vehicle_type": self.emergency_vehicle_type,
        }


class ScenarioDemandGenerator:
    """Generates deterministic SUMO route XML and SUMO config files for scenarios."""

    @staticmethod
    def ensure_scenarios_dir() -> Path:
        """Ensure the scenarios directory exists."""
        SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
        return SCENARIOS_DIR

    @classmethod
    def generate_scenario_files(cls, config: ScenarioConfig) -> Tuple[Path, Path]:
        """Generate deterministic route XML and sumocfg files for the given scenario configuration.

        Args:
            config: The scenario configuration parameters.

        Returns:
            Tuple[Path, Path]: (route_file_path, sumocfg_file_path)
        """
        config.direction_bias.validate()
        cls.ensure_scenarios_dir()

        scenario_hash = config.compute_hash()
        route_filename = f"scenario_{scenario_hash}.rou.xml"
        sumocfg_filename = f"scenario_{scenario_hash}.sumocfg"

        route_path = SCENARIOS_DIR / route_filename
        sumocfg_path = SCENARIOS_DIR / sumocfg_filename

        # Generate route XML
        route_content = cls._build_route_xml(config)
        with open(route_path, "w", encoding="utf-8") as f:
            f.write(route_content)

        # Generate sumocfg XML
        sumocfg_content = cls._build_sumocfg_xml(route_filename, config.duration)
        with open(sumocfg_path, "w", encoding="utf-8") as f:
            f.write(sumocfg_content)

        logger.info("Generated scenario files: %s and %s", route_path.name, sumocfg_path.name)
        return route_path, sumocfg_path

    @classmethod
    def _build_route_xml(cls, config: ScenarioConfig) -> str:
        """Construct the XML content for scenario vehicle flows."""
        effective_mult = config.get_effective_multiplier()
        total_veh_per_hour = config.BASE_TOTAL_HOURLY_VEHICLES * effective_mult
        duration_sec = max(3600, config.duration + 600)  # Ensure flows extend beyond simulation duration

        bias = config.direction_bias
        n_flow = total_veh_per_hour * (bias.north / 100.0)
        s_flow = total_veh_per_hour * (bias.south / 100.0)
        e_flow = total_veh_per_hour * (bias.east / 100.0)
        w_flow = total_veh_per_hour * (bias.west / 100.0)

        # Flow allocations per direction:
        # Straight: 65%
        # Right turn: 15%
        # Left turn: 12%
        # Heavy trucks (straight): 8%
        def calc_flows(total_dir_flow: float) -> Tuple[int, int, int, int]:
            straight = max(1, int(round(total_dir_flow * 0.65)))
            right = max(0, int(round(total_dir_flow * 0.15)))
            left = max(0, int(round(total_dir_flow * 0.12)))
            truck = max(0, int(round(total_dir_flow * 0.08)))
            return straight, right, left, truck

        n_str, n_rt, n_lt, n_trk = calc_flows(n_flow)
        s_str, s_rt, s_lt, s_trk = calc_flows(s_flow)
        e_str, e_rt, e_lt, e_trk = calc_flows(e_flow)
        w_str, w_rt, w_lt, w_trk = calc_flows(w_flow)

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated Traffic Demand for Scenario: {config.name} (Multiplier: {effective_mult:.2f}x, Seed: {config.seed}) -->
<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">
    <!-- Vehicle Type Definitions -->
    <vType id="standard_car"
           accel="2.6"
           decel="4.5"
           sigma="0.5"
           length="5.0"
           minGap="2.5"
           maxSpeed="13.89"
           color="0,0.6,0.9"/>

    <vType id="heavy_vehicle"
           accel="1.5"
           decel="3.5"
           sigma="0.5"
           length="8.5"
           minGap="3.0"
           maxSpeed="11.11"
           color="0.9,0.5,0.1"/>

    <vType id="emergency_vehicle"
           accel="3.5"
           decel="5.0"
           sigma="0.2"
           length="6.5"
           minGap="2.0"
           maxSpeed="22.22"
           color="1.0,0.1,0.1"
           vClass="emergency"
           guiShape="emergency"/>

    <vType id="ambulance"
           accel="3.5"
           decel="5.0"
           sigma="0.2"
           length="6.5"
           minGap="2.0"
           maxSpeed="22.22"
           color="1.0,0.1,0.1"
           vClass="emergency"
           guiShape="emergency"/>

    <vType id="fire_engine"
           accel="2.8"
           decel="4.5"
           sigma="0.2"
           length="8.5"
           minGap="2.5"
           maxSpeed="20.0"
           color="0.9,0.2,0.1"
           vClass="emergency"
           guiShape="firebrigade"/>

    <!-- Route Definitions -->
    <!-- Straight Movements -->
    <route id="r_NS" edges="N2C C2S"/>
    <route id="r_SN" edges="S2C C2N"/>
    <route id="r_EW" edges="E2C C2W"/>
    <route id="r_WE" edges="W2C C2E"/>

    <!-- Turning Movements -->
    <route id="r_NW" edges="N2C C2W"/>
    <route id="r_NE" edges="N2C C2E"/>
    <route id="r_SE" edges="S2C C2E"/>
    <route id="r_SW" edges="S2C C2W"/>
    <route id="r_EN" edges="E2C C2N"/>
    <route id="r_ES" edges="E2C C2S"/>
    <route id="r_WS" edges="W2C C2S"/>
    <route id="r_WN" edges="W2C C2N"/>

    <!-- Standard Vehicle Flows (begin=0) -->
    <!-- North Approach -->
    <flow id="flow_NS" type="standard_car" route="r_NS" begin="0" end="{duration_sec}" vehsPerHour="{n_str}" departLane="best" departSpeed="max"/>
    <flow id="flow_NW" type="standard_car" route="r_NW" begin="0" end="{duration_sec}" vehsPerHour="{n_rt}" departLane="best" departSpeed="max"/>
    <flow id="flow_NE" type="standard_car" route="r_NE" begin="0" end="{duration_sec}" vehsPerHour="{n_lt}" departLane="best" departSpeed="max"/>

    <!-- South Approach -->
    <flow id="flow_SN" type="standard_car" route="r_SN" begin="0" end="{duration_sec}" vehsPerHour="{s_str}" departLane="best" departSpeed="max"/>
    <flow id="flow_SE" type="standard_car" route="r_SE" begin="0" end="{duration_sec}" vehsPerHour="{s_rt}" departLane="best" departSpeed="max"/>
    <flow id="flow_SW" type="standard_car" route="r_SW" begin="0" end="{duration_sec}" vehsPerHour="{s_lt}" departLane="best" departSpeed="max"/>

    <!-- East Approach -->
    <flow id="flow_EW" type="standard_car" route="r_EW" begin="0" end="{duration_sec}" vehsPerHour="{e_str}" departLane="best" departSpeed="max"/>
    <flow id="flow_EN" type="standard_car" route="r_EN" begin="0" end="{duration_sec}" vehsPerHour="{e_rt}" departLane="best" departSpeed="max"/>
    <flow id="flow_ES" type="standard_car" route="r_ES" begin="0" end="{duration_sec}" vehsPerHour="{e_lt}" departLane="best" departSpeed="max"/>

    <!-- West Approach -->
    <flow id="flow_WE" type="standard_car" route="r_WE" begin="0" end="{duration_sec}" vehsPerHour="{w_str}" departLane="best" departSpeed="max"/>
    <flow id="flow_WS" type="standard_car" route="r_WS" begin="0" end="{duration_sec}" vehsPerHour="{w_rt}" departLane="best" departSpeed="max"/>
    <flow id="flow_WN" type="standard_car" route="r_WN" begin="0" end="{duration_sec}" vehsPerHour="{w_lt}" departLane="best" departSpeed="max"/>

    <!-- Heavy Vehicle Flows (begin=5) -->
    <flow id="flow_truck_NS" type="heavy_vehicle" route="r_NS" begin="5" end="{duration_sec}" vehsPerHour="{n_trk}" departLane="best" departSpeed="max"/>
    <flow id="flow_truck_SN" type="heavy_vehicle" route="r_SN" begin="5" end="{duration_sec}" vehsPerHour="{s_trk}" departLane="best" departSpeed="max"/>
    <flow id="flow_truck_EW" type="heavy_vehicle" route="r_EW" begin="5" end="{duration_sec}" vehsPerHour="{e_trk}" departLane="best" departSpeed="max"/>
    <flow id="flow_truck_WE" type="heavy_vehicle" route="r_WE" begin="5" end="{duration_sec}" vehsPerHour="{w_trk}" departLane="best" departSpeed="max"/>
    {f'    <vehicle id="EV_01" type="{config.emergency_vehicle_type or "ambulance"}" route="{"r_NS" if config.emergency_approach=="north" else ("r_SN" if config.emergency_approach=="south" else ("r_EW" if config.emergency_approach=="east" else "r_WE"))}" depart="{config.emergency_step}.0" departLane="best" departSpeed="max"/>' if config.emergency_vehicle else ''}
</routes>
"""
        return xml

    @classmethod
    def _build_sumocfg_xml(cls, route_filename: str, duration: int) -> str:
        """Construct the XML content for scenario SUMO configuration."""
        sim_end = max(3600, duration + 600)
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">
    <input>
        <net-file value="../intersection.net.xml"/>
        <route-files value="{route_filename}"/>
        <gui-settings-file value="../gui-settings.xml"/>
    </input>

    <time>
        <begin value="0"/>
        <end value="{sim_end}"/>
        <step-length value="1.0"/>
    </time>

    <processing>
        <time-to-teleport value="-1"/>
        <collision.action value="none"/>
    </processing>

    <report>
        <verbose value="false"/>
        <no-step-log value="true"/>
    </report>

    <gui_only>
        <start value="true"/>
        <quit-on-end value="false"/>
    </gui_only>
</configuration>
"""
        return xml
