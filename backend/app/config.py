"""Environment-backed configuration for the RepoPilot API.

Secrets are intentionally read only by the backend. The Vite app never receives
provider keys; it talks to the API through the local proxy or deployed API URL.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    github_token: str | None = os.getenv("GITHUB_TOKEN") or None
    llm_provider: str = os.getenv("LLM_PROVIDER", "none").lower()
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    allowed_origins: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    api_timeout_seconds: float = float(os.getenv("API_TIMEOUT_SECONDS", "20"))
    analysis_cache_ttl_seconds: int = int(os.getenv("ANALYSIS_CACHE_TTL_SECONDS", "300"))
    analysis_cache_max_entries: int = int(os.getenv("ANALYSIS_CACHE_MAX_ENTRIES", "32"))

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
