"""Telemetry transformation service for converting simulation states to API payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.schemas.traffic import (
    AIDecisionInfo,
    EmergencyLiveInfo,
    PredictionLiveInfo,
    QueuesInfo,
    SignalInfo,
    SpeedInfo,
    TrafficSnapshotResponse,
    VehicleLiveState,
    VehiclesInfo,
    WaitingInfo,
)
from backend.schemas.websocket import WebSocketMessage
from prediction.predictor import predictor
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
        agentic_decision: Optional[Any] = None,
    ) -> TrafficSnapshotResponse:
        """Construct a standardized TrafficSnapshotResponse from live simulation state and metrics."""
        phase_idx = state.current_phase
        phase_name, phase_state = cls.PHASE_STATE_MAP.get(phase_idx, ("UNKNOWN", "green"))

        # Vehicles count
        total_veh = state.total_vehicles
        entered_veh = metrics.total_vehicles if metrics else total_veh
        completed_veh = metrics.throughput if metrics else 0

        # Convert live vehicle states
        live_veh_list = [
            VehicleLiveState(
                id=v.id,
                x=v.x,
                y=v.y,
                angle=v.angle,
                speed=v.speed,
                lane_id=v.lane_id,
                edge_id=v.edge_id,
                waiting_time=v.waiting_time,
                vehicle_type=v.vehicle_type,
                length=v.length,
                width=v.width,
            )
            for v in (state.vehicles or [])
        ]

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

        # AI Info: populates from AgenticTrafficEngine decision or legacy DQN stats
        ai_info: Optional[AIDecisionInfo] = None
        controller_name = controller.name if controller else "Unknown"

        if agentic_decision is not None:
            action_name = getattr(agentic_decision, "requested_action", "KEEP")
            req_phase = getattr(agentic_decision, "requested_phase", phase_idx)
            val_action = getattr(agentic_decision, "validated_action", "APPROVED")
            q_vals = getattr(agentic_decision, "q_values", None) or []
            reward_val = getattr(agentic_decision, "reward", None)
            reason_str = getattr(agentic_decision, "decision_reason", None)
            dec_time = getattr(agentic_decision, "simulation_time", state.simulation_time)

            # Determine action_id (0: KEEP, 1: REQ_NS, 2: REQ_EW)
            if isinstance(controller, DQNController):
                stats = controller.get_stats()
                last_act_id = stats.get("last_selected_action", 0)
                norm_feat = stats.get("normalized_state", [])
            else:
                norm_feat = []
                if "NORTH_SOUTH" in action_name or "NS" in action_name:
                    last_act_id = 1
                elif "EAST_WEST" in action_name or "EW" in action_name:
                    last_act_id = 2
                else:
                    last_act_id = 0

            ai_info = AIDecisionInfo(
                action=action_name,
                action_id=last_act_id,
                requested_phase=req_phase,
                approved=(val_action == "APPROVED"),
                reason=reason_str,
                q_values=q_vals,
                normalized_state=norm_feat,
                reward=reward_val,
                decision_time=dec_time,
            )
        elif isinstance(controller, DQNController):
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
                q_values=stats.get("q_values", []),
                normalized_state=stats.get("normalized_state", []),
                reward=stats.get("reward"),
                decision_time=state.simulation_time,
            )

        # Emergency vehicle live info
        emergency_info: Optional[EmergencyLiveInfo] = None
        ev = state.emergency
        if ev and ev.active:
            emergency_info = EmergencyLiveInfo(
                active=True,
                vehicle_id=ev.vehicle_id,
                vehicle_type=ev.vehicle_type,
                approach=ev.approach,
                state=ev.state,
                distance=ev.distance,
                distance_to_stopline=ev.distance_to_stopline,
                lane_id=getattr(ev, "lane_id", None),
                edge_id=getattr(ev, "edge_id", None),
                speed=ev.speed,
                eta_seconds=ev.eta_seconds,
                priority_requested=ev.priority_requested,
                priority_approved=ev.priority_approved,
                priority_active=ev.priority_active,
                priority_duration=getattr(ev, "priority_duration", 0.0),
                lifecycle_state=getattr(ev, "lifecycle_state", ev.state),
                safety_status=ev.safety_status,
                current_action=ev.current_action,
                reason=ev.reason,
                entry_time=ev.entry_time,
                exit_time=ev.exit_time,
                travel_time=ev.travel_time,
                delay_seconds=ev.delay_seconds,
            )

        # Real-time predictive intelligence (30-second horizon)
        prediction_info: Optional[PredictionLiveInfo] = None
        try:
            snapshot_dict = {
                "simulation_id": simulation_id,
                "simulation_time": state.simulation_time,
                "step": state.step,
                "controller": controller_name,
                "queues": {
                    "north": q_north,
                    "south": q_south,
                    "east": q_east,
                    "west": q_west,
                    "total": q_total,
                },
                "waiting": {
                    "average_seconds": round(avg_wait, 2),
                    "total_seconds": round(tot_wait, 2),
                },
                "speed": {
                    "average_mps": round(avg_speed, 2),
                },
                "signal": {
                    "phase_index": phase_idx,
                    "elapsed_seconds": round(state.time_since_phase_change, 2),
                },
            }
            prediction_info = predictor.predict_live(
                snapshot=snapshot_dict,
                simulation_id=simulation_id,
                step=state.step,
                simulation_time=state.simulation_time,
            )
        except Exception:
            prediction_info = PredictionLiveInfo(model_available=False)

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
            vehicles_data=live_veh_list,
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
                raw_state=state.signal_raw_state,
                elapsed_seconds=round(state.time_since_phase_change, 2),
            ),
            ai=ai_info,
            emergency=emergency_info,
            prediction=prediction_info,
            decision=agentic_decision.to_dict() if agentic_decision is not None and hasattr(agentic_decision, "to_dict") else None,
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
