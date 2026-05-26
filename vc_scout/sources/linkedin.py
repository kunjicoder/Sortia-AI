"""Bright Data Web Scraper API wrapper — LinkedIn collectors.

Used for: founder LinkedIn profiles, company page (team size, hiring velocity).

LinkedIn blocks aggressively; the Web Scraper API uses pre-built collectors
that handle the heavy lifting. Pick the right collector ID in the Bright
Data dashboard and reference it here.

Docs: https://docs.brightdata.com/scraping-automation/web-scraper-api/overview
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import requests

from ..config import settings

log = logging.getLogger(__name__)

SCRAPER_ENDPOINT = "https://api.brightdata.com/datasets/v3/trigger"


def fetch_company(company: str) -> Dict[str, Any]:
    """Fetch a LinkedIn company page via Bright Data's pre-built collector.

    TODO Thursday: pick the right collector ID (probably
    `gd_l1viktl72bvl7bjuj0` for LinkedIn company page) and confirm the
    trigger/poll flow. Triggers are async — we may need to poll a job ID
    rather than return synchronously.
    """
    if not settings.brightdata_api_key or not settings.brightdata_scraper_zone:
        log.warning("Bright Data Web Scraper not configured — returning empty result.")
        return {}

    raise NotImplementedError("Implement LinkedIn collector trigger and polling on Thursday.")


def fetch_founder(linkedin_url: str) -> Dict[str, Any]:
    """Fetch a single LinkedIn profile (founder background)."""
    raise NotImplementedError("Implement founder profile fetch on Thursday.")
