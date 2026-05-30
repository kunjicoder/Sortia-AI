"""App Store collector — iOS rating, review velocity, ranking.

Adaptive: only runs when company_type=consumer_app (or appstore_url present).
Uses Bright Data Scraping Browser (CDP/Playwright) to render the App Store
listing and extract structured signals.

Signals emitted:
  section="traction" — rating, review count, chart ranking (trust="high": Apple's own data)
  section="product"  — app subtitle, description excerpt (trust="medium": store copy)

Degrades to [] if BRIGHTDATA_BROWSER_URL is unset or the page doesn't render.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Patterns for metric extraction from rendered App Store text
_RATING_RE = re.compile(r"\b([1-5]\.\d)\b(?:\s*out\s+of\s+5)?")
_REVIEW_COUNT_RE = re.compile(r"([\d,.]+[KkMm]?)\s+(?:Ratings?|Reviews?)")
_RANK_RE = re.compile(r"#\s*(\d+)\s+in\s+([\w\s&]+?)(?:\n|$)")


def fetch_appstore_signals(appstore_url: str) -> dict:
    """Return structured App Store signals, or {} on any failure.

    Output:
      {
        "rating":        float,    # e.g. 4.8
        "review_count":  str,      # e.g. "31.4K"
        "chart_rank":    str,      # e.g. "#1 in Productivity"
        "description":   str,      # first 500 chars of app description
        "app_subtitle":  str,      # marketing tagline below the title
        "source_url":    str,
      }
    """
    if not appstore_url:
        return {}

    from ..config import settings
    if not settings.brightdata_browser_url:
        log.warning("AppStore: Scraping Browser not configured — skipping.")
        return {}

    try:
        page_text, structured = _render_appstore(appstore_url, settings.brightdata_browser_url)
    except ImportError as exc:
        log.error("AppStore: Playwright not installed (%s).", exc)
        return {}
    except Exception as exc:
        log.error("AppStore FAILED for %s — %s: %s", appstore_url, type(exc).__name__, exc, exc_info=True)
        return {}

    if not page_text:
        return {}

    out: dict = {"source_url": appstore_url}

    # Description from structured JS extraction, or regex fallback
    if structured.get("description"):
        out["description"] = structured["description"][:500]
    if structured.get("subtitle"):
        out["app_subtitle"] = structured["subtitle"][:120]

    # Rating
    rating_m = _RATING_RE.search(page_text)
    if rating_m:
        try:
            out["rating"] = float(rating_m.group(1))
        except ValueError:
            pass

    # Review count
    rc_m = _REVIEW_COUNT_RE.search(page_text)
    if rc_m:
        out["review_count"] = rc_m.group(1)

    # Chart ranking — take the first match (highest rank)
    rank_m = _RANK_RE.search(page_text)
    if rank_m:
        out["chart_rank"] = f"#{rank_m.group(1)} in {rank_m.group(2).strip()}"

    if len(out) <= 1:  # only source_url — nothing extracted
        log.info("AppStore: no structured signals extracted from %s", appstore_url)
        return {}

    log.info("AppStore: extracted %s", {k: v for k, v in out.items() if k != "description"})
    return out


def _render_appstore(url: str, browser_ws_url: str) -> tuple[str, dict]:
    """Render the App Store listing via Scraping Browser.

    Returns (page_text, structured_dict) where structured_dict has
    'description' and 'subtitle' extracted by JS if possible.
    """
    from playwright.sync_api import sync_playwright

    structured: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(browser_ws_url)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2_000)

            # Try to extract key fields via JS
            structured = page.evaluate("""() => {
                function text(sel) {
                    const el = document.querySelector(sel);
                    return el ? el.innerText.trim() : '';
                }
                return {
                    subtitle: text('.product-header__subtitle') ||
                              text('[class*="subtitle"]') || '',
                    description: text('.section__description .we-truncate') ||
                                 text('.we-clamp') ||
                                 text('[class*="description"] p') || '',
                };
            }""") or {}

            # Full page text for regex-based extraction
            page_text = page.evaluate("""() => document.body ? document.body.innerText : ''""") or ""
            page.close()
        finally:
            browser.close()

    return page_text, structured


# ── Collector wrapper ────────────────────────────────────────────────────────

class AppStoreCollector:
    """Collector: iOS App Store signals (rating, reviews, ranking).

    Adaptive: applies_to() returns True for consumer_app type OR when
    appstore_url is present (resolver found it in SERP).
    """
    name = "App Store"

    def applies_to(self, ctx) -> bool:
        return bool(ctx.appstore_url)

    def collect(self, ctx) -> list:
        from .base import Signal

        data = fetch_appstore_signals(ctx.appstore_url)
        if not data:
            return []

        url = data.get("source_url", ctx.appstore_url)
        signals: list[Signal] = []

        # Traction signals — high trust (Apple's own platform data)
        if "rating" in data and "review_count" in data:
            signals.append(Signal(
                section="traction",
                fact=f"iOS App Store rating: {data['rating']}/5.0 from {data['review_count']} ratings.",
                url=url, source="App Store", trust="high",
                key="ios_rating", value={"rating": data["rating"], "count": data["review_count"]},
            ))
        elif "rating" in data:
            signals.append(Signal(
                section="traction",
                fact=f"iOS App Store rating: {data['rating']}/5.0.",
                url=url, source="App Store", trust="high",
                key="ios_rating", value=data["rating"],
            ))

        if "chart_rank" in data:
            signals.append(Signal(
                section="traction",
                fact=f"App Store chart position: {data['chart_rank']}.",
                url=url, source="App Store", trust="high",
                key="chart_rank",
            ))

        # Product signals — medium trust (store copy, first-party)
        if "app_subtitle" in data:
            signals.append(Signal(
                section="product",
                fact=f"App Store subtitle: {data['app_subtitle']}",
                url=url, source="App Store", trust="medium",
                key="app_subtitle",
            ))

        if "description" in data:
            signals.append(Signal(
                section="product",
                fact=data["description"][:400],
                url=url, source="App Store", trust="medium",
                key="app_description",
            ))

        log.info("App Store: emitted %d signals from %s", len(signals), url)
        return signals
