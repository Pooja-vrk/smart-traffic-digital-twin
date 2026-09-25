"""Pydantic schemas for analytics aggregations and controller benchmarking comparisons."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ControllerMetricsSummary(BaseModel):
    """Aggregated mean metrics for a single controller type."""
    runs_count: int = Field(default=0, description="Total completed experiment runs")
    throughput: float = Field(default=0.0, description="Mean vehicle throughput (completed trips)")
    average_queue: float = Field(default=0.0, description="Mean total queue length in vehicles")
    peak_queue: float = Field(default=0.0, description="Mean peak total queue length")
    average_wait: float = Field(default=0.0, description="Mean waiting time in seconds")
    average_delay: float = Field(default=0.0, description="Mean delay in seconds per vehicle")
    average_speed: float = Field(default=0.0, description="Mean vehicle velocity in m/s")
    phase_changes: float = Field(default=0.0, description="Mean total signal phase transitions")
    estimated_co2_kg: float = Field(default=0.0, description="Mean cumulative estimated CO2 emissions in kg")


class ControllerComparisonResponse(BaseModel):
    """Comparative benchmarking metrics grouped across Fixed-Time, Adaptive, and DQN controllers."""
    controllers: Dict[str, ControllerMetricsSummary] = Field(
        default_factory=dict,
        description="Dictionary mapping controller ID to performance summary metrics",
    )
    sample_count: int = Field(default=0, description="Total number of evaluated simulation runs analyzed")


class AnalyticsSummaryResponse(BaseModel):
    """High-level digital twin platform statistics across all recorded simulation experiments."""
    total_simulations: int = Field(default=0, description="Total completed simulation runs")
    controllers: Dict[str, int] = Field(default_factory=dict, description="Distribution of runs per controller")
    best_throughput: Optional[int] = Field(default=None, description="Maximum throughput achieved in any run")
    lowest_average_queue: Optional[float] = Field(default=None, description="Lowest mean queue length achieved")
    lowest_average_wait: Optional[float] = Field(default=None, description="Lowest mean waiting time achieved")
    total_vehicles_served: int = Field(default=0, description="Cumulative trips completed across all runs")


class CongestionDistributionResponse(BaseModel):
    """Distribution of congestion levels across historical data."""
    congestion_levels: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of snapshots per congestion level (FREE_FLOW, LOW, MODERATE, HIGH, SEVERE)"
    )
    total_snapshots: int = Field(default=0, description="Total number of snapshots analyzed")
    percentage_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="Percentage of snapshots per congestion level"
    )


class TrafficTrendPoint(BaseModel):
    """Single point in traffic trend time series."""
    simulation_time: float = Field(default=0.0, description="Simulation time in seconds")
    queue: float = Field(default=0.0, description="Total queue length")
    speed: float = Field(default=0.0, description="Average speed in m/s")
    throughput: int = Field(default=0, description="Cumulative vehicles completed")
    waiting_time: float = Field(default=0.0, description="Average waiting time in seconds")
    congestion_score: Optional[float] = Field(default=None, description="Congestion score (0-100)")


class TrafficTrendsResponse(BaseModel):
    """Time-series traffic trends data."""
    simulation_id: Optional[str] = Field(default=None, description="Simulation ID if filtering by single run")
    trends: list[TrafficTrendPoint] = Field(default_factory=list, description="Time-series data points")
    count: int = Field(default=0, description="Number of data points")


class ControllerPerformanceResponse(BaseModel):
    """Detailed controller performance comparison."""
    controllers: Dict[str, ControllerMetricsSummary] = Field(
        default_factory=dict,
        description="Performance metrics per controller"
    )
    comparison_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary comparison metrics"
    )
