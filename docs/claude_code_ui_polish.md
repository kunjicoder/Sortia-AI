# VC Scout — UI polish (Claude Code prompt)

Paste into Claude Code at repo root. Goal: confirm the current styling is intact, then make a
focused set of tasteful UI upgrades. **All changes live in `vc_scout/app.py` only** — do NOT touch
the pipeline, models, collectors, or prompt. The render logic stays; we improve presentation.

## Ground rules
- Only edit `app.py`. Keep all existing rendering behavior and field handling.
- Every visual must degrade gracefully — if a field is missing, render nothing, never error.
- Keep the palette: navy `#1E2761`, navy-2 `#2A3A7A`, ice `#CADCFC`, ink `#1A1F36`,
  green `#1F9D6B` (go), amber `#C8841C` (caution), red `#C0392B` (pass).
- `py_compile` after every change. Launch the app and eyeball before declaring done.

---

## PART 1 — Confirm the existing polish is in place
The app should already have: a `_THEME` (Soft, Inter font), a `_CSS` block, and `build_ui()` using
`gr.Blocks(theme=_THEME, css=_CSS)` with: a gradient navy `#vcs-header`, a `#vcs-controls` input
row, a navy `#vcs-btn`, and `#vcs-output` markdown card with styled headings, blockquotes, and a
wrapping research-log table. **Verify all of this exists; if anything is missing, restore it.**

---

## PART 2 — Further UI upgrades (do these, in order, all in `app.py`)

1. **Driver score bars.** In `_render_markdown`, render each decision driver's score as a small
   inline HTML bar (0–10) instead of plain text. A filled segment colored by score band:
   1-3 red `#C0392B`, 4-6 amber `#C8841C`, 7-8 navy `#1E2761`, 9-10 green `#1F9D6B`.
   Keep the existing `Name — N/10 · label · confidence` line above the bar. Example HTML:
   `<div style="background:#EDF0F8;border-radius:6px;height:8px;width:180px;display:inline-block">
   <div style="background:{color};width:{score*10}%;height:8px;border-radius:6px"></div></div>`

2. **Trust + confidence as pills, not emoji.** Replace the `_TRUST_ICON` emoji with small colored
   text pills: high → green, medium → amber/navy, low → grey. Add a `_pill(text, color)` helper
   returning an inline-styled `<span>`. Use it for evidence trust and for `MemoSection.confidence`.

3. **Source chips row.** Render `data_completeness` as a row of pill chips — present sources in
   solid navy, absent sources in faint grey (not strikethrough). Label them: SERP · Site ·
   LinkedIn · ATS · App Store · GitHub · Founders. Keep the `notes` line below.

4. **Verdict header upgrade.** Keep the colored verdict badge + conviction chip, but place them in
   a light rounded header card with the company name and one_liner, so the top of the memo reads
   like a title block. Verdict badge background = the recommendation color.

5. **Diligence questions as cards.** Render each question in a soft bordered card (left accent in
   navy) instead of a numbered list — they're the highest-value section, make them stand out.

6. **Loading state.** Replace the plain `*Searching…*` yields with a centered styled HTML block
   (navy text + a simple CSS spinner) so the wait looks intentional. Keep the same 3 steps.

7. **Empty / error states.** Style the "Please enter a company name" and error outputs as a soft
   card (amber/grey), not bare text.

8. **Micro-polish.** Smooth section dividers (`hr`), comfortable line-height (~1.6) in `#vcs-output`,
   and ensure links use the navy underline style already defined.

Keep it restrained — this is a memo, not a dashboard. No charts, no animations beyond the spinner,
no library additions.

---

## PART 3 — Verify
1. `python -m py_compile vc_scout/app.py`.
2. `USE_DEMO_CACHE=true python -m vc_scout.app`, open it, and check BOTH:
   - **Wispr Flow** (dig_deeper) — driver bars render, source chips show SERP/Site/LinkedIn/ATS on,
     research-log table wraps cleanly (no truncated/junk rows), diligence cards look good.
   - **GodHands** (pass) — verdict badge is red, empty sections render nothing (no broken markup).
3. Confirm nothing overflows the `#vcs-output` card and the page is centered.
4. Commit: "feat(ui): score bars, trust pills, source chips, diligence cards, loading state".

If a change looks off or risky, revert just that item — a clean simple memo beats a busy one.
Stop after Part 2; do not expand scope into new components or a redesign.
```
