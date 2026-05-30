"""EVIDENCE_BUNDLE assembly — Signal-aware version.

Takes a list of Signal objects (emitted by collectors) plus raw EntityContext
and produces the structured dict the triangulation LLM prompt reasons over.

Bundle schema:
{
  "entity":          { name, domain, company_type },
  "sections": {
    "market":        [ { fact, url, source, trust, date? } ],
    "team":          [ ... ],
    "product":       [ ... ],
    "traction":      [ ... ],
    "funding":       [ ... ],
    "competition":   [ ... ],
    "hiring":        [ ... ],
    "business_model": [ ... ],
    "risks":         [ ... ],
  },
  "founder_claims":  [ { claim, source, url } ],   # extracted from site_text
  "research_log":    [ { source, examined, found } ]  # per-collector summary
}
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from .sources.base import EntityContext, Signal

log = logging.getLogger(__name__)

# ── Patterns (kept for SerpCollector + backward-compat helpers) ─────────────

_JUNK_SNIPPET_RE = re.compile(
    r"(we[''']re hiring|join our team|exciting to work|open roles|job opening"
    r"|cookie\s+policy|privacy\s+policy|all rights reserved|sign up|log in"
    r"|subscribe to|newsletter)",
    re.IGNORECASE,
)

_FUNDING_RE = re.compile(
    r"(raised?|closes?|secures?|announces?|seed|series\s+[a-d]|pre-seed"
    r"|funding|round|million|billion|\$[\d,.]+[mb])",
    re.IGNORECASE,
)
_HIRING_RE = re.compile(
    r"(hiring|join\s+(our|the)\s+team|we['']re\s+(growing|hiring)|open\s+roles?"
    r"|careers?|job\s+openings?)",
    re.IGNORECASE,
)
_TRACTION_RE = re.compile(
    r"(users?|customers?|revenue|arr|mrr|growth|launched?|product\s+hunt"
    r"|hacker\s+news|downloads?|installs?|star[s]?\s+on\s+github)",
    re.IGNORECASE,
)


# ── Public API ───────────────────────────────────────────────────────────────

def assemble_from_signals(
    ctx: EntityContext,
    signals: list[Signal],
    collector_log: list[dict],
) -> dict[str, Any]:
    """Build the memo-structured EVIDENCE_BUNDLE from collected Signals."""
    # Group signals by section
    sections: dict[str, list[dict]] = {}
    for sig in signals:
        if sig.key == "site_text":
            continue  # handled separately as founder_claims
        entry: dict[str, Any] = {
            "fact": sig.fact,
            "url": sig.url,
            "source": sig.source,
            "trust": sig.trust,
        }
        if sig.date:
            entry["date"] = sig.date
        sections.setdefault(sig.section, []).append(entry)

    # Extract founder claims from site_text signal if present
    site_signal = next((s for s in signals if s.key == "site_text"), None)
    founder_claims = []
    if site_signal and site_signal.value:
        founder_claims = _extract_founder_claims(site_signal.value, site_signal.url)

    bundle: dict[str, Any] = {
        "entity": {
            "name": ctx.company,
            "domain": ctx.domain,
            "company_type": ctx.company_type,
        },
        "sections": sections,
        "research_log": collector_log,
    }
    if founder_claims:
        bundle["founder_claims"] = founder_claims

    total_signals = sum(len(v) for v in sections.values())
    log.info(
        "Bundle: %d signals across %d sections, %d founder_claims",
        total_signals, len(sections), len(founder_claims),
    )
    return bundle


def build_collector_log(
    collector_name: str,
    ctx: EntityContext,
    signals: list[Signal],
) -> dict[str, Any]:
    """Build a research_log entry from a collector's run."""
    if not signals:
        return {"source": collector_name, "examined": _examined(collector_name, ctx), "found": "No data returned"}
    facts_preview = "; ".join(s.fact[:60] for s in signals[:3])
    return {
        "source": collector_name,
        "examined": _examined(collector_name, ctx),
        "found": f"{len(signals)} signals: {facts_preview}{'…' if len(signals) > 3 else ''}",
    }


