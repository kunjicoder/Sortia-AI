"""Main agent loop — V2: Bright Data SERP + Scraping Browser → evidence bundle → triangulation brief.

V1 (SERP-only) still works when BRIGHTDATA_BROWSER_URL is not set.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .bundle import assemble, find_homepage
from .config import settings
from .llm import complete_structured
from .models import Brief, CompetitivePositioning, HiringSignals, Recommendation, RedFlag, TractionSignals
from .sources import scraping_browser, serp

log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent / "demo_cache"


def _slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def _load_cache(company: str) -> Brief | None:
    path = _CACHE_DIR / f"{_slug(company)}.json"
    if path.exists():
        log.info("Demo cache hit for %s (%s)", company, path.name)
        return Brief.model_validate_json(path.read_text(encoding="utf-8"))
    return None


@dataclass
class ScoutInput:
    company_name: str
    founder_name: Optional[str] = None


@dataclass
class ScoutResult:
    brief: Brief
    serp_ms: int
    llm_ms: int
    source_count: int
    browser_ms: int = 0

    @property
    def total_ms(self) -> int:
        return self.serp_ms + self.browser_ms + self.llm_ms

    def stats_line(self) -> str:
        parts = [f"{self.source_count} sources read"]
        if self.browser_ms:
            parts.append(f"site scraped in {self.browser_ms / 1000:.1f}s")
        parts.append(f"brief generated in {self.total_ms / 1000:.1f}s")
        return " · ".join(parts)


# ── Triangulation SYSTEM_PROMPT ──────────────────────────────────────────────
# Based on the investor-memo prompt spec. Produces structured JSON (Brief schema)
# rather than markdown, but applies the same triangulation logic.

SYSTEM_PROMPT = """You are the reasoning layer of VC Scout — a top-decile angel reviewing inbound deal flow.
You reason only over the EVIDENCE_BUNDLE provided. If a fact is not present and not marked a
founder_claim, you do not know it. Missing data is itself a signal — never fabricate precision.

EVIDENCE_BUNDLE contains:
- entity: company metadata
- founder_claims: claims from the company's own site (Scraping Browser) — UNVERIFIED
- web_evidence: facts from independent web sources (Bright Data SERP) — higher trust
- derived_signals: funding/hiring/traction signals heuristically extracted from SERP

YOUR REASONING PROCESS:
1. TRIANGULATE: For each founder_claim, find supporting or CONTRADICTING web_evidence.
   Surface every contradiction. A high-severity unresolved contradiction caps verdict at DIG_DEEPER.

2. SCORE four drivers 1–10. Each score MUST name the evidence justifying it.
   - Asymmetry: Does the insight exploit a non-obvious wedge (data access, regulatory, distribution)?
   - Defensibility: Network effects, data moat, switching cost, or just features?
   - Timing: Is the market timing right? Tailwinds or headwinds?
   - Founder grit: Track record, domain depth, evidence of resilience.
   Scoring ladder: 1-3 = not-venture-scale, 4-6 = plausible-10x, 7-8 = real-moat-forming, 9-10 = category-defining.
   If no evidence exists for a driver, set confidence=Low and say so in rationale.

3. RED TEAM: Identify the 3 likeliest ways this company dies. State each as a failure_path string.
   Include the cheapest evidence that would invalidate each concern.

4. HIDDEN INSIGHT: One non-obvious observation grounded in a specific piece of evidence.

PRINCIPLES:
- Fundraising ≠ traction. Pilots ≠ PMF. Logos ≠ deployments.
- Ask "what budget line does this replace?" Favor bottom-up market math.
- Flag top-down TAM inflation. Prefer specifics over adjectives.

