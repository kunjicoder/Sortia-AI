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

from .bundle import assemble, find_careers_url, find_homepage, find_linkedin_company_url
from .config import settings
from .llm import complete_structured
from .models import Brief, CompetitivePositioning, HiringSignals, Recommendation, RedFlag, TractionSignals
from .sources import ats, linkedin, scraping_browser, serp

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
You reason ONLY over the EVIDENCE_BUNDLE provided. If a fact is not in the bundle, you do not know it.
Missing data is itself a signal — never fabricate precision.

EVIDENCE_BUNDLE contains:
- entity: company name and domain
- founder_claims: claims from the company's own site (Scraping Browser) — UNVERIFIED, cross-check these
- web_evidence: facts from independent SERP sources (each has url + source_domain) — higher trust
- derived_signals: funding/hiring/traction signals extracted from SERP snippets
- linkedin_signals: STRUCTURED, machine-read data from LinkedIn via Bright Data — a source no
  LLM tool can reach. INDEPENDENT third-party signal, NOT ground truth: employee_count is
  "members who list this company," which over- and under-counts real headcount and lags by
  months. Use it as corroboration. A LARGE divergence from a founder_claim (e.g. claim ~3× the
  LinkedIn figure) is a "worth verifying" flag → DIG_DEEPER, not a definitive contradiction.
  Small/plausible differences are NOT contradictions. Always state the caveat when you cite it.
- hiring_signals: role-level data from the company's OWN ATS (Ashby/Greenhouse/Lever). Fields:
  open_roles, functions (counts by team), gtm_motion (sales/AE/revenue roles), roles_sample.
  This is live hiring INTENT — use it for the Timing and Asymmetry drivers and to read the
  company's stage. gtm_motion roles signal a go-to-market inflection (product-led → sales-led).

━━━ HARD RULES — VIOLATION = INVALID OUTPUT ━━━

ENTITY GROUNDING (check FIRST): Before writing any brief, confirm the web_evidence actually
  describes a COMPANY matching entity.name — a product, startup, or business with signals like
  a website, funding, founders, users, or hiring. If the evidence is instead about a PERSON, a
  piece of LEGISLATION, a generic term, or an unrelated topic (e.g. results about a politician's
  bill when the query was a company name), the name did NOT resolve to a company. In that case:
  set recommendation="pass", lead red_flags with category="ambiguous_entity" explaining the name
  is ambiguous and what the evidence actually points to, and do NOT fabricate a company thesis.
  ✗ BAD: building a trading-insights thesis from results about Rep. Luna's H.R. 8795 bill.
  ✓ GOOD: red flag — "'Luna Bill' did not resolve to a company; results describe legislation by
          Rep. Anna Paulina Luna. Verify the company name or its public footprint."

ANTI-HALLUCINATION: Every named entity you introduce — acquisitions, customers, partnerships,
  specific people, specific metrics — MUST appear verbatim (or near-verbatim) in the `fact` text
  of a web_evidence item or in a founder_claims[].claim. Pointing to a URL is not enough — the
  specific name or number must be present in the snippet text for that URL. If you cannot find
  the exact name in the bundle text, do not use it. Omit it entirely.
  ✗ BAD: "The company acquired Yapify" (unless "Yapify" literally appears in a web_evidence fact)
  ✗ BAD: citing wisprflow.ai/blog for "Yapify acquisition" when no snippet mentions "Yapify"
  ✓ GOOD: "A 10× ARR increase is cited at [url]" (because "10×" appears in that snippet)

HIDDEN INSIGHT: Must be an inference or pattern derived from quoted evidence — NOT a new named
  fact. If it introduces any company name, person, product, or metric not in a snippet, discard it.
  ✗ BAD: "The acquisition of Yapify positions them well" (introduces uncited named entity)
  ✓ GOOD: "The $30M raise coming 5 months after the 10× ARR signal (per techcrunch.com) suggests
           strong capital efficiency that the round size alone understates."

ONE_LINER: Write a crisp 10-15 word analyst description of WHAT THE COMPANY DOES and FOR WHOM.
  Derive it by reading across multiple web_evidence items. Do NOT copy any sentence verbatim.
  Do NOT use careers-page language, employee quotes, or marketing slogans.
  ✗ BAD: "It's exciting to work on something that feels both ambitious and deeply human."
  ✗ BAD: "Talk to type. Wispr Flow." (slogan, not description)
  ✓ GOOD: "AI voice-to-text dictation app enabling users to type 4× faster by speaking."

