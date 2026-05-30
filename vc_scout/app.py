"""Gradio frontend — verdict-first investment memo layout.

Layout (top to bottom):
  1. Header: company name · verdict badge · conviction · one_liner
  2. Executive summary + recommendation rationale
  3. Data completeness strip
  4. Decision drivers (4 scored drivers with evidence)
  5. Contradictions / red flags / failure paths
  6. Diligence questions
  7. Research log ("How We Got Here")
  8. Hidden insight
  9. Full detail (collapsible): market · team · product · traction ·
     business_model · competition · hiring_gtm · funding
 10. Sources · stats footer

Launch:
    python -m vc_scout.app
"""

from __future__ import annotations

import logging

import gradio as gr

from .models import InvestmentMemo, MemoSection, Recommendation
from .orchestrator import ScoutInput, ScoutResult, build_brief

log = logging.getLogger(__name__)

_BADGE = {
    Recommendation.TAKE_CALL:  ("#1a7a1a", "GO — TAKE THE CALL"),
    Recommendation.DIG_DEEPER: ("#7a6200", "SECOND LOOK — DIG DEEPER"),
    Recommendation.PASS:       ("#8b0000", "NO-GO — PASS"),
}

_CONVICTION_COLOR = {"High": "#1a4a7a", "Medium": "#555", "Low": "#888"}

_SCORE_LABEL = [
    (range(1, 4),  "not venture scale"),
    (range(4, 7),  "plausible 10×"),
    (range(7, 9),  "real moat forming"),
    (range(9, 11), "category-defining"),
]

_SEVERITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}
_TRUST_ICON = {"high": "✅", "medium": "🟡", "low": "⚠️"}

