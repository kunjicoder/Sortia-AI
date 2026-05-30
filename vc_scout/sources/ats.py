"""Bright Data Scraping Browser — ATS / careers-page hiring signals.

Why this source: an LLM tool can read "we're hiring" off a homepage. It cannot
tell you the company just opened its FIRST enterprise Account Executive role —
the moment a product-led company turns sales-led. Role-level hiring intent is a
leading GTM signal, it's the company's own live pipeline (hard to fake), and the
ATS pages (Ashby, Greenhouse, Lever) are JS apps that Bright Data's Scraping
Browser renders cleanly.

We extract the live role list, then derive:
  - open_roles: total count
  - functions: {engineering, sales, marketing, product, ops, other} counts
  - gtm_motion: roles that signal a go-to-market inflection (AE, sales, revenue,
    GTM, partnerships, customer success)

Degrades to {} on any failure; the pipeline continues without it.
"""

from __future__ import annotations

import logging
import re

from ..config import settings

log = logging.getLogger(__name__)

# Known ATS hosts whose board URLs are worth rendering.
_ATS_HOSTS = ("ashbyhq.com", "greenhouse.io", "lever.co", "workable.com", "jobs.")

# Role-title classification (first match wins; order matters).
_FUNCTION_PATTERNS = [
    ("sales", re.compile(r"\b(account executive|ae\b|sales|revenue|gtm|go.to.market"
                         r"|partnership|business development|bizdev|customer success)\b", re.I)),
    ("engineering", re.compile(r"\b(engineer|engineering|developer|swe|infrastructure"
                               r"|backend|frontend|full.?stack|ml|machine learning|data)\b", re.I)),
    ("product", re.compile(r"\b(product manager|product designer|\bpm\b|design|ux|ui)\b", re.I)),
    ("marketing", re.compile(r"\b(marketing|growth|content|brand|demand gen|community)\b", re.I)),
    ("operations", re.compile(r"\b(operations|ops|finance|recruit|people|hr|legal|office)\b", re.I)),
]

# Titles that signal a GTM inflection specifically.
_GTM_RE = re.compile(
    r"\b(account executive|\bae\b|sales|revenue|gtm|go.to.market|partnership"
    r"|business development|customer success|head of sales|vp.*sales)\b", re.I)


def fetch_hiring_signals(careers_url: str) -> dict:
    """Return structured hiring signals from a rendered ATS/careers page, or {}."""
    if not careers_url:
        return {}
    if not settings.brightdata_browser_url:
        log.warning("ATS: Scraping Browser not configured — skipping hiring signals.")
        return {}

    try:
        titles = _render_role_titles(careers_url)
    except ImportError as exc:
        log.error("ATS: Playwright not installed (%s).", exc)
        return {}
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        log.error("ATS FAILED for %s — %s: %s", careers_url, type(exc).__name__, exc, exc_info=True)
        return {}

    if not titles:
        log.info("ATS: no roles parsed from %s", careers_url)
        return {}

    signals = _derive(titles, careers_url)
    log.info("ATS: %d roles, gtm_motion=%s, functions=%s",
             signals["open_roles"], bool(signals.get("gtm_motion")), signals["functions"])
    return signals


def _render_role_titles(careers_url: str) -> list[str]:
    """Render the JS careers page via Scraping Browser and pull anchor texts that
    look like job titles."""
    from playwright.sync_api import sync_playwright

    titles: list[str] = []
    with sync_playwright() as p:
        log.info("ATS: connecting over CDP for %s", careers_url)
        browser = p.chromium.connect_over_cdp(settings.brightdata_browser_url)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            page.goto(careers_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)  # let the ATS app paint its job list
            anchors = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: (a.innerText || '').trim(),
                    href: a.href || ''
                }));
            }""")
            page.close()
        finally:
            browser.close()

    # Keep anchors that look like role postings: multi-word title-ish text whose
    # href points at a job posting (not nav/social). Heuristics tuned for Ashby/
    # Greenhouse/Lever where each role is its own link.
    seen = set()
    for a in anchors:
        text = (a.get("text") or "").strip()
        href = (a.get("href") or "").lower()
        if not text or len(text) < 4 or len(text) > 90:
            continue
        if text.lower() in seen:
            continue
        looks_like_job_link = any(k in href for k in (
            "/job", "ashbyhq.com", "greenhouse.io", "lever.co", "workable", "/careers/", "gh_jid"))
        looks_like_title = bool(re.search(r"[A-Za-z].*\s.*[A-Za-z]", text)) and not text.lower().startswith(
            ("apply", "view all", "see all", "sign in", "log in", "home", "about", "powered by"))
        if looks_like_job_link and looks_like_title:
            seen.add(text.lower())
            titles.append(text)
    return titles


def _derive(titles: list[str], source_url: str) -> dict:
    functions = {"engineering": 0, "sales": 0, "marketing": 0, "product": 0, "operations": 0, "other": 0}
    gtm_roles: list[str] = []

    for t in titles:
        placed = False
        for name, pat in _FUNCTION_PATTERNS:
            if pat.search(t):
                functions[name] += 1
                placed = True
                break
        if not placed:
            functions["other"] += 1
        if _GTM_RE.search(t):
            gtm_roles.append(t)

    signals = {
        "open_roles": len(titles),
        "functions": {k: v for k, v in functions.items() if v},
        "roles_sample": titles[:12],
        "source_url": source_url,
    }
    if gtm_roles:
        signals["gtm_motion"] = gtm_roles[:5]
    return signals


# ── Collector wrapper ────────────────────────────────────────────────────────

class ATSCollector:
    """Collector: ATS/careers page → hiring signals."""
    name = "ATS"

    def applies_to(self, ctx) -> bool:
        return bool(ctx.careers_url)

    def collect(self, ctx) -> list:
        from .base import Signal
        ats = fetch_hiring_signals(ctx.careers_url)
        if not ats:
            return []
        url = ats.get("source_url", ctx.careers_url)
        facts = [f"{ats['open_roles']} open roles at {url}."]
        if ats.get("functions"):
            breakdown = ", ".join(f"{k}:{v}" for k, v in ats["functions"].items())
            facts.append(f"Role breakdown: {breakdown}.")
        if ats.get("gtm_motion"):
            roles = ", ".join(ats["gtm_motion"][:3])
            facts.append(f"GTM-motion roles present: {roles} — signals product-led→sales-led inflection.")
        signals = [
            Signal(section="hiring", fact=f, url=url, source="ATS", trust="medium",
                   key="hiring_signals", value=ats)
            for f in facts
        ]
        return signals
