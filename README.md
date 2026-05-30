```markdown
# VC Scout

VC Scout is an AI-powered research agent that converts a company name into a structured investor brief in under 90 seconds. It automates multi-source web intelligence — LinkedIn, Crunchbase, GitHub, Hacker News, press mentions — and synthesizes the findings using a large language model.

---

## Problem Statement

Early-stage venture capital associates typically review 200+ inbound companies per month. Manually researching each one — including founder backgrounds, traction signals, recent press, and funding history — requires 30–60 minutes per company. This manual triage process consumes hours that could otherwise be dedicated to investment thesis development.

VC Scout reduces this triage time to less than two minutes.

---

## Architecture

```text
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

### Bright Data Integration

**Product used: SERP API**

The `sources/serp.py` module calls the Bright Data SERP API to perform a targeted web search for each company using the query:

`"{company}" (news OR raised OR launched OR hiring)`

The request uses `brd_json=1` to return parsed JSON (organic results, news snippets) instead of raw HTML. The response is normalized into a flat list of `{title, url, description, source}` dictionaries and passed to the LLM as evidence. This enables VC Scout to retrieve live, post‑training‑cutoff data directly from the web.

### LLM Synthesis

The `llm.py` module calls an OpenAI‑compatible endpoint with a structured prompt, asking the model to produce a JSON object matching the `Brief` Pydantic schema. The schema includes: founders, traction signals, hiring activity, funding history, recent press, competitive positioning, red flags, and a recommendation (`take_call` / `dig_deeper` / `pass`).

The system prompt instructs the model to:

- Populate `sources[]` with every URL used from the evidence.
- Attribute major claims to a specific source URL.
- Raise a `red_flags` entry only when concrete evidence exists (avoiding speculative flags for companies with a limited public footprint).

---

## Setup

### Prerequisites

- Python 3.11+
- A [Bright Data](https://brightdata.com) account with the SERP API zone enabled
- An LLM API key (e.g., AI/ML API, Grok/xAI, or standard OpenAI)

### Installation

```bash
git clone <repo-url>
cd vc-scout
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Configuration

Copy `.env.example` to `.env` and populate with your credentials:

```env
# LLM — choose your provider
LLM_PROVIDER=aiml          # or "grok", "openai"
AIML_API_KEY=your_api_key_here
AIML_MODEL=gpt-4o-mini

# Bright Data
BRIGHTDATA_API_KEY=your_api_key_here
BRIGHTDATA_SERP_ZONE=your_zone_name   # zone name from Bright Data dashboard

# Demo/Testing Mode — returns cached briefs instantly for known companies to save API calls
USE_DEMO_CACHE=false
```

### Execution

**Gradio Web UI (Recommended):**

```bash
python -m vc_scout.app
# Opens http://127.0.0.1:7860
```

**CLI (Raw JSON output):**

```bash
python -m vc_scout.orchestrator "Company Name"
```

**With Cache (No network calls):**

```bash
USE_DEMO_CACHE=true python -m vc_scout.orchestrator "Company Name"
```

### Testing

```bash
pytest -q
```

---

## Project Structure

```text
vc_scout/
  app.py           Gradio UI
  orchestrator.py  Main agent loop (build_brief)
  llm.py           LLM client
  models.py        Pydantic schemas (Brief, Founder, TractionSignals, ...)
  config.py        Settings loaded from .env
  demo_cache/      Pre-generated briefs for offline/testing mode
  sources/
    serp.py        Bright Data SERP API wrapper
    linkedin.py    (stub)
    unlocker.py    (stub)
tests/
  test_smoke.py    Import and schema round-trip smoke tests
  test_serp.py     Unit tests for SERP response parser
```

---

## Notes

- Built with direct SDK calls for speed and simplicity — no heavy agent frameworks.
- For questions or contributions, please refer to the repository issues page.
```
