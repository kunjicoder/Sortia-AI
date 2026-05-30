"""Gradio frontend — verdict-first investment memo layout.

Layout (top to bottom):
  1. Header card: company name · one_liner · verdict badge · conviction
  2. Executive summary + recommendation rationale
  3. Source chips (data completeness)
  4. Decision drivers (4 scored drivers with score bar + evidence)
  5. Contradictions / red flags / failure paths
  6. Diligence questions (left-accent cards)
  7. Research log ("How We Got Here")
  8. Hidden insight
  9. Full detail (collapsible): market · team · product · traction ·
     business_model · competition · hiring_gtm · funding
 10. Stats footer

Launch:
    python -m vc_scout.app
"""

from __future__ import annotations

import logging

import gradio as gr

from .models import InvestmentMemo, MemoSection, Recommendation
from .orchestrator import ScoutInput, ScoutResult, build_brief

log = logging.getLogger(__name__)

# ── Palette ───────────────────────────────────────────────────────────────────
_NAVY  = "#1E2761"
_NAVY2 = "#2A3A7A"
_ICE   = "#CADCFC"
_INK   = "#1A1F36"
_GREEN = "#1F9D6B"
_AMBER = "#C8841C"
_RED   = "#C0392B"

_BADGE = {
    Recommendation.TAKE_CALL:  (_GREEN, "GO — TAKE THE CALL"),
    Recommendation.DIG_DEEPER: (_AMBER, "SECOND LOOK — DIG DEEPER"),
    Recommendation.PASS:       (_RED,   "NO-GO — PASS"),
}

_CONVICTION_COLOR = {"High": _NAVY, "Medium": "#555", "Low": "#888"}

_SCORE_LABEL = [
    (range(1, 4),  "not venture scale"),
    (range(4, 7),  "plausible 10×"),
    (range(7, 9),  "real moat forming"),
    (range(9, 11), "category-defining"),
]

_SEVERITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}

_PROGRESS_STEPS = [
    "Searching the web…",
    "Reading sources…",
    "Synthesizing memo…",
]


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _trunc(text: str, max_len: int) -> str:
    text = text.replace("|", "·")
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return (truncated or text[:max_len]) + "…"


def _pill(text: str, fg: str, bg: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
        f'font-size:0.78em;font-weight:600;color:{fg};background:{bg};'
        f'letter-spacing:0.3px;white-space:nowrap">{text}</span>'
    )


def _trust_pill(trust: str) -> str:
    _c = {
        "high":   (_GREEN, "#E8F7F1"),
        "medium": (_AMBER, "#FEF5E7"),
        "low":    ("#888",  "#F5F5F5"),
    }
    fg, bg = _c.get(trust.lower(), ("#888", "#F5F5F5"))
    return _pill(trust.upper(), fg, bg)


def _conf_pill(conf: str) -> str:
    _c = {
        "high":   (_GREEN, "#E8F7F1"),
        "medium": (_AMBER, "#FEF5E7"),
        "low":    ("#888",  "#F5F5F5"),
    }
    fg, bg = _c.get(conf.lower(), ("#888", "#F5F5F5"))
    return _pill(conf, fg, bg)


def _source_chip(label: str, active: bool) -> str:
    if active:
        return (
            f'<span style="display:inline-block;padding:4px 12px;border-radius:999px;'
            f'background:{_NAVY};color:#fff;font-size:0.8em;font-weight:600;margin:3px 2px;">'
            f'{label}</span>'
        )
    return (
        f'<span style="display:inline-block;padding:4px 12px;border-radius:999px;'
        f'background:#F0F2F8;color:#B0B8CC;font-size:0.8em;font-weight:500;margin:3px 2px;">'
        f'{label}</span>'
    )


def _score_color(score: int) -> str:
    if score <= 3:
        return _RED
    if score <= 6:
        return _AMBER
    if score <= 8:
        return _NAVY
    return _GREEN