FOUNDERS: Scan all web_evidence items for person names with roles (CEO, CTO, co-founder, etc.).
  If found, populate founders[]. Set linkedin_url from any LinkedIn URL in web_evidence for
  that person. If no founder names appear anywhere in web_evidence, return founders=[].
  Do NOT pad a founder's background with vague filler ("led product development for tech
  ventures"). State only what a snippet supports; if you know only the name and role, say only that.

THESIS: One falsifiable sentence built on a SPECIFIC fact from the bundle (a number, a named
  wedge, a growth rate). It must be a claim that could be proven wrong — not a marketing line.
  ✗ BAD: "X is redefining its category with an innovative platform." (vague, unfalsifiable)
  ✗ BAD: "X is a leading AI company transforming the industry."
  ✓ GOOD: "X is the first consumer dictation app to reach 10× ARR growth on a voice-OS wedge."
  Ban these words in the thesis: redefining, innovative, revolutionary, transforming, leading,
  cutting-edge, next-generation, seamless, empowering.

━━━ REASONING PROCESS ━━━

1. TRIANGULATE: For each founder_claim, find supporting or CONTRADICTING evidence across
   web_evidence and linkedin_signals.
   - A claim contradicted by an INDEPENDENT web_evidence FACT (different number, conflicting
     date, denied partnership) is a real contradiction — severity by how load-bearing it is.
   - A claim that merely diverges from linkedin_signals is a SOFT flag (data caveat above):
     mark is_contradiction=false, note it as "worth verifying," and route to DIG_DEEPER if the
     gap is large and the claim is central. Never assert a hard contradiction on LinkedIn alone.
   Surface contradictions with both URLs. High-severity unresolved contradiction → DIG_DEEPER.

2. SCORE four drivers 1–10, each citing a specific web_evidence URL.
   Asymmetry | Defensibility | Timing | Founder grit
   Ladder: 1-3 not-venture-scale · 4-6 plausible-10× · 7-8 real-moat-forming · 9-10 category-defining
   No evidence for a driver → confidence=Low, say so.
   Each rationale MUST quote the specific fact behind the score (a number, a named round, a
   named customer). A rationale with no concrete fact is invalid.
   ✗ BAD: "Rising demand for voice tech supports rapid market entry." (generic, no fact)
   ✓ GOOD: "$30M Series A from Menlo (techcrunch.com) funds 18-24mo of runway at current burn."

3. RED TEAM: 3 likeliest failure paths. Each names the SPECIFIC weakness in THIS company's
   evidence — not a risk that applies to any startup. Tie each to what would invalidate it.
   ✗ BAD: "Delays in product development could hinder momentum." (true of every company)
   ✓ GOOD: "All traction is self-reported (10× ARR, no third-party source) — if the base was
            near-zero, the multiple is noise."

4. HIDDEN INSIGHT: One INFERENCE connecting two cited facts. It introduces NO new named entity
   (no company, person, product, or metric not already in a snippet). If you find yourself
   naming a thing here, it belongs in traction/press, not hidden_insight.
   ✗ BAD: "The acquisition of Yapify strengthens their position." (introduces a named fact)
   ✓ GOOD: "A $30M round landing ~5 months after the 10× ARR signal points to capital
            efficiency the headline number alone understates."

━━━ PRINCIPLES ━━━
Fundraising ≠ traction. Pilots ≠ PMF. Logos ≠ deployments.
Ask "what budget line does this replace?" Flag top-down TAM inflation.

━━━ OUTPUT FIELD RULES ━━━
- sources[]: every URL from web_evidence you actually used — must not be empty
- contradictions[].is_contradiction: true = contradicted, false = corroborated
- contradictions[].severity: "high" | "medium" | "low"
- decision_drivers: exactly four entries, one per named driver
- recommendation: "take_call" (GO) | "dig_deeper" (SECOND LOOK) | "pass" (NO-GO)
- thesis: single falsifiable sentence (see THESIS rule). No banned words.
- CONSISTENCY: structured fields must agree with prose. If traction.summary states a funding
  round, that round MUST also appear as a funding_history[] entry (amount, stage, investor,
  date as available). Never claim a fact in prose and leave its structured field empty.

