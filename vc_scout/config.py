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

    # AI/ML API (partner) — OpenAI-compatible unified model gateway.
    aiml_api_key: str = ""
    aiml_base_url: str = "https://api.aimlapi.com/v1"
    aiml_model: str = "gpt-4o-mini"

    # Which provider the LLM client uses: "aiml" (partner) or "grok".
    llm_provider: str = "aiml"

    # Bright Data
    brightdata_api_key: str = ""
    brightdata_serp_zone: str = ""
    brightdata_unlocker_zone: str = ""
    brightdata_scraper_zone: str = ""
    # Scraping Browser CDP endpoint — wss://brd-customer-...@brd.superproxy.io:9222
    brightdata_browser_url: str = ""

    # App
    use_demo_cache: bool = False
    log_level: str = "INFO"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def load_settings() -> Settings:
    return Settings(
        grok_api_key=_env("GROK_API_KEY"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        aiml_api_key=_env("AIML_API_KEY"),
        aiml_model=_env("AIML_MODEL", "gpt-4o-mini"),
        llm_provider=_env("LLM_PROVIDER", "aiml").lower(),
        brightdata_api_key=_env("BRIGHTDATA_API_KEY"),
        brightdata_serp_zone=_env("BRIGHTDATA_SERP_ZONE"),
        brightdata_unlocker_zone=_env("BRIGHTDATA_UNLOCKER_ZONE"),
        brightdata_scraper_zone=_env("BRIGHTDATA_SCRAPER_ZONE"),
        brightdata_browser_url=_env("BRIGHTDATA_BROWSER_URL"),
        use_demo_cache=_env("USE_DEMO_CACHE", "false").lower() == "true",
        log_level=_env("LOG_LEVEL", "INFO"),
    )


settings = load_settings()