FIELD RULES:
- contradictions[].is_contradiction = true if claim is contradicted, false if corroborated
- contradictions[].severity = "high" | "medium" | "low"
- decision_drivers must include all four named drivers (Asymmetry, Defensibility, Timing, Founder grit)
- recommendation: "take_call" (GO), "dig_deeper" (SECOND LOOK), or "pass" (NO-GO)
- sources: every URL from the evidence you actually used
- Do NOT fabricate data. If a field is unknown, use null or omit it.
- thesis: single sentence investment thesis"""


def build_brief(scout_input: ScoutInput) -> ScoutResult:
    """End-to-end pipeline: SERP + Scraping Browser → evidence bundle → triangulation brief."""
    company = scout_input.company_name
    log.info("Building brief for %s", company)

    if settings.use_demo_cache:
        cached = _load_cache(company)
        if cached is not None:
            return ScoutResult(
                brief=cached,
                serp_ms=0,
                llm_ms=0,
                source_count=len(cached.sources),
            )

    # 1. Bright Data SERP API
    t0 = time.perf_counter()
    serp_data = serp.search_company(company)
    serp_ms = int((time.perf_counter() - t0) * 1000)
    log.info("SERP: %d results in %dms", len(serp_data), serp_ms)

    if not serp_data:
        log.warning("No SERP results for %s — returning insufficient-data brief", company)
        brief = _insufficient_data_brief(company)
        return ScoutResult(brief=brief, serp_ms=serp_ms, llm_ms=0, source_count=0)

    # 2. Bright Data Scraping Browser (best-effort — skipped when URL not configured)
    homepage = find_homepage(company, serp_data)
    t1 = time.perf_counter()
    site_text = scraping_browser.fetch_site_text(homepage) if homepage else ""
    browser_ms = int((time.perf_counter() - t1) * 1000)
    if site_text:
        log.info("Scraping Browser: %d chars from %s in %dms", len(site_text), homepage, browser_ms)
    else:
        log.info("Scraping Browser: unavailable — proceeding SERP-only")
        browser_ms = 0

    # 3. Assemble EVIDENCE_BUNDLE
    bundle = assemble(
        company=company,
        serp_results=serp_data,
        site_text=site_text,
        site_url=homepage,
    )
    log.info("Bundle: %d web_evidence, %d founder_claims",
             len(bundle.get("web_evidence", [])),
             len(bundle.get("founder_claims", [])))

    # 4. LLM triangulation synthesis
    t2 = time.perf_counter()
    brief = complete_structured(
        prompt=f"EVIDENCE_BUNDLE:\n{json.dumps(bundle, indent=2)}",
        schema=Brief,
        system=SYSTEM_PROMPT,
    )
    llm_ms = int((time.perf_counter() - t2) * 1000)
    source_count = len(brief.sources)
    log.info("LLM: %d sources cited, %d contradictions in %dms",
             source_count, len(brief.contradictions), llm_ms)

    result = ScoutResult(
        brief=brief,
        serp_ms=serp_ms,
        browser_ms=browser_ms,
        llm_ms=llm_ms,
        source_count=source_count,
    )
    log.info("Total: %s", result.stats_line())
    return result


def _insufficient_data_brief(company: str) -> Brief:
    """Return a well-formed Brief when SERP finds nothing."""
    return Brief(
        company_name=company,
        one_liner="Insufficient public data to generate a brief.",
        thesis="Cannot form a thesis without public evidence.",
        founders=[],
        traction=TractionSignals(summary="No public traction signals found via web search."),
        hiring=HiringSignals(summary="No public hiring data found."),
        competitive_positioning=CompetitivePositioning(
            market_segment="Unknown",
            differentiation="Insufficient data.",
        ),
        red_flags=[
            RedFlag(
                category="missing_footprint",
                detail="No search results returned for this company name. "
                       "Verify the name is correct or check private/stealth status.",
            )
        ],
        recommendation=Recommendation.PASS,
        recommendation_rationale=(
            "No public information is available for this company. "
            "Cannot make an informed assessment without further context."
        ),
    )


def main() -> None:
    """CLI entrypoint: `python -m vc_scout.orchestrator <company name>`"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m vc_scout.orchestrator <company name>")
        sys.exit(1)
    company = " ".join(sys.argv[1:])
    result = build_brief(ScoutInput(company_name=company))
    print(result.brief.model_dump_json(indent=2))
    print(f"\n# {result.stats_line()}", file=sys.stderr)


if __name__ == "__main__":
    main()
