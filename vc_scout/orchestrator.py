"""Main pipeline — parallel collector architecture.

Build order:
  1. SERP → EntityContext (resolve domain, LinkedIn URL, company type, ...)
  2. All applicable collectors run concurrently (ThreadPoolExecutor, per-collector timeout)
  3. Signals grouped into memo-structured EVIDENCE_BUNDLE
  4. LLM triangulation → InvestmentMemo (structured JSON)
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .bundle import assemble_from_signals, build_collector_log
from .config import settings
from .llm import complete_structured
from .models import (
    DataCompleteness, InvestmentMemo, Recommendation, RedFlag, ResearchStep,
)
from .sources.base import EntityContext, Signal
from .sources.registry import COLLECTORS
from .sources.resolve import resolve
from .sources.serp import search_company

log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent / "demo_cache"
_COLLECTOR_TIMEOUT = 90   # seconds per collector
_GLOBAL_BUDGET = 150      # seconds total wall-clock budget for all collectors


def _slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def _load_cache(company: str) -> InvestmentMemo | None:
    path = _CACHE_DIR / f"{_slug(company)}.json"
    if not path.exists():
        return None
    try:
        log.info("Demo cache hit for %s (%s)", company, path.name)
        return InvestmentMemo.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Demo cache %s failed validation (%s) — falling through to live pipeline",
                    path.name, exc)
        return None


@dataclass
class ScoutInput:
    company_name: str
    founder_name: Optional[str] = None


@dataclass
class ScoutResult:
    memo: InvestmentMemo
    serp_ms: int
    collect_ms: int
    llm_ms: int
    source_count: int

    @property
    def total_ms(self) -> int:
        return self.serp_ms + self.collect_ms + self.llm_ms

    def stats_line(self) -> str:
        parts = [f"{self.source_count} sources read"]
        if self.collect_ms:
            parts.append(f"collected in {self.collect_ms / 1000:.1f}s")
        parts.append(f"brief generated in {self.total_ms / 1000:.1f}s")
        return " · ".join(parts)


# ── Synthesis SYSTEM_PROMPT ──────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the reasoning layer of VC Scout — a top-decile angel investor writing
a first-pass deal memo. You reason ONLY over the EVIDENCE_BUNDLE provided. If a fact is not in
the bundle, you do not know it. Missing data is itself a signal — never fabricate precision.

EVIDENCE_BUNDLE contains:
- entity: company name, domain, company_type (dev_tool | consumer_app | b2b_saas | unknown)
- sections: signals grouped by section (market, team, product, traction, funding, competition,
  hiring, business_model, risks). Each signal has: fact, url, source, trust (high|medium|low).
  high-trust = independent sources (SERP, LinkedIn, App Store, GitHub)
  medium-trust = structured but first-party (ATS, Scraping Browser structured data)
  low-trust = self-reported site copy — UNVERIFIED, cross-check against high-trust sources
- founder_claims: verifiable claims extracted from the company site — LOW TRUST, unverified
- research_log: which collectors ran and what they returned

━━━ HARD RULES — VIOLATION = INVALID OUTPUT ━━━

ENTITY GROUNDING: Before writing anything, confirm sections[] actually describes a COMPANY
  (product, startup, or business with signals: website, funding, founders, users, hiring). If
  evidence describes a PERSON, LEGISLATION, or unrelated topic, set recommendation="pass",
  add red_flag category="ambiguous_entity", do NOT fabricate a thesis.

ANTI-HALLUCINATION: Every named entity you introduce (acquisitions, customers, partnerships,
  specific metrics, person names) MUST appear verbatim in a fact text. Pointing to a URL is
  not enough — the specific name/number must be in the fact text for that URL. If you cannot
  find the exact name in the bundle, omit it entirely.

HIDDEN INSIGHT: One inference connecting two cited facts — introduces NO new named entity.
  ✗ "The acquisition of Yapify positions them well" (introduces uncited entity)
  ✓ "$30M raise 5 months after 10× ARR signal → capital efficiency understated"

ONE_LINER: 10-15 word analyst description of WHAT the company does and FOR WHOM. Synthesize
  from web_evidence. Never copy marketing/careers slogans.
  ✗ "Talk to type. Wispr Flow." (slogan)
  ✓ "AI voice dictation app enabling users to compose text 4× faster by speaking"

FOUNDERS: Populate from evidence only.
  - university: only if literally named in a fact. Never guess.
  - prior_companies: only named companies that appear in fact text.
  - prior_exits_or_scaling: only if an exit/scaling event is explicitly mentioned.
  - domain_fit: 1 sentence on why background fits this problem, grounded in evidence.
  - Never pad with generic statements ("led product development for tech ventures").

THESIS: One falsifiable sentence anchored to a SPECIFIC fact (number, named wedge, growth rate).
  Must be a claim that could be proven wrong. Ban these words: redefining, innovative,
  revolutionary, transforming, leading, cutting-edge, next-generation, seamless, empowering.
  ✗ "X is redefining its category with an innovative AI platform" (vague, banned words)
  ✓ "X is the first consumer dictation app to reach 10× ARR growth on a voice-OS wedge"

DRIVER RATIONALES: Each must quote the specific fact behind the score.
  ✗ "Rising demand for voice tech supports rapid market entry" (generic)
  ✓ "$30M Series A from Menlo (techcrunch.com) funds 18-24mo runway at current burn"

FAILURE PATHS: Each names THIS company's specific weakness tied to THIS evidence. Not generic.
  ✗ "Delays in product development could hinder momentum" (true of every startup)
  ✓ "All ARR growth is self-reported with no third-party corroboration — if base was near-zero,
     the 10× multiple is noise"

CONSISTENCY: Structured fields must agree with prose. A funding round in prose → FundingRound
  entry. A metric in traction.summary → must appear in supporting_evidence.

LINKEDIN CAVEAT: linkedin_signals.employee_count is "members who list this company" — over/
  under-counts real headcount, lags by months. Use as corroboration only. Large divergence from
  founder claim → DIG_DEEPER flag, NOT a hard contradiction. State this caveat when citing it.

━━━ MEMO SECTION INSTRUCTIONS ━━━

For each section, fill summary + key_points + evidence + confidence:
  - summary: 1-3 sentences of analyst prose from THIS section's signals only.
  - key_points: 2-5 bullet phrases (not full sentences) — the punchy highlights.
  - evidence: 1-3 EvidencePoints per section: { fact, url, source, trust }
  - confidence: High = ≥2 independent (high-trust) sources corroborate; Medium = 1 high-trust
    or multiple medium; Low = low-trust or self-reported only.

market: segment, TAM/SAM only if a size figure appears in facts (else omit), tailwinds,
  why-now, competitors named only if they appear in a fact.

team: Populate from web_evidence facts mentioning founder names + roles. For each founder,
  extract university, prior_companies, domain_fit — only from evidence. Include evidence[]
  with EvidencePoints for each pedigree fact cited.
team_assessment: overall completeness (solo founder? CTO present?), gaps, repeat-founder signal.

product: what it does, capabilities, maturity stage — from site facts and SERP.
traction: distinguish self-reported (low trust) from independent (high trust). State which.
  If only self-reported data exists, say so explicitly and set confidence=Low.
business_model: pricing model, monetization, tiers — from pricing page or SERP facts only.
competition: named competitors (only from evidence), differentiation, moat.
hiring_gtm: ATS role mix + GTM motion signal. If no ATS data, say so and set confidence=Low.

━━━ VERDICT MACHINERY ━━━

1. SCORE four drivers 1–10, each citing a specific evidence URL and fact.
   Asymmetry | Defensibility | Timing | Founder grit
   Ladder: 1-3 not-venture-scale · 4-6 plausible-10× · 7-8 real-moat-forming · 9-10 category-defining
   confidence=Low when a driver has no corroborating evidence.

2. EXECUTIVE SUMMARY: 3-5 sentences. Opportunity, why interesting, the verdict rationale.
   DO NOT just restate the one_liner. Show the reasoning.

3. RECOMMENDATION: "take_call" | "dig_deeper" | "pass"
   conviction: High = ≥2 independent sources corroborate thesis. Low = single source or
   self-reported only. State the basis in recommendation_rationale.

4. DILIGENCE QUESTIONS: 3-5 sharp questions targeting THIS company's specific gaps.
   Target: retention, margins, CAC, real revenue base — facts public data cannot confirm.
   ✗ "What is your go-to-market strategy?" (generic)
   ✓ "The 10× ARR growth is self-reported — what is the base ARR and how measured?" (specific)

5. research_log: one entry per source that contributed data. State what was examined, found,
   and the investor-relevant inference. Be concrete.
6. data_completeness: set booleans based on which bundle sections are non-empty.

━━━ OUTPUT RULES ━━━
- sources[]: every URL you actually used — must not be empty.
- decision_drivers: exactly 4 entries.
- Each MemoSection.confidence: "High" | "Medium" | "Low".
- Do NOT fabricate. Unknown fields → null or omit."""


