"""Bright Data Web Scraper API — LinkedIn people (founder pedigree).

Unlocks the highest-signal team section: university, prior companies, prior
exits/scaling per founder. Self-reported on LinkedIn but validated through the
network — more reliable than anything an LLM can hallucinate from a bio.

Architecture note: This collector is DEEP-mode only.
  - Live path (<90s): SKIP (heavy async polling, adds 30-60s per profile)
  - DEEP=true path: runs during cache-bake, results baked into demo_cache/

Usage gate: only runs if settings.deep=True AND ctx.linkedin_people_urls is non-empty.

API flow (same as linkedin.py company collector):
  1. POST /datasets/v3/trigger?dataset_id=<BRIGHTDATA_DATASET_PEOPLE>
     payload: [{"url": <linkedin_profile_url>}, ...]
  2. Poll GET /datasets/v3/snapshot/<snapshot_id>?format=json until 200
  3. Normalize each row → Signal(section="team", ...)

Degrades to [] on any failure; pipeline continues without pedigree signals.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from ..config import settings
from .base import EntityContext, Signal

log = logging.getLogger(__name__)

_TRIGGER_URL = "https://api.brightdata.com/datasets/v3/trigger"
_SNAPSHOT_URL = "https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"

_POLL_INTERVAL_S = 8
_POLL_TIMEOUT_S = 300  # people collector can be slow; generous budget for DEEP path

_EXIT_RE = re.compile(
    r"(acqui[rs]ed|acquisition|sold to|ipo|went public|\$[\d,.]+[mb]|"
    r"grew to|scaled to|series [a-d]|raised|exited|merger|acquihire)",
    re.I,
)


def fetch_people_signals(profile_urls: list[str]) -> list[dict[str, Any]]:
    """Return normalized pedigree dicts for each profile URL, or [] on any failure.

    Each dict:
      {
        "profile_url": str,
        "name": str,
        "headline": str,
        "current_company": str,
        "education": [{"school": str, "degree": str}],       # univ list
        "experience": [{"company": str, "title": str, "description": str}],
        "exits_or_scaling": str | None,   # first exit/scaling mention found
      }
    """
    if not profile_urls:
        return []
    if not (settings.brightdata_api_key and settings.brightdata_dataset_people):
        log.warning("LinkedIn People: BRIGHTDATA_DATASET_PEOPLE not configured — skipping.")
        return []

    payload = [{"url": url} for url in profile_urls]
    try:
        rows = _trigger_and_poll(settings.brightdata_dataset_people, payload)
    except Exception as exc:
        log.error("LinkedIn People fetch FAILED — %s: %s", type(exc).__name__, exc, exc_info=True)
        return []

    if not rows:
        log.info("LinkedIn People: empty result for %d profiles", len(profile_urls))
        return []

    profiles = [_normalize_person(row) for row in rows if isinstance(row, dict)]
    log.info("LinkedIn People: %d profiles normalized", len(profiles))
    return profiles


def _trigger_and_poll(dataset_id: str, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {settings.brightdata_api_key}",
        "Content-Type": "application/json",
    }

    log.info("LinkedIn People: triggering dataset=%s for %d profile(s)", dataset_id, len(payload))
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
        log.warning("LinkedIn People: no snapshot_id in response: %s", resp.text[:200])
        return []
    log.info("LinkedIn People: snapshot_id=%s — polling…", snapshot_id)

    snap_url = _SNAPSHOT_URL.format(snapshot_id=snapshot_id)
    deadline = time.time() + _POLL_TIMEOUT_S
    while time.time() < deadline:
        poll = requests.get(snap_url, headers=headers, params={"format": "json"}, timeout=30)
        if poll.status_code == 202:
            log.info("LinkedIn People: snapshot still building…")
            time.sleep(_POLL_INTERVAL_S)
            continue
        poll.raise_for_status()
        data = poll.json()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        return data if isinstance(data, list) else [data]

    log.warning("LinkedIn People: poll timed out after %ds", _POLL_TIMEOUT_S)
    return []


def _normalize_person(row: dict[str, Any]) -> dict[str, Any]:
    """Map a Bright Data LinkedIn people row to our pedigree dict.

    Field names vary across collector versions — we probe aliases. Never invent values.
    """
    profile_url = _first_str(row, ("url", "profile_url", "linkedin_url")) or ""
    name = _first_str(row, ("name", "full_name", "first_name"))
    headline = _first_str(row, ("headline", "title", "current_title"))
    current_company = _first_str(row, ("current_company", "company", "employer"))

    # Education: probe both a list field and individual school fields
    education: list[dict[str, str]] = []
    raw_edu = row.get("education") or row.get("educations") or []
    if isinstance(raw_edu, list):
        for entry in raw_edu:
            if not isinstance(entry, dict):
                continue
            school = _first_str(entry, ("school", "school_name", "institution", "university"))
            degree = _first_str(entry, ("degree", "degree_name", "field_of_study"))
            if school:
                education.append({"school": school, "degree": degree})

    # Experience: probe list field
    experience: list[dict[str, str]] = []
    raw_exp = row.get("experience") or row.get("experiences") or row.get("positions") or []
    if isinstance(raw_exp, list):
        for entry in raw_exp:
            if not isinstance(entry, dict):
                continue
            company = _first_str(entry, ("company", "company_name", "organization"))
            title = _first_str(entry, ("title", "job_title", "position"))
            description = _first_str(entry, ("description", "summary"))
            if company:
                experience.append({"company": company, "title": title, "description": description})

    # Look for exit/scaling language across all experience descriptions
    exits_or_scaling: str | None = None
    for exp in experience:
        desc = exp.get("description", "")
        if desc and _EXIT_RE.search(desc):
            exits_or_scaling = desc[:200]
            break
    # Also check a top-level summary field
    if not exits_or_scaling:
        summary = _first_str(row, ("summary", "about", "bio"))
        if summary and _EXIT_RE.search(summary):
            exits_or_scaling = summary[:200]

    out: dict[str, Any] = {"profile_url": profile_url}
    if name:
        out["name"] = name
    if headline:
        out["headline"] = headline
    if current_company:
        out["current_company"] = current_company
    if education:
        out["education"] = education
    if experience:
        out["experience"] = experience
    if exits_or_scaling:
        out["exits_or_scaling"] = exits_or_scaling
    return out


def _first_str(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v if x)[:300]
    return ""


# ── Collector wrapper ────────────────────────────────────────────────────────

class LinkedInPeopleCollector:
    """Collector: LinkedIn founder profiles → pedigree signals.

    DEEP-mode only (settings.deep=True). Runs during cache bake, not live path.
    Each profile yields signals for the team section: university, prior companies,
    exits/scaling evidence — all with trust="medium" (self-reported on LinkedIn).
    """
    name = "LinkedIn People"

    def applies_to(self, ctx: EntityContext) -> bool:
        return settings.deep and bool(ctx.linkedin_people_urls)

    def collect(self, ctx: EntityContext) -> list[Signal]:
        profiles = fetch_people_signals(ctx.linkedin_people_urls)
        if not profiles:
            return []

        signals: list[Signal] = []
        for p in profiles:
            url = p.get("profile_url", "")
            name = p.get("name", "unknown founder")

            # University signal — first education entry
            education = p.get("education", [])
            if education:
                school = education[0].get("school", "")
                degree = education[0].get("degree", "")
                if school:
                    fact = f"{name} attended {school}" + (f" ({degree})" if degree else "") + "."
                    signals.append(Signal(
                        section="team", fact=fact, url=url,
                        source="LinkedIn People", trust="medium",
                        key="university", value=school,
                    ))

            # Prior companies — all past experience company names
            experience = p.get("experience", [])
            current = p.get("current_company", "").lower()
            prior = [
                e["company"] for e in experience
                if e.get("company") and e["company"].lower() != current
            ]
            if prior:
                companies_str = ", ".join(prior[:5])
                signals.append(Signal(
                    section="team",
                    fact=f"{name} previously worked at: {companies_str}.",
                    url=url, source="LinkedIn People", trust="medium",
                    key="prior_companies", value=prior,
                ))

            # Exit / scaling signal
            exits = p.get("exits_or_scaling")
            if exits:
                signals.append(Signal(
                    section="team",
                    fact=f"{name} exit/scaling evidence: {exits[:200]}",
                    url=url, source="LinkedIn People", trust="medium",
                    key="exits_or_scaling", value=exits,
                ))

            # Headline as a general team signal
            headline = p.get("headline", "")
            if headline:
                signals.append(Signal(
                    section="team",
                    fact=f"{name}: {headline}",
                    url=url, source="LinkedIn People", trust="medium",
                    key="headline",
                ))

        log.info("LinkedIn People: emitted %d signals from %d profiles", len(signals), len(profiles))
        return signals