def _score_bar(score: int) -> str:
    color = _score_color(score)
    pct = score * 10
    return (
        f'<div style="background:#EDF0F8;border-radius:6px;height:8px;width:180px;'
        f'display:inline-block;vertical-align:middle;margin:4px 0 8px 0">'
        f'<div style="background:{color};width:{pct}%;height:8px;border-radius:6px"></div>'
        f'</div>'
    )


def _loading_html(step: str) -> str:
    return (
        '<div class="vcs-loading">'
        '<span class="vcs-spinner"></span>'
        f'{step}'
        '</div>'
    )


def _info_card(text: str, color: str = "") -> str:
    color = color or _AMBER
    bg = "#FFF9F2" if color == _AMBER else "#FFF2F2" if color == _RED else "#F4F6FC"
    return (
        f'<div style="padding:16px 20px;border-radius:12px;border-left:4px solid {color};'
        f'background:{bg};color:#3A4154;font-size:0.97em;margin:12px 0;">{text}</div>'
    )


# ── Run handler ───────────────────────────────────────────────────────────────

def run(company: str, founder: str):
    company = (company or "").strip()
    if not company:
        yield _info_card("Please enter a company name.")
        return
    founder = (founder or "").strip() or None

    for step in _PROGRESS_STEPS:
        yield _loading_html(step)

    try:
        result = build_brief(ScoutInput(company_name=company, founder_name=founder))
    except Exception as e:
        log.exception("build_brief failed")
        yield _info_card(f"<strong>Error:</strong> {e}", _RED)
        return

    yield _render_markdown(result)


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _score_label(score: int) -> str:
    for r, label in _SCORE_LABEL:
        if score in r:
            return f"{score}/10 · {label}"
    return f"{score}/10"


def _render_memo_section(title: str, section: MemoSection) -> list[str]:
    conf_p = _conf_pill(section.confidence)
    lines = [f"### {title}", "", f"{conf_p} — {section.summary}"]
    if section.key_points:
        lines.append("")
        for kp in section.key_points:
            lines.append(f"- {kp}")
    if section.evidence:
        lines.append("")
        lines.append("*Evidence:*")
        for ep in section.evidence:
            tp = _trust_pill(ep.trust)
            lines.append(f"- {tp} [{ep.source}]({ep.url}): *{ep.fact[:120]}*")
    lines.append("")
    return lines


