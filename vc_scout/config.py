"""Configuration loader. Reads from environment variables (and `.env` if present).

All secrets are loaded here so the rest of the codebase imports `settings`
rather than reading os.environ directly. Makes it easier to swap providers
or mock for tests later.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root if it exists. No-op if missing.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # LLM
    grok_api_key: str
    gemini_api_key: str
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-2-latest"

    # Bright Data
    brightdata_api_key: str = ""
    brightdata_serp_zone: str = ""
    brightdata_unlocker_zone: str = ""
    brightdata_scraper_zone: str = ""

    # App
    use_demo_cache: bool = False
    log_level: str = "INFO"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def load_settings() -> Settings:
    return Settings(
        grok_api_key=_env("GROK_API_KEY"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        brightdata_api_key=_env("BRIGHTDATA_API_KEY"),
        brightdata_serp_zone=_env("BRIGHTDATA_SERP_ZONE"),
        brightdata_unlocker_zone=_env("BRIGHTDATA_UNLOCKER_ZONE"),
        brightdata_scraper_zone=_env("BRIGHTDATA_SCRAPER_ZONE"),
        use_demo_cache=_env("USE_DEMO_CACHE", "false").lower() == "true",
        log_level=_env("LOG_LEVEL", "INFO"),
    )


settings = load_settings()