━━━ NEW FIELD RULES ━━━

overview: 2-4 sentences synthesizing what the company does, who it's for, and its apparent
  stage — read from web_evidence only, not marketing copy. This is the analyst's opening
  paragraph. Write it after reading all evidence.

decision_drivers[].supporting_evidence: 1-3 EvidencePoints per driver. Each must be a real
  quoted fact from the bundle with its url and source_type ("serp"|"site"|"linkedin"|"ats").
  If a driver has genuinely no evidence, confidence=Low and supporting_evidence=[].

conviction: "High" only when ≥2 independent sources corroborate the thesis. "Low" when the
  brief leans on a single source or self-reported claims only. "Medium" otherwise.
  State the basis briefly in recommendation_rationale.

market.segment: required — state the segment the company operates in.
market.sizing_note: only populate if a TAM/SAM/market-size figure appears verbatim in evidence.
  Omit/null if no figure is cited. Do NOT invent market sizes.
market.tailwinds/headwinds: short phrases (≤10 words each) grounded in evidence. Max 3 each.
market.competitors: named only if a competitor appears by name in a web_evidence snippet.

research_log: ONE entry per source that actually contributed. Always include SERP API. Include
  Scraping Browser, LinkedIn, ATS only if those bundle sections are present.
  - examined: what URL or data type was looked at (e.g. "wisprflow.ai homepage + /about")
  - found: what came back concretely (e.g. "8 web snippets, Yapify acquisition confirmed,
    $30M raise confirmed" or "No data returned")
  - inference: what it tells an investor in one sentence (or "Inconclusive")
  This section SHOWS THE WORK — be concrete about what each source contributed.

data_completeness: set serp/company_site/linkedin/ats booleans to reflect which bundle sections
  are present (non-empty). notes: 1-2 sentences on gaps and how they limit confidence.

diligence_questions: 3-5 sharp questions a sharp investor would ask THIS specific founder.
  Each must target a gap, risk, or unverified claim in THIS evidence — not generic startup
  questions. Tie each to a specific observation from the bundle.
  ✗ BAD: "What is your go-to-market strategy?" (generic)
  ✓ GOOD: "The 10× ARR figure is self-reported with no third-party corroboration — what is
          the actual base ARR and how is it measured?" (specific, tied to a gap)

- Do NOT fabricate. Unknown fields → null or omit."""


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

    # 2b. Bright Data Web Scraper API — LinkedIn company signals (high-trust,
    #     a source LLM tools can't reach). Async/slow: in the live path this is
    #     only attempted when a dataset is configured; the demo runs from cache.
    linkedin_url = find_linkedin_company_url(serp_data)
    linkedin_signals = linkedin.fetch_company_signals(linkedin_url) if linkedin_url else {}
    if linkedin_signals:
        log.info("LinkedIn signals: %s", list(linkedin_signals.keys()))

    # 2c. ATS / careers page — role-level hiring intent (leading GTM signal).
    careers_url = find_careers_url(serp_data)
    ats_signals = ats.fetch_hiring_signals(careers_url) if careers_url else {}
    if ats_signals:
        log.info("ATS signals: %d roles, gtm=%s", ats_signals.get("open_roles"),
                 bool(ats_signals.get("gtm_motion")))

    # 3. Assemble EVIDENCE_BUNDLE
    bundle = assemble(
        company=company,
        serp_results=serp_data,
        site_text=site_text,
        site_url=homepage,
        linkedin_signals=linkedin_signals,
        ats_signals=ats_signals,
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
    from .models import DataCompleteness, ResearchStep
    return Brief(
        company_name=company,
        one_liner="Insufficient public data to generate a brief.",
        overview="No public information found for this company via web search.",
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
        conviction="Low",
        recommendation_rationale=(
            "No public information is available for this company. "
            "Cannot make an informed assessment without further context."
        ),
        research_log=[
            ResearchStep(
                source="SERP API",
                examined=f"Web search for '{company}'",
                found="No data returned",
                inference="Company may be stealth, pre-launch, or the name is ambiguous.",
            )
        ],
        data_completeness=DataCompleteness(
            serp=False,
            company_site=False,
            linkedin=False,
            ats=False,
            notes="Zero SERP results — all signals absent.",
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