def _render_markdown(result: ScoutResult) -> str:
    memo = result.memo
    color, label = _BADGE.get(memo.recommendation, ("#555", memo.recommendation.value.upper()))
    conviction = memo.conviction or "Medium"
    conv_color = _CONVICTION_COLOR.get(conviction, "#555")

    lines: list[str] = []

    # ── 1. Verdict header card ────────────────────────────────────────────────
    one_liner_html = (
        f'<p style="color:#555;margin:0 0 16px;font-size:1em;line-height:1.5">'
        f'{memo.one_liner}</p>'
    ) if memo.one_liner else ""
    lines.append(
        f'<div style="border:1px solid #E8ECF6;border-radius:14px;padding:22px 26px;'
        f'margin-bottom:20px;background:#FAFBFE;">'
        f'<h1 style="color:{_INK};font-weight:800;font-size:1.8em;margin:0 0 4px;'
        f'letter-spacing:-0.5px;">{memo.company_name}</h1>'
        f'{one_liner_html}'
        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
        f'<span style="display:inline-block;padding:8px 20px;border-radius:8px;'
        f'background:{color};color:#fff;font-weight:bold;font-size:1.1em;">{label}</span>'
        f'<span style="display:inline-block;padding:5px 12px;border-radius:6px;'
        f'background:{conv_color};color:#fff;font-size:0.85em;font-weight:600;">'
        f'{conviction} conviction</span>'
        f'</div></div>'
    )

    # ── 2. Executive summary ──────────────────────────────────────────────────
    lines += ["## Executive Summary", "", memo.executive_summary, ""]
    lines.append(f"**Rationale:** {memo.recommendation_rationale}")
    lines.append("")
    lines.append("---")

    # ── 3. Source chips ───────────────────────────────────────────────────────
    if memo.data_completeness:
        dc = memo.data_completeness
        chips = (
            _source_chip("SERP", dc.serp)
            + _source_chip("Site", dc.company_site)
            + _source_chip("LinkedIn", dc.linkedin)
            + _source_chip("ATS", dc.ats)
            + _source_chip("App Store", dc.appstore)
            + _source_chip("GitHub", dc.github)
            + _source_chip("Founders", dc.linkedin_people)
        )
        lines.append(f'<div style="margin:8px 0 4px">{chips}</div>')
        if dc.notes:
            lines.append(f"*{dc.notes}*")
        lines.append("")

    # ── 4. Decision drivers ───────────────────────────────────────────────────
    if memo.decision_drivers:
        lines += ["## Decision Drivers", ""]
        for d in memo.decision_drivers:
            score_str = _score_label(d.score)
            conf_p = f" {_conf_pill(d.confidence)}" if d.confidence else ""
            lines.append(f"**{d.name}** — {score_str}{conf_p}")
            lines.append(_score_bar(d.score))
            lines.append(f"> {d.rationale}")
            for ep in d.supporting_evidence:
                tp = _trust_pill(ep.trust)
                lines.append(f"> {tp} *{ep.fact[:120]}* — [{ep.source}]({ep.url})")
            lines.append("")

    lines.append("---")

    # ── 5. Contradictions · red flags · failure paths ─────────────────────────
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

    # ── 6. Diligence questions — left-accent cards ────────────────────────────
    if memo.diligence_questions:
        lines += ["## Diligence Questions", ""]
        for i, q in enumerate(memo.diligence_questions, 1):
            lines.append(
                f'<div style="border-left:3px solid {_NAVY};background:#F8FAFE;'
                f'padding:10px 16px;margin:8px 0;border-radius:0 8px 8px 0;">'
                f'<span style="color:#AAB0C0;font-size:0.75em;font-weight:700;'
                f'letter-spacing:0.5px;text-transform:uppercase">Q{i}</span>'
                f'<div style="color:{_INK};margin-top:4px">{q}</div>'
                f'</div>'
            )
        lines.append("")

    lines.append("---")

    # ── 7. Research log ───────────────────────────────────────────────────────
    if memo.research_log:
        lines += ["## How We Got Here", ""]
        lines.append("| Source | Examined | Found | Investor Inference |")
        lines.append("|--------|----------|-------|--------------------|")
        for step in memo.research_log:
            found     = _trunc(step.found, 160)
            inference = _trunc(step.inference, 100)
            examined  = _trunc(step.examined, 80)
            lines.append(f"| **{step.source}** | {examined} | {found} | {inference} |")
        lines.append("")

    # ── 8. Hidden insight ─────────────────────────────────────────────────────
    if memo.hidden_insight:
        lines += ["## Hidden Insight", f"> {memo.hidden_insight}", ""]

    # ── 9. Full detail (collapsible) ──────────────────────────────────────────
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
                tp = _trust_pill(ep.trust)
                detail_lines.append(f"  - {tp} *{ep.fact[:100]}* — [{ep.source}]({ep.url})")
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

    # ── Stats footer ──────────────────────────────────────────────────────────
    if result.total_ms > 0:
        lines += ["", "---", f"*{result.stats_line()}*"]

    return "\n".join(line for line in lines if line is not None)


# ── Theme + CSS ───────────────────────────────────────────────────────────────

_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.slate,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
)

