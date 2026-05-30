# VC Scout — Demo Video Screenplay

**Target length:** 2:30 (hard cap 3:00). **Format:** screen recording + voiceover.
**Tools:** screen recorder (OBS / Loom / QuickTime) + the Gradio app. Record narration separately
and lay it over, or talk live — VO over clean screen capture reads more polished.

**Pre-flight (do before hitting record):**
- Set `USE_DEMO_CACHE=true` so GodHands + Wispr return instantly and identically every take.
- App open, browser zoomed to ~110%, no bookmarks bar, clean desktop.
- Have the architecture slide (deck slide 7) and adaptive-routing slide (slide 8) in a tab to cut to.
- Re-bake the Wispr cache with the guarded prompt first so the thesis/overview has no banned words.

**Three demo beats:** (1) GodHands = honest refusal · (2) Wispr = live data + skeptical verdict ·
(3) Architecture = why it's defensible. Keep the cursor deliberate; let results land before talking over them.

---

## SHOT LIST

| # | Time | On screen | Voiceover | On-screen caption |
|---|------|-----------|-----------|-------------------|
| 1 | 0:00–0:10 | Title card → cut to the app's empty input box | "A VC associate gets two hundred cold inbound decks a month, and five minutes per company. VC Scout gives those five minutes back — for every one." | **VC Scout — investment memos in 90 seconds** |
| 2 | 0:10–0:22 | Cursor hovers the input | "It turns a company name into a grounded, source-cited deal memo. The catch: it only reports what the live web actually supports." | *Grounded, not generative* |
| 3 | 0:22–0:30 | Type **GodHands**, hit run | "First, a near-stealth company most tools would happily hallucinate about." | — |
| 4 | 0:30–0:48 | Memo renders: PASS badge, "no public footprint" red flag, empty founders/funding | "VC Scout returns *pass*. No founders, no funding, no traction — and critically, it invents none. Empty evidence in, empty memo out. That's the honesty most AI tools skip." | **PASS · no public footprint — nothing fabricated** |
| 5 | 0:48–0:58 | Clear input, type **Wispr Flow**, run | "Now a real company — an AI voice-dictation startup." | — |
| 6 | 0:58–1:18 | Memo renders. Scroll to executive summary + traction section. Highlight Nvidia/Amazon + $260M lines | "Here it surfaces software used by Nvidia and Amazon, a reported $260 million round, and the Yapify acquisition — all *after* every model's training cutoff. This came off the live web through Bright Data, not the model's memory." | **Live web · post-cutoff facts · every claim cited** |
| 7 | 1:18–1:38 | Scroll to verdict + hiring/GTM section. Highlight **dig_deeper** and "Founding Account Executive" | "And the verdict is *dig deeper*, not a yes. The $260M is unverified, so it won't rubber-stamp it. But it flags a real signal a summarizer would miss: their first 'Founding Account Executive' hire — a product-led company turning sales-led." | **dig_deeper — skeptical by design** |
| 8 | 1:38–1:52 | Scroll to diligence questions + research log | "It even writes the questions to ask the founder — base ARR, real user counts — and shows its work: every source it checked, what it found, what it inferred." | **It shows its work** |
| 9 | 1:52–2:12 | Cut to architecture slide (4 source boxes) | "Under the hood: four Bright Data sources in parallel — Google results, the company's own site, LinkedIn, and its live hiring board — synthesized into one memo. No agent framework." | **SERP · Scraping Browser · LinkedIn · ATS** |
| 10 | 2:12–2:24 | Cut to adaptive-routing slide | "And it routes to the source that fits — GitHub for dev tools, App Store for consumer apps. It reaches what ChatGPT and Perplexity are locked out of." | **Adaptive web intelligence** |
| 11 | 2:24–2:35 | Back to a finished Wispr memo, slow zoom out | "Thirty minutes of manual triage, in ninety seconds — for every company that hits the inbox. That's VC Scout." | **VC Scout · built on Bright Data** |

---

## VOICEOVER SCRIPT (clean, for a separate read — ~330 words, ≈2:20 at a calm pace)

> A VC associate gets two hundred cold inbound decks a month, and five minutes per company. VC Scout gives those five minutes back — for every one.
>
> It turns a company name into a grounded, source-cited deal memo. The catch: it only reports what the live web actually supports.
>
> First, a near-stealth company most tools would happily hallucinate about — "GodHands." VC Scout returns *pass*. No founders, no funding, no traction — and it invents none. Empty evidence in, empty memo out. That's the honesty most AI tools skip.
>
> Now a real company — Wispr Flow, an AI voice-dictation startup. Here it surfaces software used by Nvidia and Amazon, a reported two-hundred-and-sixty-million-dollar round, and the Yapify acquisition — all *after* every model's training cutoff. This came off the live web through Bright Data, not the model's memory.
>
> And the verdict is *dig deeper*, not a yes. The raise is unverified, so it won't rubber-stamp it. But it flags a signal a summarizer would miss: their first "Founding Account Executive" hire — a product-led company turning sales-led.
>
> It even writes the questions to ask the founder, and shows its work — every source it checked, what it found, what it inferred.
>
> Under the hood: four Bright Data sources in parallel — Google results, the company's own site, LinkedIn, and its live hiring board — synthesized into one memo. No agent framework. And it routes to the source that fits — GitHub for dev tools, App Store for consumer apps. It reaches what ChatGPT and Perplexity are locked out of.
>
> Thirty minutes of manual triage, in ninety seconds — for every company that hits the inbox. That's VC Scout.

---

## EDITING NOTES
- Keep each memo on screen ~2s before narrating over it — let the verdict badge register.
- Use a subtle highlight/zoom on: PASS badge, Nvidia/Amazon line, dig_deeper badge, Founding AE line.
- Cut the dead air during any live load (or stay on cache so there is none).
- End card = deck closing slide. Add the repo/Spaces URL in the lower third.
- Music: low, neutral, drop it under the VO. No stingers on the serious lines.
```
