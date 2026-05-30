# VC Scout — Master Build Prompt (paste into Claude Code at repo root)

You are my senior engineer on **VC Scout**, a GTM-intelligence tool for the Bright Data
hackathon. Input a company name → output an investor-grade diligence brief in one pass,
grounded in live web data via Bright Data, synthesized by an LLM.

## Non-negotiable ground rules
- **No agent frameworks.** Direct SDK calls only (we use the `openai` SDK against AI/ML API).
- **Ship beats perfect.** Every change must keep the app runnable. Never break the SERP-only path.
- **Every source degrades gracefully.** Any source that fails returns empty and the pipeline
  continues. One slow/blocked source must never crash a brief.
- **Anti-hallucination is sacred.** Never invent a number, name, customer, or acquisition that
  isn't in the evidence. Missing data is a signal — say "not found," don't fabricate.
- **Commit in small steps** with clear messages. Run `python -m py_compile` on every file you
  touch and the test suite before declaring done.
- Read a file before editing it. Keep diffs minimal and focused.

---

## PART 1 — Confirm the multi-source architecture is wired

The pipeline in `vc_scout/orchestrator.py::build_brief` must call, in order, each degrading to
empty on failure:

1. **Bright Data SERP API** (`sources/serp.py`) — independent web facts. WORKING. Don't change.
2. **Bright Data Scraping Browser** (`sources/scraping_browser.py`) — founder claims from the
   company's own site. Uses Playwright `connect_over_cdp`, `wait_until="domcontentloaded"`
   (NOT networkidle), settle delay. WORKING.
3. **LinkedIn via Web Scraper API** (`sources/linkedin.py`) — `fetch_company_signals(url)`,
   async trigger→poll. Independent signal, **NOT ground truth** (employee_count = members who
   list the company; over/under-counts; lags). Dataset id from `BRIGHTDATA_DATASET_COMPANY`.
4. **ATS / careers** (`sources/ats.py`) — `fetch_hiring_signals(url)`, renders the Ashby/
   Greenhouse/Lever board via Scraping Browser, derives `open_roles`, `functions` (counts by
   team), `gtm_motion` (sales/AE/revenue roles = product-led→sales-led inflection).

`bundle.assemble(...)` takes `linkedin_signals` and `ats_signals` and emits bundle sections
`linkedin_signals` and `hiring_signals`. Helpers `find_linkedin_company_url` and
`find_careers_url` pick the URLs from SERP results. **Verify all of this exists and is wired.
Fix anything missing. Do not regress the reliability caveat on LinkedIn.**

---

## PART 2 — Rebuild the report to be COMPREHENSIVE (the main task)

The current `Brief` is too thin — it states conclusions without showing the research or the
reasoning. Expand `vc_scout/models.py` so the brief reads like an analyst memo that shows its
work. Every new field obeys anti-hallucination: **omit or empty when there is no evidence.**

### New / expanded Pydantic models

```python
class EvidencePoint(BaseModel):
    fact: str                      # the specific quoted fact
    url: str
    source_type: str               # "serp" | "site" | "linkedin" | "ats"

class ScoreDriver(BaseModel):      # EXPAND existing
    name: str                      # Asymmetry | Defensibility | Timing | Founder grit
    score: int                     # 1-10
    confidence: str                # High | Medium | Low
    rationale: str                 # 1-2 sentences, MUST quote the specific fact behind the score
    supporting_evidence: List[EvidencePoint] = []   # NEW: the trail behind the score

class Market(BaseModel):           # NEW
    segment: str
    sizing_note: Optional[str] = None      # TAM/SAM only if evidence supports it; else null
    tailwinds: List[str] = []
    headwinds: List[str] = []
    competitors: List[str] = []            # named only if they appear in evidence

class ResearchStep(BaseModel):     # NEW — shows the multi-source research explicitly
    source: str                    # "SERP API" | "Scraping Browser" | "LinkedIn" | "ATS"
    examined: str                  # what we looked at
    found: str                     # what came back, or "No data returned"
    inference: str                 # what it tells an investor (or "Inconclusive")

class DataCompleteness(BaseModel): # NEW — honest coverage map
    serp: bool
    company_site: bool
    linkedin: bool
    ats: bool
    notes: str = ""

class Brief(BaseModel):            # EXPAND
    company_name: str
    one_liner: str                 # 10-15 word analyst description
    overview: str                  # NEW: 2-4 sentence analyst summary (what / who for / stage)
    thesis: str                    # falsifiable, banned-words list enforced
    recommendation: Recommendation # take_call | dig_deeper | pass
    conviction: str                # NEW: High | Medium | Low — confidence in the verdict itself
    recommendation_rationale: str  # EXPAND: must reference the driver scores + the key evidence
                                   #         that moved the verdict (show how it was reached)
    founders: List[Founder] = []
    market: Market                 # NEW
    traction: TractionSignals
    hiring: HiringSignals          # populate from ATS hiring_signals when present
    funding_history: List[FundingRound] = []
    recent_press: List[PressItem] = []
    competitive_positioning: CompetitivePositioning
    decision_drivers: List[ScoreDriver]      # exactly 4
    contradictions: List[Contradiction] = []
    failure_paths: List[str] = []            # each names THIS company's specific weakness
    diligence_questions: List[str] = []      # NEW: 3-5 sharp questions for the founder,
                                             #      derived from gaps/risks/contradictions
    hidden_insight: str
    research_log: List[ResearchStep] = []    # NEW: one step per source actually used
    data_completeness: DataCompleteness      # NEW
    red_flags: List[RedFlag] = []
    sources: List[str] = []
```

