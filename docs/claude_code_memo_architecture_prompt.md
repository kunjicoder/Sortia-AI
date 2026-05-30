# VC Scout — Investment-Memo Architecture (paste into Claude Code at repo root)

You are my senior engineer on **VC Scout** (Bright Data hackathon, GTM Intelligence). We are
re-architecting the system around the document a real VC analyst submits: the **deal memo** —
a 1–3 page first-pass investment memo that decides whether a company is worth deeper diligence.

Goal: pull the **maximum possible PUBLIC information** the memo needs, from the live web via
Bright Data, and synthesize it into a memo-structured brief that shows its reasoning.

## Non-negotiable ground rules
- **No agent frameworks.** Direct SDK + Python stdlib only (`concurrent.futures` is fine).
- **Ship beats perfect.** App stays runnable after every step. Never break the SERP-only path.
- **Every collector degrades to empty on failure** and never crashes the pipeline.
- **Anti-hallucination is sacred.** No invented numbers/names. Missing data → "not found."
- Read before edit. Small commits. `py_compile` + tests before "done."

---

## PART A — The memo → source → Bright Data mapping (this is the design)

Build collection to fill these memo sections. Each row: memo section → signals an analyst wants
→ public source → Bright Data product. Universal sources run for every company; adaptive sources
run based on company type.

| Memo section | Signals analyst wants | Public source | Bright Data product |
|---|---|---|---|
| **Market** | segment, TAM/SAM, growth, why-now, tailwinds/headwinds | news, analyst pages, Wikipedia | SERP API |
| **Team / Founders** | **university, prior companies, prior exits/scaling**, repeat-founder, domain fit, co-founder completeness | **LinkedIn people profiles**, team/about page, Crunchbase person | **Web Scraper API (LinkedIn people)** + Scraping Browser |
| **Product** | what it does, capabilities, maturity | company site, Product Hunt, app store listing | Scraping Browser, SERP |
| **Traction** | users, ARR/revenue, growth RATE, retention proxy, adoption | App Store/Play (consumer), G2/Capterra (B2B), GitHub (dev tools), Product Hunt, HN | Web Scraper API / Scraping Browser |
| **Business model** | pricing, monetization, tiers | pricing page, app-store IAP, G2 pricing | Scraping Browser |
| **Competition** | named competitors, positioning, differentiation | G2 compare, "X vs Y" SERP, news | SERP, Scraping Browser |
| **Hiring / GTM motion** | role mix, first AE / VP Sales = sales-led inflection | ATS (Ashby/Greenhouse/Lever) | Scraping Browser |
| **Funding** | rounds, investors, total raised | news, Crunchbase | SERP (+ Web Unlocker for Crunchbase if blocked) |
| **Risks / Red flags** | Glassdoor sentiment, layoffs, leadership churn, litigation | Glassdoor, news, Reddit/HN | Scraping Browser, SERP |
| **Diligence questions** | gaps NOT publicly sourceable (retention, margins, CAC) | — generated from gaps | n/a |

**Adaptive routing by company type** (this is the originality beat — we pick the right
underrated source instead of scraping LinkedIn like everyone else):
- **dev tool / infra** → GitHub (stars/contributors/commit cadence)
- **consumer / prosumer app** → App Store + Play (rating trend, review velocity)
- **B2B SaaS** → G2/Capterra (review velocity, named customer logos) + ATS

---

## PART B — Architectural changes (the collector layer)

Refactor `vc_scout/sources/` from ad-hoc functions into a **collector registry**.

1. **`sources/base.py`** — define the contract:
   ```python
   @dataclass
   class Signal:
       section: str          # "market" | "team" | "product" | "traction" | ...
       fact: str             # the quoted/derived fact
       url: str
       source: str           # "SERP" | "LinkedIn(company)" | "ATS" | "GitHub" | ...
       trust: str            # "high" | "medium" | "low" (independent > self-reported)
       key: str = ""         # optional machine key, e.g. "employee_count"
       value: Any = None     # optional structured value
       date: str = ""

   @dataclass
   class EntityContext:      # resolved once up front, passed to every collector
       company: str
       domain: str = ""
       linkedin_company_url: str = ""
       linkedin_people_urls: list[str] = field(default_factory=list)
       careers_url: str = ""
       github_url: str = ""
       company_type: str = "unknown"   # "dev_tool" | "consumer_app" | "b2b_saas" | "unknown"
       serp_results: list[dict] = field(default_factory=list)

   class Collector(Protocol):
       name: str
       def applies_to(self, ctx: EntityContext) -> bool: ...
       def collect(self, ctx: EntityContext) -> list[Signal]: ...
   ```

