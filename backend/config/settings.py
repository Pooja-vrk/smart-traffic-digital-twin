"""Application configuration and settings using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """FastAPI application settings loaded from environment or defaults."""

    # Project metadata
    PROJECT_NAME: str = "Smart Traffic Digital Twin API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "AI-Driven Digital Twin for Smart City Traffic Flow Management"
    API_V1_STR: str = "/api"

    # Server binding
    HOST: str = Field(default="127.0.0.1", validation_alias="BACKEND_HOST")
    PORT: int = Field(default=8000, validation_alias="BACKEND_PORT")

    # CORS settings
    FRONTEND_URL: str = Field(default="http://localhost:5173", validation_alias="FRONTEND_URL")

    # SUMO & Simulation settings
    SUMO_HOME: Optional[str] = Field(default=None, validation_alias="SUMO_HOME")
    DEFAULT_SIMULATION_STEPS: int = 300
    MAX_SIMULATION_STEPS: int = 3600
    DEFAULT_SEED: int = 42
    TELEMETRY_INTERVAL: float = 1.0  # seconds between telemetry broadcasts
    WEBSOCKET_HEARTBEAT_INTERVAL: float = 15.0  # seconds

    # MongoDB Persistence settings
    MONGODB_URI: str = Field(default="mongodb://localhost:27017", validation_alias="MONGODB_URI")
    DATABASE_NAME: str = Field(default="smart_traffic_digital_twin", validation_alias="DATABASE_NAME")
    MONGODB_CONNECT_TIMEOUT_MS: int = 2000

    # AI Model paths
    DQN_MODEL_PATH: str = "ai/models/dqn_traffic_controller.pt"
    DQN_BEST_MODEL_PATH: str = "ai/models/dqn_best_model.pt"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )



settings = Settings()

