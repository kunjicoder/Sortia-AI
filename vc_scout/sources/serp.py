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
    """Search Google for recent mentions of the company via Bright Data SERP API.

    We append `brd_json=1` to the Google URL so Bright Data returns parsed JSON
    (organic results, news, etc.) instead of raw HTML. We then normalize that
    into a flat list of {title, url, description, source} dicts for the LLM.
    """
    if not settings.brightdata_api_key or not settings.brightdata_serp_zone:
        log.warning("Bright Data SERP not configured — returning empty results.")
        return []

    query = f'"{company}" (news OR raised OR launched OR hiring)'
    google_url = (
        f"https://www.google.com/search?q={requests.utils.quote(query)}"
        f"&num={num_results}&brd_json=1"
    )
    payload = {
        "zone": settings.brightdata_serp_zone,
        "url": google_url,
        "format": "raw",  # with brd_json=1 the response body is the parsed JSON itself
    }
    headers = {
        "Authorization": f"Bearer {settings.brightdata_api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(SERP_ENDPOINT, json=payload, headers=headers, timeout=45)
    resp.raise_for_status()

    # With format=raw the body is the parsed SERP JSON as text.
    try:
        raw = resp.json()
    except ValueError:
        log.error("SERP response was not JSON: %s", resp.text[:500])
        return []
    return _parse_serp_response(raw)


# Keys Bright Data's brd_json parser may use for each result field.
_TITLE_KEYS = ("title", "name")
_URL_KEYS = ("link", "url", "href")
_DESC_KEYS = ("description", "snippet", "desc")
# Sections of the parsed SERP that contain list-of-result items.
_RESULT_SECTIONS = ("organic", "news", "organic_results", "news_results")


def _parse_serp_response(raw: Any) -> List[Dict[str, Any]]:
    """Normalize Bright Data's parsed SERP JSON into a flat list of results.

    The brd_json shape can vary (organic vs organic_results, news, etc.), so we
    scan known sections and pull the first matching field name from each item.
    Defensive on purpose — verify exact keys on first live call and trim later.
    """
    # Some responses wrap the payload in {"body": "<json string>"}.
    if isinstance(raw, dict) and "body" in raw and isinstance(raw["body"], str):
        import json

        try:
            raw = json.loads(raw["body"])
        except json.JSONDecodeError:
            log.error("Could not parse wrapped SERP body.")
            return []

    if not isinstance(raw, dict):
        log.warning("Unexpected SERP shape: %s", type(raw))
        return []

    results: List[Dict[str, Any]] = []
    for section in _RESULT_SECTIONS:
        items = raw.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": _first(item, _TITLE_KEYS),
                    "url": _first(item, _URL_KEYS),
                    "description": _first(item, _DESC_KEYS),
                    "source": section,
                }
            )
    log.info("SERP returned %d normalized results", len(results))
    return results


def _first(item: Dict[str, Any], keys: tuple) -> str:
    for k in keys:
        v = item.get(k)
        if v:
            return str(v)
    return ""


# ── Collector wrapper ────────────────────────────────────────────────────────

class SerpCollector:
    """Collector: SERP API facts → market / funding / competition / risks signals."""
    name = "SERP API"

    def applies_to(self, ctx) -> bool:
        return True  # universal

    def collect(self, ctx) -> list:
        from .base import Signal
        from ..bundle import _JUNK_SNIPPET_RE, _FUNDING_RE, _TRACTION_RE

        signals = []
        for item in ctx.serp_results:
            fact = (item.get("description") or item.get("title") or "").strip()
            if not fact or _JUNK_SNIPPET_RE.search(fact):
                continue
            url = item.get("url", "")
            text = f"{item.get('title', '')} {fact}"
            section = "market"
            if _FUNDING_RE.search(text):
                section = "funding"
            elif _TRACTION_RE.search(text):
                section = "traction"
            signals.append(Signal(
                section=section,
                fact=fact[:300],
                url=url,
                source="SERP",
                trust="high",
                date=item.get("date", ""),
            ))
        return signals
