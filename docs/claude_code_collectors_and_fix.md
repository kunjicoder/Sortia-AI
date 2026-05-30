# VC Scout — Fix research_log + ship GitHub & App Store collectors (Claude Code prompt)

Paste into Claude Code at repo root. Two goals:
**(A)** Fix the broken/incomplete `research_log` (junk rows + truncated cells).
**(B)** Make the deck's "adaptive routing → GitHub / App Store" claim TRUE and VERIFIABLE.

## Ground rules
- No agent frameworks. Direct SDK + stdlib. App stays runnable after every step.
- Every collector degrades to `[]` on failure; never crash the pipeline.
- Anti-hallucination: never invent a number/name. Missing data → omit.
- Read before edit. `py_compile` + `pytest` before declaring done. Small commits.

---

## PART A — Fix `research_log` (do this first, it's a real bug)

**Symptom:** the "How We Got Here" table shows phantom rows ("Promo", "Don't type, just
speak", "The voic") — these are SERP sitelink/marketing fragments the LLM invented as sources —
and cells are truncated mid-word.

**Root cause:** the LLM is populating `research_log`. It must not.

1. In `orchestrator.py`, build `research_log` **deterministically** from the collectors that
   actually ran, using `build_collector_log` (already imported). One `ResearchStep` per collector
   that executed, with:
   - `source` = collector.name (SERP API / Scraping Browser / LinkedIn / ATS / GitHub / App Store)
   - `examined` = the URL or query it hit
   - `found` = a short factual summary ("19 roles", "rating 4.7, 2.1k reviews", "No data returned")
   - `inference` = one investor-relevant line (or "Inconclusive")
   Assign `memo.research_log = build_collector_log(ran_collectors, signals)` AFTER synthesis,
   overwriting whatever the LLM produced.
2. In `SYSTEM_PROMPT`, change the research_log instruction to: **"Do NOT populate research_log;
   it is filled programmatically. Leave it as []."** Remove any example that fills it.
3. In `models.py`, ensure `ResearchStep` fields are plain strings; add a validator that drops
   entries whose `source` is not one of the known collector names (defensive).
4. In `app.py`, the "How We Got Here" table must **wrap** text, not clip. Set column widths and
   allow multi-line cells; truncate each cell to a sane length (e.g. 160 chars) with an ellipsis
   in CODE, not by overflow. Verify no row is cut mid-word.
5. Re-bake the Wispr + GodHands caches so their `research_log` is clean.

---

## PART B — GitHub collector (`sources/github.py`)

Make the dev-tool routing real. Use the public GitHub REST API (no auth needed for low volume;
optional `GITHUB_TOKEN` raises rate limit). This is legitimate — it's a public API, and the
adaptive-routing story is "the right source per company type."

- `fetch_repo_signals(github_url_or_owner_repo: str) -> dict` returning only present fields:
  `stars`, `forks`, `open_issues`, `contributors` (count via `?per_page=1` Link header),
  `last_commit` (ISO date from `/commits`), `language`, `source_url`.
- Resolve owner/repo from a `github.com/<owner>/<repo>` URL found in SERP/context.
- Timeout 15s, degrade to `{}` on any error/non-200.
- `GitHubCollector` (protocol): `name="GitHub"`, `applies_to(ctx)= ctx.company_type=="dev_tool" and bool(ctx.github_url)`,
  `collect(ctx)` → Signals in section `"traction"`, trust `"high"`, e.g.
  "GitHub: 12.4k stars, 340 contributors, last commit 2026-05-28 (high-trust adoption proxy)."

Resolver (`resolve.py`): populate `ctx.github_url` from the first `github.com/<owner>/<repo>`
SERP result, and set `company_type="dev_tool"` when GitHub/infra keywords dominate.

---

## PART C — App Store collector (`sources/appstore.py`)

Make the consumer-app routing real. Two options — pick the simplest that returns data:
1. **iTunes Search API** (public, no key): `https://itunes.apple.com/search?term=<app>&entity=software&limit=1`
   → returns `trackName`, `averageUserRating`, `userRatingCount`, `price`, `sellerName`,
   `trackViewUrl`. Zero-friction, reliable. Use this as the default.
2. If you want it to be a *Bright Data* scrape for the hackathon narrative, render the App Store
   web page via the Scraping Browser and parse rating + review count. Heavier; only if (1) is
   insufficient. Document which one is active.

- `fetch_app_signals(company_or_app_name: str) -> dict`: `app_name`, `rating`, `rating_count`,
  `price`, `seller`, `source_url`. Degrade to `{}`.
- `AppStoreCollector`: `name="App Store"`,
  `applies_to(ctx)= ctx.company_type=="consumer_app"`,
  `collect(ctx)` → Signals in `"traction"`, trust `"high"`:
  "App Store: 4.7★ from 2,140 ratings (independent adoption proxy)."

Resolver: set `company_type="consumer_app"` when app-store / mobile / consumer keywords dominate.

---

## PART D — Registry + adaptive routing

- Register `GitHubCollector` and `AppStoreCollector` in `sources/registry.py::COLLECTORS`.
- The orchestrator already filters by `collector.applies_to(ctx)` — confirm GitHub fires only for
  `dev_tool` and App Store only for `consumer_app`, while SERP/Scraping Browser/LinkedIn/ATS stay
  universal. This makes the deck's adaptive-routing claim literally true.
- `.env.example`: add optional `GITHUB_TOKEN=` with a comment that it only raises rate limits.

---

## PART E — VERIFY (this is how we back the deck claim)

Add `scripts/verify_sources.py` that runs and prints a table of which collectors fired + sample data:
1. **Dev tool** (e.g. "Ollama" or "Cursor") → assert a GitHub signal exists with a real
   `github.com` URL and a star count > 0. Print the signal.
2. **Consumer app** (e.g. "Wispr Flow" or "Notion") → assert an App Store signal with a real
   `apps.apple.com`/`itunes` URL and a rating. Print it.
3. Print each run's `research_log` and confirm: only real collector names, no marketing
   fragments, no truncated/junk rows.

Also:
- `python -m py_compile` all changed files; `pytest -q` green.
- Re-validate all demo_cache JSON against `InvestmentMemo`.
- Manual: run the app on a dev tool and a consumer app, screenshot the GitHub row and the App
   Store row for the demo video — that screenshot IS the proof the claim is real.

Build order: A (fix) → B (GitHub) → C (App Store) → D (wire) → E (verify). After each, summarize
what changed + what you verified, and confirm the app still runs. If time runs short, A + one of
{B, C} fully working beats both half-built — and update the deck to claim only what actually runs.
```