2. **Resolver** (`sources/resolve.py`) — one initial SERP pass, then build `EntityContext`:
   domain, LinkedIn company URL, founder LinkedIn URLs, careers URL, GitHub URL, and a
   **company-type classifier** (cheap heuristic over SERP domains/keywords; LLM fallback).

3. **Collectors** (each implements the protocol, each degrades to `[]`):
   - `serp.py` — market/funding/news facts (universal). EXISTS — adapt to emit `Signal`s.
   - `company_site.py` — wraps Scraping Browser for site + pricing/about (universal). From existing `scraping_browser.py`.
   - `linkedin_company.py` — company signals (universal). EXISTS as `linkedin.py` — keep caveat: NOT ground truth.
   - `linkedin_people.py` — **NEW, high priority**: founder profiles → university, prior companies, prior exits, tenure. Web Scraper API people collector (`BRIGHTDATA_DATASET_PEOPLE`).
   - `ats.py` — hiring signals (universal). EXISTS.
   - `github.py` — **NEW, adaptive (dev_tool)**: stars, contributors, commit cadence, open issues.
   - `appstore.py` — **NEW, adaptive (consumer_app)**: rating, review count/velocity, ranking.
   - `reviews.py` — **NEW, adaptive (b2b_saas)**: G2/Capterra review velocity + named logos.
   - `glassdoor.py` — **OPTIONAL**: sentiment / leadership-churn red flags.

4. **Parallel orchestration** (`orchestrator.py`) — resolve context, then run all applicable
   collectors **concurrently** with `concurrent.futures.ThreadPoolExecutor`, a per-collector
   timeout, and a global wall-clock budget. Collect all `Signal`s. This keeps latency bounded
   even with many sources. (Heavy async scrapers like LinkedIn people stay OFF the live path —
   gate them behind a `DEEP=true` flag and bake their results into cache.)

5. **Memo assembler** (`bundle.py`) — group `Signal`s by `section` into the memo-structured
   bundle, preserving url+source+trust per signal. Build a `research_log` automatically from
   which collectors ran and what each returned.

---

## PART C — Output model: `InvestmentMemo` (mirror the real memo, in the real order)

In `models.py`, the brief becomes memo-structured. Order reflects how VCs decide
(Market → Team → Product → Traction → ...). Every field obeys anti-hallucination (omit/empty
when no evidence).

```python
class EvidencePoint(BaseModel):
    fact: str; url: str; source: str; trust: str   # trust: high|medium|low

class Founder(BaseModel):                  # EXPAND for pedigree
    name: str; role: str
    university: Optional[str] = None       # NEW
    prior_companies: List[str] = []        # NEW
    prior_exits_or_scaling: Optional[str] = None   # NEW: "co-founded X (acq. 2021)"
    domain_fit: Optional[str] = None       # NEW: why their background fits this problem
    linkedin_url: Optional[str] = None
    evidence: List[EvidencePoint] = []     # NEW: where each pedigree fact came from

class MemoSection(BaseModel):              # generic section wrapper
    summary: str                           # analyst prose for the section
    key_points: List[str] = []
    evidence: List[EvidencePoint] = []
    confidence: str                        # High|Medium|Low (based on source coverage)

class ScoreDriver(BaseModel):
    name: str; score: int; confidence: str
    rationale: str                         # quotes the specific fact
    supporting_evidence: List[EvidencePoint] = []

class InvestmentMemo(BaseModel):
    company_name: str
    one_liner: str
    executive_summary: str                 # 3-5 sentences: opportunity, why interesting, the read
    recommendation: Recommendation         # take_call | dig_deeper | pass
    conviction: str                        # High|Medium|Low in the verdict itself
    recommendation_rationale: str          # walk drivers + decisive evidence → verdict

    market: MemoSection
    team: List[Founder]                    # pedigree-rich
    team_assessment: MemoSection           # completeness, gaps, key hires
    product: MemoSection
    traction: MemoSection
    business_model: MemoSection
    competition: MemoSection
    funding: List[FundingRound] = []
    hiring_gtm: MemoSection                 # ATS-derived role mix + GTM motion

    decision_drivers: List[ScoreDriver]     # exactly 4: Asymmetry|Defensibility|Timing|Founder grit
    contradictions: List[Contradiction] = []
    risks_red_flags: List[RedFlag] = []
    failure_paths: List[str] = []
    diligence_questions: List[str] = []     # 3-5 sharp questions for gaps not publicly sourceable
    hidden_insight: str

    research_log: List[ResearchStep] = []   # per-source: examined / found / inference
    data_completeness: DataCompleteness     # which sources returned data
    sources: List[str] = []
```
Keep `_coerce_null_lists` working for all new list fields.

