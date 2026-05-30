"""App Store collector — iOS rating and review signals via iTunes Search API.

Adaptive: applies_to() returns True when company_type=consumer_app.
Uses the public iTunes Search API (no key required).
Searches by company name, not URL — works even when SERP misses the App Store link.

API endpoint:
  GET https://itunes.apple.com/search?term=<name>&entity=software&limit=5
  Returns: trackName, averageUserRating, userRatingCount, price, sellerName,
           trackViewUrl, shortDescription / description

Signals emitted (section="traction", trust="high" — Apple's own data):
  - Rating + review count (independent adoption proxy)
  - Price (freemium/paid signal)

Degrades to [] if API returns no results or request fails.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

import requests

log = logging.getLogger(__name__)

_API_BASE = "https://itunes.apple.com/search"
_TIMEOUT = 15


def fetch_app_signals(app_name: str) -> dict[str, Any]:
    """Return App Store signals for app_name, or {} on any failure.

    Searches iTunes for up to 5 results and picks the best match
    (highest userRatingCount among results where trackName partially matches).

    Output keys (only present fields included):
      track_name, rating, review_count, price, seller_name, source_url
    """
    if not app_name:
        return {}

    try:
        resp = requests.get(
            _API_BASE,
            params={"term": app_name, "entity": "software", "limit": 5},
            timeout=_TIMEOUT,
            headers={"User-Agent": "vc-scout/1.0"},
        )
        if not resp.ok:
            log.warning("iTunes API returned %d for '%s'", resp.status_code, app_name)
            return {}

        results = resp.json().get("results", [])
        if not results:
            log.info("iTunes: no results for '%s'", app_name)
            return {}

        # Pick best match: prefer name overlap, tie-break by review count
        query_lower = app_name.lower()
        best = max(
            results,
            key=lambda r: (
                _name_overlap(r.get("trackName", ""), query_lower),
                r.get("userRatingCount", 0),
            ),
        )

        out: dict[str, Any] = {}
        if best.get("trackName"):
            out["track_name"] = best["trackName"]
        if best.get("averageUserRating") is not None:
            out["rating"] = round(float(best["averageUserRating"]), 1)
        if best.get("userRatingCount") is not None:
            out["review_count"] = int(best["userRatingCount"])
        if best.get("price") is not None:
            out["price"] = float(best["price"])
        if best.get("sellerName"):
            out["seller_name"] = best["sellerName"]
        if best.get("trackViewUrl"):
            out["source_url"] = best["trackViewUrl"]

        if not out:
            return {}

        log.info(
            "iTunes: '%s' → %s (rating=%.1f, reviews=%s)",
            app_name,
            out.get("track_name"),
            out.get("rating", 0.0),
            out.get("review_count", 0),
        )
        return out

    except Exception as exc:
        log.error("iTunes fetch FAILED for '%s' — %s: %s", app_name, type(exc).__name__, exc)
        return {}


def _name_overlap(track_name: str, query_lower: str) -> int:
    """Score how well track_name matches query. Simple word-overlap count."""
    track_lower = track_name.lower()
    if query_lower in track_lower or track_lower in query_lower:
        return 2
    query_words = set(query_lower.split())
    track_words = set(track_lower.split())
    return len(query_words & track_words)


# ── Collector wrapper ────────────────────────────────────────────────────────

class AppStoreCollector:
    """Collector: iOS App Store signals (rating, review count, price).

    Adaptive: applies_to() requires company_type=consumer_app.
    Searches by company name via iTunes API — no App Store URL needed.
    Signals are trust="high" — Apple's own platform data.
    """
    name = "App Store"

    def applies_to(self, ctx) -> bool:
        return ctx.company_type == "consumer_app"

    def collect(self, ctx) -> list:
        from .base import Signal

        data = fetch_app_signals(ctx.company)
        if not data:
            return []

        url = data.get("source_url", "https://apps.apple.com")
        signals: list[Signal] = []

        # Primary traction signal — rating + review count
        parts: list[str] = []
        if "rating" in data:
            parts.append(f"{data['rating']}★")
        if "review_count" in data:
            count = data["review_count"]
            if count >= 1_000:
                parts.append(f"{count / 1000:.1f}K ratings")
            else:
                parts.append(f"{count:,} ratings")
        if "price" in data:
            price = data["price"]
            parts.append("free" if price == 0.0 else f"${price:.2f}")
        if "track_name" in data:
            parts.append(f"app: {data['track_name']}")

        if parts:
            signals.append(Signal(
                section="traction",
                fact=f"App Store: {', '.join(parts)} (independent adoption proxy).",
                url=url, source="App Store", trust="high",
                key="ios_rating",
                value={k: v for k, v in data.items() if k != "source_url"},
            ))

        log.info("App Store collector: emitted %d signals from %s", len(signals), url)
        return signals
