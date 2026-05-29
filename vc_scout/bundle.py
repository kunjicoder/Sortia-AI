"""EVIDENCE_BUNDLE assembly.

Takes raw inputs (company name, SERP results, Scraping Browser site text) and
produces the structured dict that the triangulation LLM prompt operates on.

Bundle schema (all fields optional except entity.name):
{
  "entity": { "name", "one_liner", "sector", "stage", "domain" },
  "founder_claims": [{ "claim", "source": "company_site", "url" }],
  "web_evidence":   [{ "fact", "source_title", "url", "date" }],
  "derived_signals": {
      "funding":  { "total_raised", "last_round", "investors", "url" },
      "hiring":   { "open_roles", "functions", "enterprise_signals", "url" },
      "traction": { "notes", "url" }
  }
}

Design rules:
- OMIT fields we can't support from evidence. Never invent numbers.
- founder_claims come from the company's own site (Scraping Browser) — tagged
  as unverified until the triangulation LLM cross-checks them.
- web_evidence is everything from SERP — third-party, more trustworthy per item.
- derived_signals are extracted heuristically from SERP snippets; only populated
  when there's a clear signal.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# ── Patterns that indicate a SERP snippet is from a junk page ───────────────
# These snippets must not be used as the entity one_liner or web_evidence facts.
_JUNK_SNIPPET_RE = re.compile(
    r"(we[''']re hiring|join our team|exciting to work|open roles|job opening"
    r"|cookie\s+policy|privacy\s+policy|all rights reserved|sign up|log in"
    r"|subscribe to|newsletter)",
    re.IGNORECASE,
)

# ── Keyword heuristics for derived_signals ──────────────────────────────────

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

def assemble(
    company: str,
    serp_results: list[dict[str, Any]],
    site_text: str,
    site_url: str = "",
) -> dict[str, Any]:
    """Return the EVIDENCE_BUNDLE dict for the triangulation prompt."""
    entity = _build_entity(company, serp_results, site_url)
    web_evidence = _build_web_evidence(serp_results)
    founder_claims = _extract_founder_claims(site_text, site_url or entity.get("domain", ""))
    derived = _build_derived_signals(serp_results)

    bundle: dict[str, Any] = {
        "entity": entity,
        "web_evidence": web_evidence,
    }
    if founder_claims:
        bundle["founder_claims"] = founder_claims
    if derived:
        bundle["derived_signals"] = derived

    log.info(
        "Bundle assembled: %d web_evidence, %d founder_claims, derived=%s",
        len(web_evidence),
        len(founder_claims),
        list(derived.keys()),
    )
    return bundle


def find_homepage(company: str, serp_results: list[dict[str, Any]]) -> str:
    """Guess the company's homepage from SERP results.

    Prefers results whose URL matches the slugified company name over generic
    directories (crunchbase, linkedin, techcrunch, etc.).
    """
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


# ── Private helpers ──────────────────────────────────────────────────────────

def _build_entity(
    company: str,
    serp_results: list[dict[str, Any]],
    site_url: str,
) -> dict[str, Any]:
    entity: dict[str, Any] = {"name": company}

    # Intentionally do NOT put a one_liner in the entity — the LLM must
    # synthesise it from web_evidence so it reads like an analyst description,
    # not a copied careers-page quote.  (The SYSTEM_PROMPT enforces this rule.)

    domain = ""
    if site_url:
        parsed = urlparse(site_url)
        domain = parsed.netloc.removeprefix("www.")
    elif serp_results:
        domain_candidate = find_homepage(company, serp_results)
        if domain_candidate:
            domain = urlparse(domain_candidate).netloc.removeprefix("www.")
    if domain:
        entity["domain"] = domain

    return entity


def _build_web_evidence(serp_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for item in serp_results:
        fact = (item.get("description") or item.get("title") or "").strip()
        if not fact:
            continue
        # Drop snippets that are clearly from careers/boilerplate pages
        if _JUNK_SNIPPET_RE.search(fact):
            log.debug("Skipping junk snippet: %.80s", fact)
            continue
        url = item.get("url", "")
        entry: dict[str, Any] = {
            "fact": fact[:300],
            "source_title": (item.get("title") or "").strip()[:120],
            "url": url,
            "source_domain": urlparse(url).netloc.removeprefix("www.") if url else "",
        }
        if item.get("date"):
            entry["date"] = item["date"]
        evidence.append(entry)
    return evidence


def _extract_founder_claims(site_text: str, site_url: str) -> list[dict[str, Any]]:
    """Extract claim sentences from site text using a cheap LLM call.

    Returns [] if site_text is empty (Scraping Browser unavailable).
    """
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
                })
        return claims
    except json.JSONDecodeError:
        log.warning("Claim extraction: LLM returned non-JSON: %.200s", raw)
        return []


def _build_derived_signals(serp_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Heuristically extract funding, hiring, and traction signals from SERP."""
    derived: dict[str, Any] = {}

    funding_items = [r for r in serp_results if _FUNDING_RE.search(_item_text(r))]
    hiring_items = [r for r in serp_results if _HIRING_RE.search(_item_text(r))]
    traction_items = [r for r in serp_results if _TRACTION_RE.search(_item_text(r))]

    if funding_items:
        best = funding_items[0]
        funding: dict[str, Any] = {"url": best.get("url", "")}
        # Try to pull dollar amount
        amount_match = re.search(r"\$[\d,.]+\s*[mb]illion|\$[\d,.]+[mb]", _item_text(best), re.IGNORECASE)
        if amount_match:
            funding["total_raised"] = amount_match.group(0)
        round_match = re.search(r"(seed|series\s+[a-e]|pre-seed|series\s+[a-e]\d*)", _item_text(best), re.IGNORECASE)
        if round_match:
            funding["last_round"] = round_match.group(0).title()
        if funding.get("total_raised") or funding.get("last_round"):
            derived["funding"] = funding

    if hiring_items:
        best = hiring_items[0]
        derived["hiring"] = {
            "notes": _item_text(best)[:200],
            "url": best.get("url", ""),
        }

    if traction_items:
        best = traction_items[0]
        derived["traction"] = {
            "notes": _item_text(best)[:200],
            "url": best.get("url", ""),
        }

    return derived


def _item_text(item: dict[str, Any]) -> str:
    return f"{item.get('title', '')} {item.get('description', '')}".strip()
