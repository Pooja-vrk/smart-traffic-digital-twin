"""Telemetry transformation service for converting simulation states to API payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.schemas.traffic import (
    AIDecisionInfo,
    QueuesInfo,
    SignalInfo,
    SpeedInfo,
    TrafficSnapshotResponse,
    VehiclesInfo,
    WaitingInfo,
)
from backend.schemas.websocket import WebSocketMessage
from simulation.controllers.base_controller import BaseController
from simulation.controllers.dqn_controller import DQNController
from simulation.metrics import SimulationMetrics
from simulation.state import TrafficState


class TelemetryService:
    """Encapsulates transformations from raw TraCI/controller dataclasses to public API telemetry."""

    PHASE_STATE_MAP = {
        0: ("NORTH_SOUTH_GREEN", "green"),
        1: ("NORTH_SOUTH_YELLOW", "yellow"),
        2: ("EAST_WEST_GREEN", "green"),
        3: ("EAST_WEST_YELLOW", "yellow"),
    }

    @classmethod
    def create_snapshot(
        cls,
        state: TrafficState,
        metrics: Optional[SimulationMetrics],
        controller: Optional[BaseController],
        simulation_id: Optional[str] = None,
        peak_queue: int = 0,
    ) -> TrafficSnapshotResponse:
        """Construct a standardized TrafficSnapshotResponse from live simulation state and metrics."""
        phase_idx = state.current_phase
        phase_name, phase_state = cls.PHASE_STATE_MAP.get(phase_idx, ("UNKNOWN", "green"))

        # Vehicles count
        total_veh = state.total_vehicles
        entered_veh = metrics.total_vehicles if metrics else total_veh
        completed_veh = metrics.throughput if metrics else 0

        # Queues
        q_north = state.north.queue_length
        q_south = state.south.queue_length
        q_east = state.east.queue_length
        q_west = state.west.queue_length
        q_total = state.total_queue
        q_peak = max(peak_queue, q_total)

        # Speed and waiting
        avg_speed = state.average_speed
        tot_wait = state.total_waiting_time
        avg_wait = (tot_wait / total_veh) if total_veh > 0 else 0.0

        # AI Info if DQN controller active
        ai_info: Optional[AIDecisionInfo] = None
        controller_name = controller.name if controller else "Unknown"

        if isinstance(controller, DQNController):
            stats = controller.get_stats()
            last_action_id = stats.get("last_selected_action", 0)
            last_action_name = stats.get("last_action_name", "KEEP")
            
            # Action to requested phase
            req_phase = 0 if last_action_id == 1 else (2 if last_action_id == 2 else phase_idx)
            approved = (state.current_phase == req_phase) if last_action_id in {1, 2} else True

            ai_info = AIDecisionInfo(
                action=last_action_name,
                action_id=last_action_id,
                requested_phase=req_phase,
                approved=approved,
                reason=f"DQN policy selected action {last_action_name}",
            )

        return TrafficSnapshotResponse(
            simulation_id=simulation_id,
            simulation_time=state.simulation_time,
            step=state.step,
            controller=controller_name,
            vehicles=VehiclesInfo(
                total=total_veh,
                entered=entered_veh,
                completed=completed_veh,
            ),
            queues=QueuesInfo(
                north=q_north,
                south=q_south,
                east=q_east,
                west=q_west,
                total=q_total,
                peak=q_peak,
            ),
            speed=SpeedInfo(average_mps=round(avg_speed, 2)),
            waiting=WaitingInfo(
                average_seconds=round(avg_wait, 2),
                total_seconds=round(tot_wait, 2),
            ),
            signal=SignalInfo(
                phase_index=phase_idx,
                phase_name=phase_name,
                state=phase_state,
                elapsed_seconds=round(state.time_since_phase_change, 2),
            ),
            ai=ai_info,
        )

    @classmethod
    def create_websocket_message(
        cls,
        msg_type: str,
        data: Dict[str, Any],
        simulation_id: Optional[str] = None,
    ) -> WebSocketMessage:
        """Build a typed WebSocket message packet."""
        return WebSocketMessage(
            type=msg_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            simulation_id=simulation_id,
            data=data,
        )
