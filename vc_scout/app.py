"""Gradio frontend for the demo.

Single text input -> triangulation investor memo rendered as markdown.

Launch:
    python -m vc_scout.app
"""

from __future__ import annotations

import logging

import gradio as gr

from .models import Brief, Recommendation
from .orchestrator import ScoutInput, ScoutResult, build_brief

log = logging.getLogger(__name__)

_BADGE = {
    Recommendation.TAKE_CALL:  ("🟢", "#1a7a1a", "GO — TAKE THE CALL"),
    Recommendation.DIG_DEEPER: ("🟡", "#7a6200", "SECOND LOOK — DIG DEEPER"),
    Recommendation.PASS:       ("🔴", "#8b0000", "NO-GO — PASS"),
}

_SCORE_BAR = {
    range(1, 4):  ("🔴", "not-venture-scale"),
    range(4, 7):  ("🟡", "plausible 10×"),
    range(7, 9):  ("🟢", "real moat forming"),
    range(9, 11): ("💎", "category-defining"),
}

_SEVERITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}

_PROGRESS_STEPS = [
    "Searching the web…",
    "Reading sources…",
    "Synthesizing brief…",
]


def run(company: str, founder: str):
    company = (company or "").strip()
    if not company:
        yield "Please enter a company name."
        return
    founder = (founder or "").strip() or None

    for step in _PROGRESS_STEPS:
        yield f"*{step}*"

    try:
        result = build_brief(ScoutInput(company_name=company, founder_name=founder))
    except Exception as e:
        log.exception("build_brief failed")
        yield f"**Error:** {e}"
        return

    yield _render_markdown(result)


def _score_label(score: int) -> str:
    for r, (icon, label) in _SCORE_BAR.items():
        if score in r:
            return f"{icon} {score}/10 — {label}"
    return f"{score}/10"


def _render_markdown(result: ScoutResult) -> str:
    brief = result.brief
    emoji, color, label = _BADGE.get(
        brief.recommendation,
        ("⚪", "#555", brief.recommendation.value.upper()),
    )

    lines = [
        f"# {brief.company_name}",
        f"*{brief.one_liner}*" if brief.one_liner else "",
        "",
    ]

    # ── Verdict badge (most prominent) ──────────────────────────────────────
    lines += [
        f'<div style="display:inline-block;padding:8px 18px;border-radius:8px;'
        f'background:{color};color:#fff;font-weight:bold;font-size:1.15em;">'
        f"{emoji} {label}</div>",
        "",
        f"**Thesis:** {brief.thesis}" if brief.thesis else "",
        "",
        f"**Rationale:** {brief.recommendation_rationale}",
        "",
        "---",
    ]

    # ── Decision drivers ─────────────────────────────────────────────────────
    if brief.decision_drivers:
        lines += ["", "## Decision Drivers"]
        for d in brief.decision_drivers:
            score_str = _score_label(d.score)
            conf = f" *[{d.confidence} confidence]*" if d.confidence else ""
            src = f" ([source]({d.evidence_url}))" if d.evidence_url else ""
            lines.append(f"- **{d.name}:** {score_str} — {d.rationale}{src}{conf}")

    # ── Contradictions (the demo wow) ────────────────────────────────────────
    if brief.contradictions:
        lines += ["", "## Contradictions Found"]
        for c in brief.contradictions:
            icon = _SEVERITY_ICON.get(c.severity.lower(), "⚠️")
            verb = "CONTRADICTS" if c.is_contradiction else "CORROBORATES"
            lines += [
                f"{icon} **{c.severity.upper()} — {verb}**",
                f"- Claim ([source]({c.claim_url})): *{c.claim}*",
                f"- Web evidence ([source]({c.evidence_url})): {c.web_evidence}",
                "",
            ]
    else:
        lines += ["", "## Contradictions Found", "*No contradictions detected.*"]

    # ── Why this could break ─────────────────────────────────────────────────
    if brief.failure_paths:
        lines += ["", "## Why This Could Break"]
        for fp in brief.failure_paths:
            lines.append(f"- {fp}")

    # ── Hidden insight ───────────────────────────────────────────────────────
    if brief.hidden_insight:
        lines += ["", "## Hidden Insight", f"> {brief.hidden_insight}"]

    # ── Red flags ────────────────────────────────────────────────────────────
    if brief.red_flags:
        lines += ["", "## Red Flags"]
        for rf in brief.red_flags:
            lines.append(f"- **{rf.category}** — {rf.detail}")

    # ── Evidence sections ────────────────────────────────────────────────────
    lines += ["", "---", "", "## Founders"]
    if brief.founders:
        for f in brief.founders:
            line = f"- **{f.name}** — {f.role}. {f.background}"
            if f.notable_priors:
                line += f" *(Prior: {', '.join(f.notable_priors)})*"
            lines.append(line)
    else:
        lines.append("*No founder data found in public sources.*")

    lines += ["", "## Traction", brief.traction.summary]
    if brief.traction.github_url:
        lines.append(f"**GitHub:** {brief.traction.github_url}")
    if brief.traction.hn_mentions:
        lines.append("**HN:** " + " · ".join(brief.traction.hn_mentions))

    lines += ["", "## Hiring", brief.hiring.summary]
    if brief.hiring.open_roles:
        lines.append(f"**Open roles:** {brief.hiring.open_roles}")

    if brief.funding_history:
        lines += ["", "## Funding"]
        for r in brief.funding_history:
            investors = f" ({', '.join(r.investors)})" if r.investors else ""
            date = f" — {r.date}" if r.date else ""
            lines.append(f"- **{r.round}** {r.amount or ''}{date}{investors}")

    if brief.recent_press:
        lines += ["", "## Recent Press"]
        for p in brief.recent_press:
            date = f" ({p.date})" if p.date else ""
            lines.append(f"- [{p.title}]({p.url}){date} — *{p.source}*")

    if brief.competitive_positioning:
        cp = brief.competitive_positioning
        lines += [
            "", "## Competitive Positioning",
            f"**Segment:** {cp.market_segment}",
            f"**Differentiation:** {cp.differentiation}",
        ]
        if cp.competitors:
            lines.append(f"**Competitors:** {', '.join(cp.competitors)}")

    # ── Sources footer ───────────────────────────────────────────────────────
    if brief.sources:
        lines += ["", "---", "", "## Sources"]
        for url in brief.sources:
            lines.append(f"- <{url}>")

    if result.total_ms > 0:
        lines += ["", "---", f"*{result.stats_line()}*"]

    return "\n".join(line for line in lines if line is not None)


def _maybe_append(lines: list, label: str, value: str | None) -> None:
    if value:
        lines.append(f"**{label}:** {value}")


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="VC Scout") as ui:
        gr.Markdown("# VC Scout\nCold inbound at 9:00 AM. Investor-ready brief by 9:01 AM.")
        with gr.Row():
            company = gr.Textbox(label="Company name", placeholder="e.g. Anthropic", value="Wispr Flow")
            founder = gr.Textbox(label="Founder name (optional)")
        button = gr.Button("Scout", variant="primary")
        output = gr.Markdown()
        button.click(fn=run, inputs=[company, founder], outputs=output)
    return ui


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_ui().launch()


if __name__ == "__main__":
    main()