_PROGRESS_STEPS = [
    "Searching the web…",
    "Reading sources…",
    "Synthesizing memo…",
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
    for r, label in _SCORE_LABEL:
        if score in r:
            return f"{score}/10 · {label}"
    return f"{score}/10"


def _render_memo_section(title: str, section: MemoSection) -> list[str]:
    conf_icon = _TRUST_ICON.get(section.confidence.lower(), "")
    lines = [f"### {title}", "", f"{conf_icon} *{section.confidence} confidence* — {section.summary}"]
    if section.key_points:
        lines.append("")
        for kp in section.key_points:
            lines.append(f"- {kp}")
    if section.evidence:
        lines.append("")
        lines.append("*Evidence:*")
        for ep in section.evidence:
            icon = _TRUST_ICON.get(ep.trust.lower(), "🔗")
            lines.append(f"- {icon} [{ep.source}]({ep.url}): *{ep.fact[:120]}*")
    lines.append("")
    return lines


def _render_markdown(result: ScoutResult) -> str:
    memo = result.memo
    color, label = _BADGE.get(memo.recommendation, ("#555", memo.recommendation.value.upper()))
    conviction = memo.conviction or "Medium"
    conv_color = _CONVICTION_COLOR.get(conviction, "#555")

    lines: list[str] = []

    # ── 1. Header band ───────────────────────────────────────────────────────
    lines.append(f"# {memo.company_name}")
    if memo.one_liner:
        lines.append(f"*{memo.one_liner}*")
    lines.append("")
    lines.append(
        f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">'
        f'<span style="display:inline-block;padding:10px 22px;border-radius:8px;'
        f'background:{color};color:#fff;font-weight:bold;font-size:1.2em;">{label}</span>'
        f'<span style="display:inline-block;padding:6px 14px;border-radius:6px;'
        f'background:{conv_color};color:#fff;font-size:0.9em;">{conviction} conviction</span>'
        f'</div>'
    )
    lines.append("")

    # ── 2. Executive summary ─────────────────────────────────────────────────
    lines += ["## Executive Summary", "", memo.executive_summary, ""]
    lines.append(f"**Rationale:** {memo.recommendation_rationale}")
    lines.append("")
    lines.append("---")

    # ── 3. Data completeness strip ───────────────────────────────────────────
    if memo.data_completeness:
        dc = memo.data_completeness
        strips = []
        strips.append("🌐 SERP" if dc.serp else "~~🌐 SERP~~")
        strips.append("🏠 Site" if dc.company_site else "~~🏠 Site~~")
        strips.append("💼 LinkedIn" if dc.linkedin else "~~💼 LinkedIn~~")
        strips.append("📋 ATS" if dc.ats else "~~📋 ATS~~")
        if dc.appstore:
            strips.append("📱 App Store")
        if dc.github:
            strips.append("🐙 GitHub")
        if dc.linkedin_people:
            strips.append("👤 Founders")
        lines += [f"*Sources: {' · '.join(strips)}*", ""]
        if dc.notes:
            lines.append(f"*{dc.notes}*")
        lines.append("")

    # ── 4. Decision drivers ──────────────────────────────────────────────────
    if memo.decision_drivers:
        lines += ["## Decision Drivers", ""]
        for d in memo.decision_drivers:
            score_str = _score_label(d.score)
            conf = f" · *{d.confidence} confidence*" if d.confidence else ""
            lines.append(f"**{d.name}** — {score_str}{conf}")
            lines.append(f"> {d.rationale}")
            for ep in d.supporting_evidence:
                icon = _TRUST_ICON.get(ep.trust.lower(), "🔗")
                lines.append(f"> {icon} *{ep.fact[:120]}* — [{ep.source}]({ep.url})")
            lines.append("")

    lines.append("---")

    # ── 5. Contradictions · red flags · failure paths ────────────────────────
    if memo.contradictions:
        lines += ["## Contradictions", ""]
        for c in memo.contradictions:
            icon = _SEVERITY_ICON.get(c.severity.lower(), "⚠️")
            verb = "CONTRADICTS" if c.is_contradiction else "CORROBORATES"
            lines += [
                f"{icon} **{c.severity.upper()} — {verb}**",
                f"- Claim ([source]({c.claim_url})): *{c.claim}*",
                f"- Evidence ([source]({c.evidence_url})): {c.web_evidence}",
                "",
            ]

    if memo.risks_red_flags:
        lines += ["## Red Flags", ""]
        for rf in memo.risks_red_flags:
            lines.append(f"- **{rf.category}** — {rf.detail}")
        lines.append("")

    if memo.failure_paths:
        lines += ["## Why This Could Break", ""]
        for fp in memo.failure_paths:
            lines.append(f"- {fp}")
        lines.append("")

    # ── 6. Diligence questions ───────────────────────────────────────────────
    if memo.diligence_questions:
        lines += ["## Diligence Questions", ""]
        for i, q in enumerate(memo.diligence_questions, 1):
            lines.append(f"{i}. {q}")
        lines.append("")

    lines.append("---")

    # ── 7. Research log ──────────────────────────────────────────────────────
    if memo.research_log:
        lines += ["## How We Got Here", ""]
        lines.append("| Source | Examined | Found | Investor Inference |")
        lines.append("|--------|----------|-------|--------------------|")
        for step in memo.research_log:
            found = step.found.replace("|", "·")[:80]
            inference = step.inference.replace("|", "·")[:100]
            examined = step.examined.replace("|", "·")[:60]
            lines.append(f"| **{step.source}** | {examined} | {found} | {inference} |")
        lines.append("")

    # ── 8. Hidden insight ─────────────────────────────────────────────────────
    if memo.hidden_insight:
        lines += ["## Hidden Insight", f"> {memo.hidden_insight}", ""]

    # ── 9. Full detail (collapsible) ─────────────────────────────────────────
    detail_lines: list[str] = []

    if memo.market:
        detail_lines += _render_memo_section("Market", memo.market)

    if memo.team:
        detail_lines += ["### Team", ""]
        for f in memo.team:
            detail_lines.append(f"**{f.name}** — {f.role}")
            if f.university:
                detail_lines.append(f"  - University: {f.university}")
            if f.prior_companies:
                detail_lines.append(f"  - Prior: {', '.join(f.prior_companies)}")
            if f.prior_exits_or_scaling:
                detail_lines.append(f"  - Exits/scaling: {f.prior_exits_or_scaling}")
            if f.domain_fit:
                detail_lines.append(f"  - Domain fit: {f.domain_fit}")
            if f.linkedin_url:
                detail_lines.append(f"  - [LinkedIn]({f.linkedin_url})")
            for ep in f.evidence:
                icon = _TRUST_ICON.get(ep.trust.lower(), "🔗")
                detail_lines.append(f"  - {icon} *{ep.fact[:100]}* — [{ep.source}]({ep.url})")
            detail_lines.append("")

    if memo.team_assessment:
        detail_lines += _render_memo_section("Team Assessment", memo.team_assessment)

    if memo.product:
        detail_lines += _render_memo_section("Product", memo.product)

    if memo.traction:
        detail_lines += _render_memo_section("Traction", memo.traction)

    if memo.business_model:
        detail_lines += _render_memo_section("Business Model", memo.business_model)

    if memo.competition:
        detail_lines += _render_memo_section("Competition", memo.competition)

    if memo.hiring_gtm:
        detail_lines += _render_memo_section("Hiring / GTM", memo.hiring_gtm)

    if memo.funding:
        detail_lines += ["### Funding", ""]
        for r in memo.funding:
            investors = f" ({', '.join(r.investors)})" if r.investors else ""
            date = f" — {r.date}" if r.date else ""
            detail_lines.append(f"- **{r.round}** {r.amount or ''}{date}{investors}")
        detail_lines.append("")

    if memo.sources:
        detail_lines += ["### Sources", ""]
        for url in memo.sources:
            detail_lines.append(f"- <{url}>")

    if detail_lines:
        lines += [
            "<details>",
            "<summary><strong>Full Detail (market · team · product · traction · competition · funding)</strong></summary>",
            "",
            "\n".join(detail_lines),
            "",
            "</details>",
        ]

    # ── Stats footer ─────────────────────────────────────────────────────────
    if result.total_ms > 0:
        lines += ["", "---", f"*{result.stats_line()}*"]

    return "\n".join(line for line in lines if line is not None)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="VC Scout") as ui:
        gr.Markdown("# VC Scout\nCold inbound at 9:00 AM. Investor-ready memo by 9:01 AM.")
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
