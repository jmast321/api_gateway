import os
from enum import Enum
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoutingMode(str, Enum):
    SYNERGY = "SYNERGY"
    HEURISTIC_ONLY = "HEURISTIC_ONLY"
    SHADOW_TEST = "SHADOW_TEST"


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # API Keys
    OPENROUTER_API_KEY: str = ""

    # Network / Host
    GATEWAY_HOST: str = "0.0.0.0"
    GATEWAY_PORT: int = 8000
    DEBUG: bool = False

    # Routing
    DEFAULT_ROUTING_MODE: RoutingMode = RoutingMode.SYNERGY
    MODEL_REFRESH_INTERVAL_MINUTES: int = 30

    # Resiliency
    MAX_RETRIES: int = 3
    BACKOFF_FACTOR: float = 1.5
    REQUEST_TIMEOUT_SECONDS: float = 120.0
    FALLBACK_CANDIDATES_COUNT: int = 3

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
