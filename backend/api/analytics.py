"""Analytics and historical metrics comparison endpoints."""

from __future__ import annotations

import logging
from typing import Optional

import pymongo
from fastapi import APIRouter, Query

from backend.database.connection import db_manager
from backend.database.repositories.traffic_repository import TrafficRepository
from backend.schemas.analytics import (
    AnalyticsSummaryResponse,
    CongestionDistributionResponse,
    ControllerComparisonResponse,
    ControllerPerformanceResponse,
    TrafficTrendPoint,
    TrafficTrendsResponse,
)
from backend.services.persistence_service import PersistenceService
from prediction.congestion import build_congestion_score, classify_congestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Platform Analytics Summary",
)
async def get_analytics_summary() -> AnalyticsSummaryResponse:
    """Retrieve high-level summary KPIs and distribution of completed simulation runs from MongoDB."""
    summary_data = PersistenceService.get_analytics_summary()
    return AnalyticsSummaryResponse(**summary_data)


@router.get(
    "/controller-comparison",
    response_model=ControllerComparisonResponse,
    summary="Comparative Controller Performance",
)
async def get_controller_comparison() -> ControllerComparisonResponse:
    """Retrieve comparative performance benchmarks grouped across Fixed-Time, Adaptive, and DQN controllers."""
    comparison_data = PersistenceService.get_controller_comparison()
    return ControllerComparisonResponse(**comparison_data)


@router.get(
    "/congestion-distribution",
    response_model=CongestionDistributionResponse,
    summary="Congestion Level Distribution",
)
async def get_congestion_distribution(
    simulation_id: Optional[str] = Query(None, description="Filter by specific simulation ID"),
    limit: int = Query(1000, description="Maximum number of snapshots to analyze"),
) -> CongestionDistributionResponse:
    """
    Retrieve distribution of congestion levels across historical traffic snapshots.

    Calculates congestion scores for snapshots and classifies them into levels.
    """
    if not db_manager.is_available or db_manager.sync_db is None:
        return CongestionDistributionResponse(
            congestion_levels={},
            total_snapshots=0,
            percentage_distribution={}
        )

    try:
        # Get snapshots
        if simulation_id:
            snapshots = TrafficRepository.get_snapshots(simulation_id, limit=limit)
        else:
            # Get recent snapshots across all simulations
            cursor = (
                db_manager.sync_db.traffic_snapshots.find({}, {"_id": 0})
                .sort("timestamp", pymongo.DESCENDING)
                .limit(limit)
            )
            snapshots = list(cursor)

        # Calculate congestion distribution
        distribution = {
            "FREE_FLOW": 0,
            "LOW": 0,
            "MODERATE": 0,
            "HIGH": 0,
            "SEVERE": 0,
        }

        for snapshot in snapshots:
            try:
                score = build_congestion_score(snapshot)
                level = classify_congestion(score)
                distribution[level] = distribution.get(level, 0) + 1
            except Exception as exc:
                logger.debug("Failed to calculate congestion for snapshot: %s", exc)
                continue

        total = sum(distribution.values())
        percentage = {
            level: (count / total * 100) if total > 0 else 0.0
            for level, count in distribution.items()
        }

        return CongestionDistributionResponse(
            congestion_levels=distribution,
            total_snapshots=total,
            percentage_distribution=percentage,
        )

    except Exception as exc:
        logger.warning("Failed to calculate congestion distribution: %s", exc)
        return CongestionDistributionResponse(
            congestion_levels={},
            total_snapshots=0,
            percentage_distribution={}
        )


@router.get(
    "/traffic-trends",
    response_model=TrafficTrendsResponse,
    summary="Traffic Trends Time Series",
)
async def get_traffic_trends(
    simulation_id: Optional[str] = Query(None, description="Filter by specific simulation ID"),
    limit: int = Query(300, description="Maximum number of data points"),
) -> TrafficTrendsResponse:
    """
    Retrieve time-series data for traffic metrics.

    Returns queue, speed, throughput, waiting time, and congestion over time.
    """
    if not db_manager.is_available or db_manager.sync_db is None:
        return TrafficTrendsResponse(
            simulation_id=simulation_id,
            trends=[],
            count=0
        )

    try:
        # Get snapshots
        if simulation_id:
            snapshots = TrafficRepository.get_snapshots(simulation_id, limit=limit)
        else:
            # Get recent snapshots across all simulations
            cursor = (
                db_manager.sync_db.traffic_snapshots.find({}, {"_id": 0})
                .sort("timestamp", pymongo.DESCENDING)
                .limit(limit)
            )
            snapshots = list(cursor)
            # Reverse to get chronological order
            snapshots = snapshots[::-1]

        # Build trend points
        trends = []
        for snapshot in snapshots:
            try:
                queues = snapshot.get("queues", {})
                speed = snapshot.get("speed", {})
                waiting = snapshot.get("waiting", {})
                vehicles = snapshot.get("vehicles", {})

                # Calculate congestion score
                congestion_score = None
                try:
                    congestion_score = build_congestion_score(snapshot)
                except Exception:
                    pass

                trend_point = TrafficTrendPoint(
                    simulation_time=snapshot.get("simulation_time", 0.0),
                    queue=float(queues.get("total", 0)),
                    speed=float(speed.get("average_mps", 0.0)),
                    throughput=int(vehicles.get("completed", 0)),
                    waiting_time=float(waiting.get("average_seconds", 0.0)),
                    congestion_score=congestion_score,
                )
                trends.append(trend_point)
            except Exception as exc:
                logger.debug("Failed to process snapshot for trends: %s", exc)
                continue

        return TrafficTrendsResponse(
            simulation_id=simulation_id,
            trends=trends,
            count=len(trends),
        )

    except Exception as exc:
        logger.warning("Failed to retrieve traffic trends: %s", exc)
        return TrafficTrendsResponse(
            simulation_id=simulation_id,
            trends=[],
            count=0
        )


@router.get(
    "/controller-performance",
    response_model=ControllerPerformanceResponse,
    summary="Detailed Controller Performance",
)
async def get_controller_performance() -> ControllerPerformanceResponse:
    """
    Retrieve detailed controller performance comparison.

    Compares Fixed, Adaptive, and DQN controllers across multiple metrics.
    """
    comparison_data = PersistenceService.get_controller_comparison()

    # Calculate comparison summary
    controllers = comparison_data.get("controllers", {})
    comparison_summary = {
        "best_throughput_controller": None,
        "lowest_queue_controller": None,
        "lowest_wait_controller": None,
        "highest_speed_controller": None,
    }

    if controllers:
        # Find best performer for each metric
        best_throughput = max(
            (c, m.get("throughput", 0)) for c, m in controllers.items()
        )
        comparison_summary["best_throughput_controller"] = best_throughput[0]

        lowest_queue = min(
            (c, m.get("average_queue", float("inf"))) for c, m in controllers.items()
        )
        comparison_summary["lowest_queue_controller"] = lowest_queue[0]

        lowest_wait = min(
            (c, m.get("average_wait", float("inf"))) for c, m in controllers.items()
        )
        comparison_summary["lowest_wait_controller"] = lowest_wait[0]

        highest_speed = max(
            (c, m.get("average_speed", 0)) for c, m in controllers.items()
        )
        comparison_summary["highest_speed_controller"] = highest_speed[0]

    return ControllerPerformanceResponse(
        controllers=controllers,
        comparison_summary=comparison_summary,
    )