def build_brief(scout_input: ScoutInput) -> ScoutResult:
    """End-to-end pipeline: SERP → parallel collectors → memo bundle → InvestmentMemo."""
    company = scout_input.company_name
    log.info("Building memo for %s", company)

    if settings.use_demo_cache:
        cached = _load_cache(company)
        if cached is not None:
            return ScoutResult(memo=cached, serp_ms=0, collect_ms=0, llm_ms=0,
                               source_count=len(cached.sources))

    # 1. SERP — initial pass, resolve EntityContext
    t0 = time.perf_counter()
    serp_results = search_company(company)
    serp_ms = int((time.perf_counter() - t0) * 1000)
    log.info("SERP: %d results in %dms", len(serp_results), serp_ms)

    if not serp_results:
        log.warning("No SERP results for %s — returning insufficient-data memo", company)
        memo = _insufficient_data_memo(company)
        return ScoutResult(memo=memo, serp_ms=serp_ms, collect_ms=0, llm_ms=0, source_count=0)

    ctx: EntityContext = resolve(company, serp_results)

    # 2. Parallel collection — all applicable collectors with per-collector timeout
    t1 = time.perf_counter()
    all_signals: list[Signal] = []
    collector_log: list[dict] = []

    applicable = [c for c in COLLECTORS if c.applies_to(ctx)]
    log.info("Running %d collectors: %s", len(applicable), [c.name for c in applicable])

    with ThreadPoolExecutor(max_workers=len(applicable) or 1) as exe:
        future_to_collector = {exe.submit(c.collect, ctx): c for c in applicable}
        deadline = time.perf_counter() + _GLOBAL_BUDGET
        for fut in as_completed(future_to_collector, timeout=max(1, deadline - time.perf_counter())):
            col = future_to_collector[fut]
            try:
                signals = fut.result(timeout=_COLLECTOR_TIMEOUT)
                all_signals.extend(signals)
                collector_log.append(build_collector_log(col.name, ctx, signals))
                log.info("Collector %s: %d signals", col.name, len(signals))
            except Exception as exc:
                log.warning("Collector %s failed: %s: %s", col.name, type(exc).__name__, exc)
                collector_log.append(build_collector_log(col.name, ctx, []))

    collect_ms = int((time.perf_counter() - t1) * 1000)
    log.info("Collection: %d signals in %dms", len(all_signals), collect_ms)

    # 3. Assemble memo-structured EVIDENCE_BUNDLE
    bundle = assemble_from_signals(ctx, all_signals, collector_log)
    log.info("Bundle sections: %s", list(bundle.get("sections", {}).keys()))

    # 4. LLM synthesis → InvestmentMemo
    t2 = time.perf_counter()
    memo = complete_structured(
        prompt=f"EVIDENCE_BUNDLE:\n{json.dumps(bundle, indent=2)}",
        schema=InvestmentMemo,
        system=SYSTEM_PROMPT,
    )
    llm_ms = int((time.perf_counter() - t2) * 1000)
    source_count = len(memo.sources)
    log.info("LLM: %d sources cited in %dms", source_count, llm_ms)

    result = ScoutResult(
        memo=memo,
        serp_ms=serp_ms,
        collect_ms=collect_ms,
        llm_ms=llm_ms,
        source_count=source_count,
    )
    log.info("Total: %s", result.stats_line())
    return result


def _insufficient_data_memo(company: str) -> InvestmentMemo:
    return InvestmentMemo(
        company_name=company,
        one_liner="Insufficient public data to generate a memo.",
        executive_summary="No public information found for this company via web search.",
        recommendation=Recommendation.PASS,
        conviction="Low",
        recommendation_rationale="No public information available — cannot make an informed assessment.",
        risks_red_flags=[RedFlag(
            category="missing_footprint",
            detail="No SERP results returned. Verify the name or check stealth/private status.",
        )],
        research_log=[ResearchStep(
            source="SERP API",
            examined=f"Web search for '{company}'",
            found="No data returned",
            inference="Company may be stealth, pre-launch, or the name is ambiguous.",
        )],
        data_completeness=DataCompleteness(
            serp=False, company_site=False, linkedin=False, ats=False,
            notes="Zero SERP results — all signals absent.",
        ),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m vc_scout.orchestrator <company name>")
        sys.exit(1)
    company = " ".join(sys.argv[1:])
    result = build_brief(ScoutInput(company_name=company))
    print(result.memo.model_dump_json(indent=2))
    print(f"\n# {result.stats_line()}", file=sys.stderr)


if __name__ == "__main__":
    main()