---

## PART D — Synthesis prompt (`orchestrator.py` SYSTEM_PROMPT)

Keep EVERY existing guardrail (ENTITY GROUNDING, ANTI-HALLUCINATION, falsifiable THESIS +
banned words, analyst ONE_LINER, FOUNDERS no-filler, fact-quoting driver rationales,
company-specific failure paths, HIDDEN INSIGHT inference-only, CONSISTENCY, LinkedIn = NOT
ground truth). Add:
- Reason over a **memo-structured bundle** (signals grouped by section, each with url/source/trust).
- Fill each `MemoSection.summary` from that section's signals; set `confidence` from how many
  INDEPENDENT (high-trust) sources corroborate.
- **Team/Founders**: extract university, prior companies, prior exits/scaling, domain fit — each
  with an EvidencePoint. If a pedigree fact isn't in evidence, leave it null. Never guess a
  university or a prior employer.
- **Traction**: distinguish self-reported (low trust) from independent (high trust). State which.
- **diligence_questions**: target the gaps — retention, margins, CAC, real revenue base — that
  public data can't confirm.
- **executive_summary** and **recommendation_rationale**: show HOW the verdict was reached from
  the section confidences and the four drivers, not just the conclusion.

---

## PART E — UI (`app.py`): memo-structured, verdict-first
Header (verdict badge + conviction + one_liner) → executive_summary → data_completeness strip →
decision_drivers (with evidence) → contradictions/failure_paths → diligence_questions →
research_log ("How we got here") → then memo sections (Market, Team w/ pedigree, Product,
Traction, Business model, Competition, Hiring/GTM, Funding) in collapsible detail → sources.

---

## PART F — Config, cache, scripts
- `.env.example`: add `BRIGHTDATA_DATASET_PEOPLE` (LinkedIn people collector), `DEEP` flag.
- `scripts/bake_cache.py "<company>"` — run full (DEEP) pipeline live, write
  `vc_scout/demo_cache/<slug>.json` (UTF-8, ensure_ascii=False).
- Regenerate `wispr-flow.json` + `godhands.json` in the `InvestmentMemo` schema with real data.

---

## BUILD ORDER (do in sequence; STOP and ship when time runs low — each step leaves a working app)
1. **Refactor to collector layer** (base.py, resolve.py, EntityContext) — wrap EXISTING sources
   (serp, company_site, linkedin_company, ats) as collectors. Parallel orchestration. App still works.
2. **`InvestmentMemo` model + memo assembler + memo prompt + UI** — the report becomes
   memo-structured and comprehensive. This is the biggest visible win — prioritize it.
3. **`linkedin_people.py`** — founder pedigree (university, priors, exits). Highest-signal new source.
4. **One adaptive collector** that fits a demo company: `appstore.py` (Wispr) OR `github.py`.
5. **Bake caches** for Wispr + GodHands; verify.
6. Glassdoor / reviews / extra adaptive collectors — ONLY if time remains. Otherwise leave as
   registered stubs and present them as the adaptive-source roadmap.

## VERIFY before done
`py_compile` all changed files · `pytest -q` green · all caches `InvestmentMemo.model_validate_json`
OK · run "GodHands" and "Wispr Flow" and confirm memo is grounded, pedigree populated, research_log
shows multi-source work · launch app, eyeball both, no overflow/placeholder. Commit.

After each BUILD ORDER step, summarize what changed + what you verified, and confirm the app still runs.
```
