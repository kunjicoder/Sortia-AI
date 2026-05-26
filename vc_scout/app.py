"""Gradio frontend for the demo.

Single text input -> structured brief rendered as markdown. Keep the UI
ruthlessly simple — the demo arc is the agent, not the layout.

Launch:
    python -m vc_scout.app
"""

from __future__ import annotations

import logging

import gradio as gr

from .models import Brief
from .orchestrator import ScoutInput, build_brief

log = logging.getLogger(__name__)


def run(company: str, founder: str) -> str:
    company = (company or "").strip()
    if not company:
        return "Please enter a company name."
    founder = (founder or "").strip() or None
    try:
        brief = build_brief(ScoutInput(company_name=company, founder_name=founder))
    except Exception as e:
        log.exception("build_brief failed")
        return f"**Error:** {e}"
    return _render_markdown(brief)


def _render_markdown(brief: Brief) -> str:
    """Render a Brief as markdown for display in Gradio."""
    lines = [
        f"# {brief.company_name}",
        f"*{brief.one_liner}*",
        "",
        f"**Recommendation:** `{brief.recommendation.value}` — {brief.recommendation_rationale}",
        "",
        "## Founders",
    ]
    for f in brief.founders:
        lines.append(f"- **{f.name}** — {f.role}. {f.background}")
    lines.append("")
    lines.append("## Traction")
    lines.append(brief.traction.summary)
    lines.append("")
    lines.append("## Hiring")
    lines.append(brief.hiring.summary)
    if brief.red_flags:
        lines.append("")
        lines.append("## Red flags")
        for rf in brief.red_flags:
            lines.append(f"- **{rf.category}** — {rf.detail}")
    return "\n".join(lines)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="VC Scout") as ui:
        gr.Markdown("# VC Scout\nCold inbound at 9:00 AM. Investor-ready brief by 9:01 AM.")
        with gr.Row():
            company = gr.Textbox(label="Company name", placeholder="e.g. Anthropic")
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