Keep `_coerce_null_lists` working for all new List fields.

---

## PART 3 — Update the synthesis prompt (`orchestrator.py` SYSTEM_PROMPT)

Keep ALL existing guardrails (do not remove any):
- ENTITY GROUNDING (ambiguous name → pass + `ambiguous_entity` red flag, no fabricated thesis)
- ANTI-HALLUCINATION (named entities must appear verbatim in evidence)
- THESIS falsifiable + banned words (redefining, innovative, revolutionary, transforming,
  leading, cutting-edge, next-generation, seamless, empowering)
- ONE_LINER analyst description, no slogans
- FOUNDERS no filler padding
- Driver rationales must quote a specific fact
- Failure paths company-specific, not generic
- HIDDEN INSIGHT = inference only, no new named entity
- CONSISTENCY: prose claims must match structured fields (a round in prose ⇒ funding_history entry)
- LinkedIn = corroborating signal, NOT ground truth; large divergence → DIG_DEEPER flag, never a
  hard contradiction on LinkedIn alone

Add instructions to populate the new fields with evidence discipline:
- **overview**: 2-4 sentences synthesizing what the company does, who it's for, and its apparent
  stage — from web_evidence, not marketing copy.
- **decision_drivers[].supporting_evidence**: 1-3 EvidencePoints per driver, each a real fact +
  url + source_type from the bundle. If a driver has no evidence, confidence=Low and
  supporting_evidence=[].
- **market**: segment always; sizing_note only if a size figure appears in evidence (else null);
  tailwinds/headwinds as short phrases grounded in evidence; competitors named only if they
  appear in a snippet.
- **research_log**: ONE entry per source that actually contributed (SERP always; Scraping
  Browser, LinkedIn, ATS only if they returned data). Each states what was examined, what was
  found (or "No data returned"), and the investor-relevant inference. This is how the brief
  SHOWS ITS WORK — be concrete, cite what each source contributed.
- **data_completeness**: set serp/company_site/linkedin/ats booleans to reflect which bundle
  sections are present; notes explains any gaps and how they limit confidence.
- **diligence_questions**: 3-5 questions a sharp investor would ask THIS founder next, each
  targeting a specific gap, risk, or unverified claim in the evidence.
- **conviction**: High only when multiple independent sources corroborate; Low when the brief
  leans on a single source or self-reported claims. State the basis in recommendation_rationale.
- **recommendation_rationale**: explicitly walk from the four driver scores and the decisive
  evidence to the verdict — the reader should see HOW the conclusion was reached, not just the
  conclusion.

---

## PART 4 — Update the UI (`vc_scout/app.py`) to render the richer report

Keep it scannable: **verdict-first, depth-on-demand.** Layout top to bottom:
1. **Header band**: verdict badge (take_call green / dig_deeper amber / pass red) + conviction +
   one_liner + thesis.
2. **Overview** paragraph + a small **data_completeness** strip (which sources returned data —
   shows the multi-source research at a glance).
3. **Decision drivers**: each as "Name — N/10 · confidence", the rationale, and its
   supporting_evidence as small cited bullets (fact → source).
4. **Contradictions** (or "claims check out" empty state) and **failure paths**.
5. **Diligence questions** as a clean numbered list — this is high-value, make it visible.
6. **Research log** rendered as a "How we got here" table/section (source · found · inference) —
   this is the showcase of research depth; render it prominently, not buried.
7. **Market**, **founders**, **traction/hiring**, **funding**, **press** in a collapsible
   "Full detail" `<details>` block.
8. **Sources** list at the bottom.

Keep the existing latency/stats line ("N sources read · brief generated in Xs").

---

## PART 5 — Cache + bake script

- Add `scripts/bake_cache.py`: runs `build_brief` live for a company name and writes the result
  to `vc_scout/demo_cache/<slug>.json` (UTF-8, `ensure_ascii=False`). One command turns a real
  run into demo-safe cache. CLI: `python scripts/bake_cache.py "Wispr Flow"`.
- Regenerate `wispr-flow.json` and `godhands.json` in the NEW expanded schema. For Wispr, run
  live so research_log, market, diligence_questions, and (if configured) linkedin/ats signals
  are real. Verify the `×` and all unicode are clean UTF-8.

---

## PART 6 — Verification (do all before declaring done)
1. `python -m py_compile` every changed file.
2. `python -m pytest -q` — all green; update tests for the new schema where needed.
3. `python -c "from vc_scout.models import Brief; import pathlib; [Brief.model_validate_json(p.read_text(encoding='utf-8')) for p in pathlib.Path('vc_scout/demo_cache').glob('*.json')]"` — all caches valid.
4. Run `python -m vc_scout.orchestrator "GodHands"` and `"Wispr Flow"` — confirm the briefs are
   comprehensive, grounded, and the research_log shows the multi-source work.
5. Launch the Gradio app, eyeball both companies — verdict-first, research log visible,
   diligence questions present, no overflow/placeholder text.
6. Commit with a clear message.

Work through Parts 1→6 in order. After each Part, summarize what changed and what you verified.
```
