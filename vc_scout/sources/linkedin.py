"""Bright Data Web Scraper API — LinkedIn company signals.

This is the differentiation layer. ChatGPT-with-browsing and Perplexity CANNOT
read LinkedIn (auth wall + anti-bot). Bright Data's Web Scraper API can, via
pre-built collectors. We pull STRUCTURED signals — headcount, headcount growth,
recent senior hires — that a summarizer never produces and that lead, not lag,
GTM momentum. These become high-trust evidence the triangulation engine checks
founder claims against.

Flow (Web Scraper API is async):
  1. POST /datasets/v3/trigger?dataset_id=...  with [{"url": <linkedin company url>}]
     -> returns {"snapshot_id": "..."}
  2. GET  /datasets/v3/snapshot/<snapshot_id>?format=json   (poll)
     -> 202 while running, 200 with rows when ready

Degrades to {} on any failure or if not configured; the pipeline continues on
SERP + Scraping Browser without LinkedIn.

Docs: https://docs.brightdata.com/scraping-automation/web-scraper-api/overview
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from ..config import settings

log = logging.getLogger(__name__)

_TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
_SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"

# Poll budget — LinkedIn collectors are slow. This runs OFFLINE to bake the
# demo cache, NOT in the live <90s path, so a generous budget is fine.
_POLL_INTERVAL_S = 8
_POLL_TIMEOUT_S = 240


def fetch_company_signals(linkedin_company_url: str) -> dict[str, Any]:
    """Return normalized LinkedIn signals for a company, or {} on any failure.

    Output (only keys we can support from the row are included):
      {
        "employee_count": int,
        "followers": int,
        "headquarters": str,
        "founded": int,
        "industries": str,
        "about": str,
        "source_url": str,        # the LinkedIn URL we scraped
      }
    """
    if not (settings.brightdata_api_key and settings.brightdata_dataset_company):
        log.warning("LinkedIn Web Scraper not configured "
                    "(BRIGHTDATA_API_KEY / BRIGHTDATA_DATASET_COMPANY) — skipping.")
        return {}
    if not linkedin_company_url:
        log.info("LinkedIn: no company URL available — skipping.")
        return {}

    try:
        rows = _trigger_and_poll(
            settings.brightdata_dataset_company,
            [{"url": linkedin_company_url}],
        )
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, never crash the pipeline
        log.error("LinkedIn fetch FAILED for %s — %s: %s",
                  linkedin_company_url, type(exc).__name__, exc, exc_info=True)
        return {}

    if not rows:
        log.info("LinkedIn: empty result for %s", linkedin_company_url)
        return {}

    signals = _normalize_company(rows[0], linkedin_company_url)
    log.info("LinkedIn: %d signal fields for %s", len(signals), linkedin_company_url)
    return signals


def _trigger_and_poll(dataset_id: str, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {settings.brightdata_api_key}",
        "Content-Type": "application/json",
    }

    log.info("LinkedIn: triggering dataset=%s for %d url(s)", dataset_id, len(payload))
    resp = requests.post(
        _TRIGGER_URL,
        headers=headers,
        params={"dataset_id": dataset_id, "include_errors": "true"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    snapshot_id = resp.json().get("snapshot_id")
    if not snapshot_id:
        log.warning("LinkedIn: no snapshot_id in trigger response: %s", resp.text[:200])
        return []
    log.info("LinkedIn: snapshot_id=%s — polling…", snapshot_id)

    snap_url = _SNAPSHOT_URL.format(snapshot_id=snapshot_id)
    deadline = time.time() + _POLL_TIMEOUT_S
    while time.time() < deadline:
        poll = requests.get(
            snap_url, headers=headers, params={"format": "json"}, timeout=30
        )
        if poll.status_code == 202:
            log.info("LinkedIn: snapshot still building…")
            time.sleep(_POLL_INTERVAL_S)
            continue
        poll.raise_for_status()
        data = poll.json()
        # Ready snapshots return a list of rows (or {"data": [...]}).
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        return data if isinstance(data, list) else [data]

    log.warning("LinkedIn: poll timed out after %ds", _POLL_TIMEOUT_S)
    return []


def _normalize_company(row: dict[str, Any], source_url: str) -> dict[str, Any]:
    """Map a Bright Data LinkedIn company row to our signal dict, omitting blanks.

    Bright Data field names vary by collector version, so we probe a few aliases
    per field and keep only what's present. Never invent values.
    """
    out: dict[str, Any] = {"source_url": source_url}

    employee_count = _first_int(row, ("employees_in_linkedin", "company_size",
                                      "employees", "num_employees", "size"))
    if employee_count is not None:
        out["employee_count"] = employee_count

    followers = _first_int(row, ("followers", "follower_count"))
    if followers is not None:
        out["followers"] = followers

    hq = _first_str(row, ("headquarters", "hq", "location"))
    if hq:
        out["headquarters"] = hq

    founded = _first_int(row, ("founded", "founded_year", "year_founded"))
    if founded is not None:
        out["founded"] = founded

    industries = _first_str(row, ("industries", "industry"))
    if industries:
        out["industries"] = industries

    about = _first_str(row, ("about", "description", "summary"))
    if about:
        out["about"] = about[:400]

    return out


def _first_int(row: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for k in keys:
        v = row.get(k)
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            digits = "".join(ch for ch in v if ch.isdigit())
            if digits:
                return int(digits)
    return None


def _first_str(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v if x)[:200]
    return ""


# ── Collector wrapper ────────────────────────────────────────────────────────

class LinkedInCompanyCollector:
    """Collector: LinkedIn company structured signals (NOT ground truth — see caveat)."""
    name = "LinkedIn"

    def applies_to(self, ctx) -> bool:
        return bool(ctx.linkedin_company_url)

    def collect(self, ctx) -> list:
        from .base import Signal
        signals_dict = fetch_company_signals(ctx.linkedin_company_url)
        if not signals_dict:
            return []
        signals = []
        url = signals_dict.get("source_url", ctx.linkedin_company_url)
        if "employee_count" in signals_dict:
            signals.append(Signal(
                section="team",
                fact=f"LinkedIn lists ~{signals_dict['employee_count']} employees (may over/under-count; lags real headcount).",
                url=url, source="LinkedIn", trust="medium",
                key="employee_count", value=signals_dict["employee_count"],
            ))
        if "founded" in signals_dict:
            signals.append(Signal(
                section="team",
                fact=f"Founded {signals_dict['founded']} per LinkedIn.",
                url=url, source="LinkedIn", trust="medium",
                key="founded", value=signals_dict["founded"],
            ))
        if "about" in signals_dict:
            signals.append(Signal(
                section="product",
                fact=signals_dict["about"][:250],
                url=url, source="LinkedIn", trust="medium",
            ))
        if "industries" in signals_dict:
            signals.append(Signal(
                section="market",
                fact=f"Industry per LinkedIn: {signals_dict['industries']}",
                url=url, source="LinkedIn", trust="medium",
                key="industries",
            ))
        return signals
