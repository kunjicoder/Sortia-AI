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
    from vc_scout.sources import (  # noqa: F401
        appstore, ats, base, github, glassdoor, linkedin,
        linkedin_people, registry, resolve, reviews, scraping_browser, serp,
    )


def test_investment_memo_schema_round_trips():
    """A minimal InvestmentMemo should round-trip through Pydantic validation."""
    from vc_scout.models import (
        DataCompleteness,
        EvidencePoint,
        Founder,
        InvestmentMemo,
        MemoSection,
        Recommendation,
        ScoreDriver,
    )

    memo = InvestmentMemo(
        company_name="Acme AI",
        one_liner="LLM-powered industrial vision tool for quality inspection teams",
        executive_summary="Acme AI is a focused industrial vision startup. Evidence is thin but team pedigree is strong.",
        recommendation=Recommendation.DIG_DEEPER,
        conviction="Medium",
        recommendation_rationale="Strong team, unclear traction signal yet.",
        market=MemoSection(
            summary="Industrial AI market growing rapidly.",
            key_points=["Factory automation demand"],
            confidence="Medium",
        ),
        team=[
            Founder(
                name="Jane Doe",
                role="CEO & Co-founder",
                university="Stanford",
                prior_companies=["Google"],
                domain_fit="Ex-Google research engineer — direct overlap with vision model deployment.",
                evidence=[
                    EvidencePoint(
                        fact="Jane Doe was a research engineer at Google Brain.",
                        url="https://linkedin.com/in/janedoe",
                        source="LinkedIn",
                        trust="high",
                    )
                ],
            )
        ],
        decision_drivers=[
            ScoreDriver(
                name="Asymmetry",
                score=6,
                confidence="Medium",
                rationale="Vision model commoditization risk is real but vertical wedge is defensible.",
            ),
            ScoreDriver(name="Defensibility", score=5, confidence="Low", rationale="No moat evidence yet."),
            ScoreDriver(name="Timing", score=7, confidence="Medium", rationale="Factory automation wave is now."),
            ScoreDriver(name="Founder grit", score=7, confidence="Medium", rationale="Google pedigree + repeat domain."),
        ],
        data_completeness=DataCompleteness(serp=True, company_site=False, linkedin=False, ats=False),
    )
    payload = memo.model_dump_json()
    InvestmentMemo.model_validate_json(payload)


def test_render_markdown_does_not_raise():
    """_render_markdown must survive a minimal InvestmentMemo without throwing.

    This guards the demo's most critical render path. The UI calls this
    function directly and shows its output to the user — a crash here
    means a blank screen during the live demo.
    """
    from vc_scout.app import _render_markdown
    from vc_scout.models import (
        DataCompleteness,
        InvestmentMemo,
        Recommendation,
        ScoreDriver,
    )
    from vc_scout.orchestrator import ScoutResult

    memo = InvestmentMemo(
        company_name="Acme AI",
        one_liner="LLM-powered industrial vision tool for quality inspection teams",
        executive_summary="Acme AI is building industrial vision AI. Evidence is thin but team pedigree is strong.",
        recommendation=Recommendation.DIG_DEEPER,
        conviction="Medium",
        recommendation_rationale="Strong team, unclear traction signal yet.",
        decision_drivers=[
            ScoreDriver(name="Asymmetry", score=6, confidence="Medium", rationale="Vertical wedge defensible."),
            ScoreDriver(name="Defensibility", score=5, confidence="Low", rationale="No moat evidence yet."),
            ScoreDriver(name="Timing", score=7, confidence="Medium", rationale="Factory automation wave is now."),
            ScoreDriver(name="Founder grit", score=7, confidence="Medium", rationale="Google pedigree."),
        ],
        data_completeness=DataCompleteness(serp=True, company_site=False, linkedin=False, ats=False),
    )
    scout_result = ScoutResult(memo=memo, serp_ms=1200, collect_ms=0, llm_ms=5800, source_count=4)
    result = _render_markdown(scout_result)
    assert "Acme AI" in result
    assert any(s in result for s in ("DIG_DEEPER", "dig_deeper", "DIG DEEPER", "SECOND LOOK"))
    assert "sources read" in result
