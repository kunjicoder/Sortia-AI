# VC Scout — Deck Outline

**DRAFT — Karthik rewrites copy in his own voice before the presentation.**

Facts are pre-filled from the actual codebase and demo runs. Slide order follows the
judging criteria: Application of Technology → Presentation → Business Value → Originality.

---

## Slide 1 — Title / Hook

**Headline:** Cold inbound at 9:00 AM. Investor-ready brief by 9:01 AM.

**Talking points:**
- You're a VC associate. 200+ inbound companies this month. You have 5 minutes per company before the partner meeting.
- VC Scout gives you back those 5 minutes — for every single company.
- One text box. One button. Done.

---

## Slide 2 — The Problem (Business Value setup)

**Headline:** Manual triage is killing deal velocity.

**Talking points:**
- 30–60 minutes per company to manually check LinkedIn, Crunchbase, GitHub, HN, news.
- Lean funds and solo angels can't afford an associate just for triage.
- Existing tools (Harmonic, Specter) are enterprise SaaS — overkill for a 5-company/day workflow.
- The cost of a missed pass: $10M+ opportunity. The cost of a wasted call: 60 minutes.

---

## Slide 3 — Live Demo Beat 1: GodHands

**Headline:** Unknown company? The model says so honestly.

**Talking points:**
- Type "GodHands" → brief returns in <1s (from cache, or ~15s live).
- Shows: `missing_footprint` red flag, no founders, no funding, no traction, recommendation: `pass`.
- Key point: the model did NOT make anything up. Empty evidence → empty brief.
- This is what honest AI looks like. No hallucination.

---

## Slide 4 — Live Demo Beat 2: Wispr Flow

**Headline:** Real company? Watch what the live web knows that the model doesn't.

**Talking points:**
- Type "Wispr Flow" → brief surfaces $30M Series A from Menlo Ventures, June 2025.
- That round is **after every major model's training cutoff**.
- The model couldn't have invented this. It came from the live web via Bright Data SERP API.
- Shows: `take_call` recommendation, funding history, TechCrunch press item, 5 source URLs.
- Stats footer: "5 sources read · brief generated in ~17s"
- This is the core demo proof: live data, not stale weights.

---

## Slide 5 — Application of Technology: Bright Data

**Headline:** Bright Data SERP API — the live web intelligence layer.

**Talking points:**
- Single API call to `api.brightdata.com/request` with `brd_json=1`.
- Bright Data proxies Google and returns parsed JSON (organic + news results) — no raw HTML scraping.
- Query pattern: `"{company}" (news OR raised OR launched OR hiring)` — tuned for VC signals.
- Returns up to 10 structured results: title, URL, description, source section.
- This is what makes post-cutoff data possible. No Bright Data = model only knows what it was trained on.
- Stubs in place for Web Scraper API (LinkedIn) and Web Unlocker (GitHub) — v2 scope.

---

## Slide 6 — Application of Technology: AI/ML API + Synthesis

**Headline:** AI/ML API turns raw evidence into a structured investor brief.

**Talking points:**
- Partner integration: AI/ML API at `api.aimlapi.com/v1` (OpenAI-compatible endpoint).
- Model: `gpt-4o-mini`, 4096 output tokens.
- System prompt enforces: populate `sources[]` from evidence URLs, tie facts to URLs, only raise red flags on concrete evidence.
- Output: Pydantic-validated `Brief` schema (founders, traction, funding, red flags, recommendation).
- `_coerce_null_lists()` defensively handles null list fields from the LLM.
- One retry with 3s backoff on transient errors; clean error messages surfaced in the UI.

---

## Slide 7 — Architecture (use the Mermaid diagram from docs/architecture.mermaid)

**Headline:** 4 files, 2 external APIs, one coherent pipeline.

**Talking points:**
- Walk the diagram: company name → SERP API → evidence assembly → AI/ML API → Pydantic Brief → Gradio UI.
- Highlight the demo cache branch: with `USE_DEMO_CACHE=true`, the whole pipeline short-circuits to a JSON file. Zero network dependency during the live demo.
- No LangChain. No CrewAI. No agent framework. Direct SDK calls — easier to debug, faster to ship.

---

## Slide 8 — Business Value

**Headline:** Every hour saved is a better investment decision.

**Talking points:**
- 30–60 min manual triage → <2 min automated triage. 15–30× faster.
- At 10 companies/day: saves 5–10 hours/week per associate.
- Flip side: catching one company you'd have missed due to time pressure = potentially $10M+ upside.
- Unit economics for the product itself: API cost per brief ≈ $0.01 (AI/ML API) + $0.01 (Bright Data SERP) = ~$0.02/brief. Viable at any price point above free.
- Target user: solo angels, emerging managers, lean seed funds — underserved by enterprise SaaS.

---

## Slide 9 — Originality

**Headline:** VC scouting is just GTM intelligence with a different job title.

**Talking points:**
- Most hackathon teams will build outbound sales tools. Same Bright Data products, saturated angle.
- VC scouting is structurally identical: research a target before reaching out, multi-source intel, LLM synthesis.
- Vertical specificity in AI/dev-tools = denser public signals (GitHub, HN, eng blogs) = higher brief quality.
- The GodHands/Wispr contrast story is inherently visual and memorable for a demo. Hard to fake.
- The $30M post-cutoff proof is a built-in technical credibility moment.

---

## Slide 10 — What's Next / Ask

**Headline:** V1 is live. V2 ships Web Scraper + Web Unlocker.

**Talking points:**
- V1 shipped: SERP API + AI/ML API synthesis + Gradio UI + demo cache + robustness hardening.
- V2 scope (stubs already in the repo): LinkedIn via Web Scraper API (founder depth), GitHub via Web Unlocker (technical traction).
- Deployment target: Hugging Face Spaces (free tier, shareable URL for judges).
- The ask (if doing a pitch framing): feedback on the VC use case fit, especially from anyone at an early-stage fund.

---

## Appendix — Raw facts to pull from

| Fact | Value |
|------|-------|
| Wispr Flow funding | $30M Series A, Menlo Ventures, June 2025 |
| Wispr Flow recommendation | `take_call` |
| GodHands recommendation | `dig_deeper` (live) / `pass` (earlier run) |
| GodHands red flag | `missing_footprint` |
| SERP results per query | 10 (configurable via `num_results`) |
| LLM max tokens | 4096 |
| Retry policy | 1 retry, 3s backoff on timeout/rate-limit |
| Cost per brief (estimate) | ~$0.02 |
| End-to-end latency (live) | ~15–20s (SERP ~5s + LLM ~10s) |
| End-to-end latency (cache) | <20ms |
| Test suite | 16 tests, 0 failures |
| Lines of code (vc_scout/) | ~450 |
