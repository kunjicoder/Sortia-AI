# VC Scout

> Cold inbound at 9:00 AM. Investor-ready brief by 9:01 AM.

**[DRAFT — Karthik to edit before submission]**

VC Scout is an AI scouting agent that turns a company name into a structured investor brief in under 90 seconds. It replaces 30–60 minutes of manual research (LinkedIn, Crunchbase, GitHub, HN, news) with automated, multi-source web intelligence synthesized by an LLM.

Built for the **Bright Data Web Data UNLOCKED Hackathon 2026** · GTM Intelligence track.

---

## The Problem

Early-stage VC associates see 200+ inbound companies per month. Triaging each one manually — founder backgrounds, traction signals, recent press, funding history — takes 30–60 minutes per company. That's hours burned on triage instead of investment thesis work.

VC Scout compresses that to under two minutes.

---

## Architecture

```
Company name (input)
        │
        ▼
┌─────────────────────┐
│  Orchestrator       │  orchestrator.py
│  (build_brief)      │
└─────────────────────┘
        │
        ├──► Bright Data SERP API ──► recent news, press, HN mentions,
        │    sources/serp.py           funding signals, hiring signals
        │
        ▼
┌─────────────────────┐
│  AI/ML API          │  llm.py
│  (gpt-4o-mini)      │  OpenAI-compatible SDK
└─────────────────────┘
        │
        ▼
  Structured Brief     models.py (Pydantic)
  rendered in Gradio   app.py
```

### Bright Data integration

**Product used: SERP API**

`sources/serp.py` calls the Bright Data SERP API to run a targeted Google search for each company:

```
"{company}" (news OR raised OR launched OR hiring)
```

The request uses `brd_json=1` so Bright Data returns parsed JSON (organic results, news snippets) instead of raw HTML. The response is normalised into a flat list of `{title, url, description, source}` dicts and passed verbatim to the LLM as evidence.

This is what lets VC Scout surface **post-training-cutoff data** — see the demo story below.

### LLM synthesis — AI/ML API

`llm.py` calls the AI/ML API (partner prize, OpenAI-compatible endpoint) with a structured prompt asking the model to produce a JSON object matching the `Brief` Pydantic schema. The schema covers: founders, traction signals, hiring, funding history, recent press, competitive positioning, red flags, and a recommendation (`take_call` / `dig_deeper` / `pass`).

The system prompt instructs the model to:
- Populate `sources[]` with every URL it used from the evidence
- Tie major claims to a source URL
- Only raise a `red_flags` entry when there is concrete evidence (prevents speculative `founder_turnover` on companies that simply have a thin public footprint)

---

## Demo Story

**The signal that proves live web data, not model memory:**

Wispr Flow raised a **$30M Series A from Menlo Ventures** in June 2025. That is after every major model's training cutoff. When you run VC Scout on "Wispr Flow", it correctly surfaces that round — because the data came from the live web via Bright Data, not from the model's weights.

Compare: searching for "GodHands" (a fictional company) returns an empty SERP and the brief reflects that honestly, with a `missing_footprint` red flag instead of fabricated data.

---

## Setup

### Prerequisites

- Python 3.11+
- A [Bright Data](https://brightdata.com) account with the SERP API zone enabled
- An [AI/ML API](https://aimlapi.com) key (or a Grok/xAI key)

### Install

```bash
git clone <repo-url>
cd vc-scout
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure `.env`

Copy `.env.example` to `.env` and fill in:

```env
# LLM — choose one provider
LLM_PROVIDER=aiml          # or "grok"
AIML_API_KEY=...
AIML_MODEL=gpt-4o-mini

# Bright Data
BRIGHTDATA_API_KEY=...
BRIGHTDATA_SERP_ZONE=...   # zone name from the Bright Data dashboard

# Demo safety net — returns cached briefs instantly for known companies
USE_DEMO_CACHE=false
```

### Run

**Gradio web UI (recommended for demos):**

```bash
python -m vc_scout.app
# → opens http://127.0.0.1:7860
```

**CLI (raw JSON output):**

```bash
python -m vc_scout.orchestrator "Wispr Flow"
```

**With demo cache (no network calls):**

```bash
USE_DEMO_CACHE=true python -m vc_scout.orchestrator "Wispr Flow"
```

### Tests

```bash
pytest -q
```

---

## Project Structure

```
vc_scout/
  app.py           Gradio UI
  orchestrator.py  Main agent loop (build_brief)
  llm.py           LLM client (AI/ML API / Grok, OpenAI SDK)
  models.py        Pydantic schemas (Brief, Founder, TractionSignals, …)
  config.py        Settings loaded from .env
  demo_cache/      Pre-generated briefs for offline/demo mode
  sources/
    serp.py        Bright Data SERP API wrapper
    linkedin.py    (stub — cut from v1 demo path)
    unlocker.py    (stub — planned v2)
tests/
  test_smoke.py    Import and schema round-trip smoke tests
  test_serp.py     Unit tests for SERP response parser
```

---

## Hackathon Notes

- **Track:** GTM Intelligence
- **Builder:** Karthik Narayan Sudheer (solo)
- **Deadline:** May 30, 2026
- Bright Data products demonstrated: **SERP API** (live; Web Scraper and Web Unlocker stubs ready for v2)
- AI/ML API used as the primary LLM gateway (partner prize integration)

---

*Built without LangChain, CrewAI, or any agent framework — direct SDK calls only.*
