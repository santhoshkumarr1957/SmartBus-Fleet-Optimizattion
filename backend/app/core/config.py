import json
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SmartBus"
    API_V1_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"

    # Supabase PostgreSQL database URL
    DATABASE_URL: str | None = None

    # CORS origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Simulation configuration
    SIMULATION_INTERVAL_SECONDS: float = 1.0
    SIMULATION_SCENARIO: str = "normal"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Union[str, None]) -> Union[str, None]:
        if not v:
            return None
        v_trimmed = v.strip()
        if not v_trimmed:
            return None
        # Handle postgres:// scheme prefix
        if v_trimmed.startswith("postgres://"):
            v_trimmed = "postgresql+pg8000://" + v_trimmed[len("postgres://"):]
        elif v_trimmed.startswith("postgresql://"):
            # Default to pure-Python pg8000 driver for guaranteed cross-platform compatibility
            v_trimmed = "postgresql+pg8000://" + v_trimmed[len("postgresql://"):]
        return v_trimmed

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
            return [i.strip() for i in v_trimmed.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
