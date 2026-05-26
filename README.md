# VC Scout

> AI scouting agent that turns a company name into an investor-ready brief in 90 seconds, powered by Bright Data's multi-source web intelligence.

**Built for:** Bright Data Web Data UNLOCKED Hackathon 2026
**Track:** GTM Intelligence
**Status:** In development — May 26–30, 2026

---

## What it does

Type a company name. Get back a structured investor brief covering founder background, traction signals, hiring velocity, recent press, competitive positioning, red flags, and a recommended next step. Replaces 30–60 minutes of manual scouting with under two minutes of automated, multi-source web intelligence.

The full project spec lives in [`project.txt`](./project.txt).

---

## Architecture

```
User input (company name)
        │
        ▼
┌─────────────────────────────┐
│   Orchestration layer       │
│   (Python + LLM)            │
└─────────────────────────────┘
        │
        ├──► Bright Data SERP API ──────► news, press, HN mentions
        │
        ├──► Bright Data Web Scraper API ─► LinkedIn (founders, team, hiring)
        │
        ├──► Bright Data Web Unlocker ───► GitHub, X/Twitter, ProductHunt
        │
        ▼
┌─────────────────────────────┐
│   LLM synthesis (Grok)      │
└─────────────────────────────┘
        │
        ▼
Structured investor brief (Pydantic-validated)
```

---

## Bright Data products used

| Product | Used for |
|---------|----------|
| SERP API | Recent news, press releases, HN front-page mentions, founder name search |
| Web Scraper API | LinkedIn collectors — founder background, team size, hiring velocity |
| Web Unlocker | GitHub repos, X/Twitter, ProductHunt launches, dynamic pricing pages |

---

## Tech stack

- Python 3.11+
- `openai` SDK (used as the client for Grok via `base_url` override)
- Pydantic v2 for structured output validation
- Gradio for the demo UI
- Bright Data REST APIs via `requests`

---

## Setup

```bash
# Clone
git clone https://github.com/<your-handle>/vc-scout.git
cd vc-scout

# Virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# Install
pip install -r requirements.txt

# Configure
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Then fill in the API keys
```

---

## Usage

```bash
# Launch the Gradio demo
python -m vc_scout.app

# Or run the CLI orchestrator directly
python -m vc_scout.orchestrator "Anthropic"
```

---

## Project layout

```
vc_scout/
├── config.py          Environment loading
├── models.py          Pydantic schemas for the investor brief
├── llm.py             Grok client wrapper
├── orchestrator.py    Main agent loop
├── app.py             Gradio frontend
└── sources/
    ├── serp.py        Bright Data SERP API
    ├── linkedin.py    Bright Data Web Scraper API
    └── unlocker.py    Bright Data Web Unlocker

tests/
└── test_smoke.py      Import smoke test
```

---

## Roadmap

- [x] Repo scaffold
- [ ] Grok client wired up and tested
- [ ] Bright Data SERP integration
- [ ] Bright Data Web Unlocker integration (GitHub)
- [ ] Bright Data Web Scraper integration (LinkedIn)
- [ ] Pydantic brief synthesis
- [ ] Gradio UI
- [ ] Three locked demo targets with cached fallback responses
- [ ] Demo video (under 3 min)
- [ ] Slide deck
- [ ] Deployed to Hugging Face Spaces

---

## License

MIT — see [LICENSE](./LICENSE).