def _examined(name: str, ctx: EntityContext) -> str:
    if name == "SERP API":
        return f"Web search for '{ctx.company}' ({len(ctx.serp_results)} results)"
    if name == "Scraping Browser":
        return f"https://{ctx.domain} + subpages" if ctx.domain else "company site"
    if name == "LinkedIn":
        return ctx.linkedin_company_url or "LinkedIn company page"
    if name == "ATS":
        return ctx.careers_url or "careers page"
    if name == "App Store":
        return ctx.appstore_url or "App Store listing"
    if name == "GitHub":
        return ctx.github_url or "GitHub repo"
    if name == "LinkedIn People":
        urls = ctx.linkedin_people_urls
        return f"{len(urls)} founder profile(s)" if urls else "LinkedIn people"
    return name


# ── Backward-compat helpers (used by legacy code paths in tests) ─────────────

def find_homepage(company: str, serp_results: list[dict[str, Any]]) -> str:
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    directory_domains = {
        "crunchbase.com", "linkedin.com", "techcrunch.com", "forbes.com",
        "bloomberg.com", "reuters.com", "wsj.com", "ycombinator.com",
        "twitter.com", "x.com", "facebook.com", "instagram.com",
        "github.com", "wikipedia.org", "glassdoor.com", "pitchbook.com",
    }
    best: str = ""
    for item in serp_results:
        url = item.get("url", "")
        if not url:
            continue
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().removeprefix("www.")
        if netloc in directory_domains:
            continue
        if slug in netloc.replace(".", "").replace("-", ""):
            return f"https://{netloc}"
        if not best:
            best = f"https://{parsed.netloc}"
    return best


def find_linkedin_company_url(serp_results: list[dict[str, Any]]) -> str:
    for item in serp_results:
        url = item.get("url", "")
        if "linkedin.com/company/" in url.lower():
            return url.split("?")[0]
    return ""


_ATS_URL_RE = re.compile(r"(ashbyhq\.com|greenhouse\.io|lever\.co|jobs\.[a-z0-9-]+\.|/careers)", re.I)


def find_careers_url(serp_results: list[dict[str, Any]]) -> str:
    for item in serp_results:
        url = item.get("url", "")
        if url and _ATS_URL_RE.search(url):
            return url.split("?")[0]
    return ""


# ── Private helpers ───────────────────────────────────────────────────────────

def _extract_founder_claims(site_text: str, site_url: str) -> list[dict[str, Any]]:
    if not site_text or len(site_text) < 50:
        return []
    try:
        return _llm_extract_claims(site_text, site_url)
    except Exception as exc:
        log.warning("Claim extraction failed: %s", exc)
        return []


def _llm_extract_claims(site_text: str, site_url: str) -> list[dict[str, Any]]:
    from .llm import complete
    prompt = (
        "You are extracting verifiable factual claims from a company's own website.\n\n"
        "Extract up to 8 specific, verifiable claims the company makes about itself. "
        "Focus on: team size, customer count, revenue metrics, funding, product capabilities, "
        "integrations, geographic presence. Ignore marketing fluff.\n\n"
        "Return a JSON array of objects: [{\"claim\": \"...\"}]\n"
        "One sentence per claim. Return ONLY the JSON array.\n\n"
        f"SITE TEXT:\n{site_text[:3000]}"
    )
    raw = complete(prompt)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        claims = []
        for item in items:
            if isinstance(item, dict) and item.get("claim"):
                claims.append({
                    "claim": str(item["claim"])[:200],
                    "source": "company_site",
                    "url": site_url,
                    "trust": "low",
                })
        return claims
    except json.JSONDecodeError:
        log.warning("Claim extraction: LLM returned non-JSON: %.200s", raw)
        return []