_CSS = """
.gradio-container { max-width: 940px !important; margin: 0 auto !important; }

/* Header band */
#vcs-header {
  background: linear-gradient(135deg, #1E2761 0%, #2A3A7A 100%);
  border-radius: 16px; padding: 26px 30px; margin-bottom: 18px;
  box-shadow: 0 6px 20px rgba(30,39,97,0.18);
}
#vcs-header h1 { color:#fff; margin:0; font-size:1.9em; font-weight:800; letter-spacing:-0.5px; }
#vcs-header p { color:#CADCFC; margin:6px 0 0; font-size:1.02em; }
#vcs-header .pill {
  display:inline-block; margin-top:14px; padding:5px 14px; border-radius:999px;
  background:rgba(255,255,255,0.12); color:#fff; font-size:0.8em; font-weight:600;
  letter-spacing:0.4px;
}

/* Input row + button */
#vcs-controls { background:#F4F6FC; border:1px solid #E2E8F5; border-radius:14px; padding:16px 18px; }
#vcs-btn button {
  background:#1E2761 !important; border:none !important; color:#fff !important;
  font-weight:700 !important; border-radius:10px !important; letter-spacing:0.3px;
}
#vcs-btn button:hover { background:#2A3A7A !important; }

/* Memo output card */
#vcs-output {
  background:#fff; border:1px solid #E8ECF6; border-radius:16px;
  padding:30px 34px; margin-top:18px; box-shadow:0 4px 18px rgba(30,39,97,0.06);
  line-height:1.6;
}
#vcs-output h1 { color:#1A1F36; font-weight:800; letter-spacing:-0.5px; margin-bottom:2px; }
#vcs-output h2 { color:#1E2761; font-weight:700; margin-top:26px; font-size:1.25em; }
#vcs-output h3 { color:#1E2761; font-weight:700; }
#vcs-output a { color:#2A3A7A; text-decoration:none; border-bottom:1px solid #CADCFC; }
#vcs-output a:hover { border-bottom-color:#2A3A7A; }
#vcs-output hr { border:none; border-top:1px solid #EDF0F8; margin:28px 0; }

/* Blockquotes = driver rationales */
#vcs-output blockquote {
  border-left:3px solid #CADCFC; background:#F8FAFE; margin:6px 0;
  padding:8px 16px; color:#3A4154; border-radius:0 8px 8px 0;
}

/* Research-log table: wrap, don't clip */
#vcs-output table { border-collapse:collapse; width:100%; margin:10px 0; font-size:0.92em; }
#vcs-output th { background:#1E2761; color:#fff; text-align:left; padding:10px 12px; font-weight:600; }
#vcs-output td { padding:10px 12px; border-bottom:1px solid #EDF0F8; vertical-align:top;
  white-space:normal; word-break:break-word; }
#vcs-output tr:nth-child(even) td { background:#FAFBFE; }

/* Collapsible full-detail */
#vcs-output details {
  border:1px solid #E8ECF6; border-radius:12px; padding:8px 16px; margin-top:18px; background:#FBFCFE;
}
#vcs-output summary { cursor:pointer; color:#1E2761; padding:6px 0; }

/* Loading spinner */
@keyframes vcs-spin { to { transform: rotate(360deg); } }
.vcs-spinner {
  display:inline-block; width:18px; height:18px;
  border:3px solid #E2E8F5; border-top-color:#1E2761;
  border-radius:50%; animation:vcs-spin 0.8s linear infinite;
  vertical-align:middle; margin-right:10px;
}
.vcs-loading {
  text-align:center; padding:40px 0; color:#1E2761;
  font-size:1.05em; font-weight:600;
}
"""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="VC Scout", theme=_THEME, css=_CSS) as ui:
        gr.HTML(
            '<div id="vcs-header">'
            '<h1>VC Scout</h1>'
            '<p>Cold inbound at 9:00 AM. Investor-ready memo by 9:01.</p>'
            '<span class="pill">GROUNDED, NOT GENERATIVE</span>'
            '</div>'
        )
        with gr.Row(elem_id="vcs-controls"):
            company = gr.Textbox(label="Company name", placeholder="e.g. Anthropic", value="Wispr Flow", scale=3)
            founder = gr.Textbox(label="Founder name (optional)", scale=2)
        button = gr.Button("Scout the company →", variant="primary", elem_id="vcs-btn")
        output = gr.Markdown(elem_id="vcs-output")
        button.click(fn=run, inputs=[company, founder], outputs=output)
    return ui


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_ui().launch()


if __name__ == "__main__":
    main()
