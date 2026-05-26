"""Bright Data SERP API wrapper.

Used for: recent news, press releases, HN front-page mentions, founder name lookups.

Docs: https://docs.brightdata.com/scraping-automation/serp-api/overview
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

from ..config import settings

log = logging.getLogger(__name__)

SERP_ENDPOINT = "https://api.brightdata.com/request"


def search_company(company: str, num_results: int = 10) -> List[Dict[str, Any]]:
    """Search Google for recent mentions of the company.

    TODO Wednesday: confirm the exact request shape for Bright Data SERP API
    against the docs. The shape below is a placeholder.
    """
    if not settings.brightdata_api_key or not settings.brightdata_serp_zone:
        log.warning("Bright Data SERP not configured — returning empty results.")
        return []

    query = f'"{company}" (news OR raised OR launched OR hiring)'
    payload = {
        "zone": settings.brightdata_serp_zone,
        "url": f"https://www.google.com/search?q={requests.utils.quote(query)}&num={num_results}",
        "format": "json",
    }
    headers = {
        "Authorization": f"Bearer {settings.brightdata_api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(SERP_ENDPOINT, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return _parse_serp_response(resp.json())


def _parse_serp_response(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize the Bright Data SERP response into a flat list of results.

    TODO: implement once we see a real response in Wednesday's testing.
    """
    raise NotImplementedError("Parse the SERP response shape after the first live call.")
