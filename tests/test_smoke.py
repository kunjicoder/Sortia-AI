"""Smoke tests. Prove the package imports and models validate.

These do not call any external API. They guard against the dumb stuff —
syntax errors, broken imports, schema typos — that breaks the build on
Saturday morning when there is no time to debug.

Run: pytest -q
"""

from __future__ import annotations


def test_package_imports():
    import vc_scout  # noqa: F401
    from vc_scout import bundle, config, llm, models, orchestrator  # noqa: F401
    from vc_scout.sources import linkedin, scraping_browser, serp, ats  # noqa: F401


def test_brief_schema_round_trips():
    """A minimal Brief should round-trip through Pydantic validation."""
    from vc_scout.models import (
        Brief,
        CompetitivePositioning,
        DataCompleteness,
        Founder,
        HiringSignals,
        Market,
        Recommendation,
        TractionSignals,
    )

    brief = Brief(
        company_name="Acme AI",
        one_liner="LLM-powered acme detector",
        thesis="Acme AI could be the first industrial vision company to reach 10× ARR on a focused wedge.",
        founders=[
            Founder(
                name="Jane Doe",
                role="CEO & Co-founder",
                background="Ex-Google research engineer, Stanford CS PhD.",
            )
        ],
        traction=TractionSignals(summary="Early but growing."),
        hiring=HiringSignals(summary="Team of 6, 2 open roles."),
        competitive_positioning=CompetitivePositioning(
            market_segment="Applied AI",
            differentiation="Vertical focus on industrial vision.",
        ),
        market=Market(segment="Industrial AI", tailwinds=["Automation demand"]),
        data_completeness=DataCompleteness(serp=True, company_site=False, linkedin=False, ats=False),
        recommendation=Recommendation.DIG_DEEPER,
        recommendation_rationale="Strong team, unclear traction signal yet.",
    )
    payload = brief.model_dump_json()
    Brief.model_validate_json(payload)


def test_render_markdown_does_not_raise():
    """_render_markdown must survive a minimal Brief without throwing.

    This guards the demo's most critical render path. The UI calls this
    function directly and shows its output to the user — a crash here
    means a blank screen during the live demo.
    """
    from vc_scout.app import _render_markdown
    from vc_scout.models import (
        Brief,
        CompetitivePositioning,
        DataCompleteness,
        Founder,
        HiringSignals,
        Market,
        Recommendation,
        TractionSignals,
    )
    from vc_scout.orchestrator import ScoutResult

    brief = Brief(
        company_name="Acme AI",
        one_liner="LLM-powered acme detector",
        thesis="Acme AI could be the first industrial vision company to reach 10× ARR on a focused wedge.",
        founders=[
            Founder(
                name="Jane Doe",
                role="CEO & Co-founder",
                background="Ex-Google research engineer, Stanford CS PhD.",
            )
        ],
        traction=TractionSignals(summary="Early but growing."),
        hiring=HiringSignals(summary="Team of 6, 2 open roles."),
        competitive_positioning=CompetitivePositioning(
            market_segment="Applied AI",
            differentiation="Vertical focus on industrial vision.",
        ),
        market=Market(segment="Industrial AI"),
        data_completeness=DataCompleteness(serp=True, company_site=False, linkedin=False, ats=False),
        recommendation=Recommendation.DIG_DEEPER,
        recommendation_rationale="Strong team, unclear traction signal yet.",
    )
    scout_result = ScoutResult(brief=brief, serp_ms=1200, llm_ms=5800, source_count=4)
    result = _render_markdown(scout_result)
    assert "Acme AI" in result
    assert any(s in result for s in ("DIG_DEEPER", "dig_deeper", "DIG DEEPER", "SECOND LOOK"))
    assert "sources read" in result
