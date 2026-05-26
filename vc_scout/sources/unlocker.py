"""Bright Data Web Unlocker wrapper.

Used for: GitHub repo pages, X/Twitter profiles, ProductHunt launches,
dynamic pricing pages, and anything else that needs JS rendering or
bot-detection bypass.

Docs: https://docs.brightdata.com/scraping-automation/web-unlocker/overview
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import requests

from ..config import settings

log = logging.getLogger(__name__)

UNLOCKER_ENDPOINT = "https://api.brightdata.com/request"


def fetch_url(url: str) -> str:
    """Fetch a URL through the Web Unlocker. Returns the rendered HTML."""
    if not settings.brightdata_api_key or not settings.brightdata_unlocker_zone:
        log.warning("Bright Data Web Unlocker not configured — returning empty HTML.")
        return ""

    payload = {
        "zone": settings.brightdata_unlocker_zone,
        "url": url,
        "format": "raw",
    }
    headers = {
        "Authorization": f"Bearer {settings.brightdata_api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(UNLOCKER_ENDPOINT, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.text


def fetch_github(company: str) -> Dict[str, Any]:
    """Best-effort GitHub org/repo lookup.

    TODO Thursday: implement the search-then-fetch flow. For the demo we
    might lean on the public GitHub REST API for stars/forks/contributors
    and only use Unlocker for the org landing page.
    """
    raise NotImplementedError("Implement GitHub fetch on Thursday.")
