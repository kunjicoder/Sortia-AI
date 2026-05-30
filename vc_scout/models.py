"""Pydantic schemas for the investor brief.

These are the shapes the LLM is asked to produce. Keeping them strict so the
demo UI can render reliably without defensive checks.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Recommendation(str, Enum):
    TAKE_CALL = "take_call"
    PASS = "pass"
    DIG_DEEPER = "dig_deeper"


class Founder(BaseModel):
    name: str
    role: str = Field(description="e.g. 'CEO & Co-founder'")
    background: str = Field(description="2-3 sentence summary; only what evidence supports")
    linkedin_url: Optional[str] = None
    notable_priors: List[str] = Field(default_factory=list, description="Companies, schools, achievements")


class TractionSignals(BaseModel):
    github_stars: Optional[int] = None
    github_url: Optional[str] = None
    npm_pypi_downloads: Optional[str] = None
    hn_mentions: List[str] = Field(default_factory=list, description="Recent HN front-page hits")
    producthunt_rank: Optional[str] = None
    twitter_followers: Optional[int] = None
    summary: str = Field(description="One-paragraph synthesis of overall traction")


class HiringSignals(BaseModel):
    team_size: Optional[int] = None
    open_roles: int = 0
    recent_hires: List[str] = Field(default_factory=list)
    summary: str


class PressItem(BaseModel):
    title: str
    url: str
    source: str
    date: Optional[str] = None


class FundingRound(BaseModel):
    round: str = Field(description="e.g. 'Seed', 'Series A'")
    amount: Optional[str] = None
    date: Optional[str] = None
    investors: List[str] = Field(default_factory=list)


class CompetitivePositioning(BaseModel):
    market_segment: str
    competitors: List[str] = Field(default_factory=list)
    differentiation: str


class RedFlag(BaseModel):
    category: str = Field(description="e.g. 'founder_turnover', 'missing_footprint', 'unverifiable_claim'")
    detail: str


class Contradiction(BaseModel):
    claim: str = Field(description="The claim the company makes on its own site")
    claim_url: str = Field(description="URL of the company's own page making the claim")
    web_evidence: str = Field(description="The contradicting or supporting fact from independent web sources")
    evidence_url: str = Field(description="URL of the independent source")
    severity: str = Field(description="high | medium | low")
    is_contradiction: bool = Field(description="true if contradicts, false if supports/corroborates")


class EvidencePoint(BaseModel):
    """A single cited fact backing a score driver."""
    fact: str = Field(description="The specific quoted fact from the source")
    url: str
    source_type: str = Field(description="serp | site | linkedin | ats")


class ScoreDriver(BaseModel):
    name: str = Field(description="Asymmetry | Defensibility | Timing | Founder grit")
    score: int = Field(ge=1, le=10)
    rationale: str = Field(description="1-2 sentences quoting the specific fact behind the score")
    evidence_url: str = Field(default="", description="Primary URL supporting this score")
    confidence: str = Field(description="High | Medium | Low")
    supporting_evidence: List[EvidencePoint] = Field(
        default_factory=list,
        description="1-3 cited facts backing the score",
    )


class Market(BaseModel):
    """Market context — omit or null fields that have no evidence."""
    segment: str
    sizing_note: Optional[str] = Field(default=None, description="TAM/SAM only if a size figure appears in evidence")
    tailwinds: List[str] = Field(default_factory=list, description="Short phrases grounded in evidence")
    headwinds: List[str] = Field(default_factory=list, description="Short phrases grounded in evidence")
    competitors: List[str] = Field(default_factory=list, description="Named only if they appear in a snippet")


class ResearchStep(BaseModel):
    """One entry per source actually consulted — shows the brief's work."""
    source: str = Field(description="SERP API | Scraping Browser | LinkedIn | ATS")
    examined: str = Field(description="What URL or data type was looked at")
    found: str = Field(description="What came back, or 'No data returned'")
    inference: str = Field(description="Investor-relevant takeaway, or 'Inconclusive'")


class DataCompleteness(BaseModel):
    """Honest map of which sources contributed data."""
    serp: bool
    company_site: bool
    linkedin: bool
    ats: bool
    notes: str = Field(default="", description="Gaps and how they limit confidence")


class Brief(BaseModel):
    company_name: str
    one_liner: str = Field(description="10-15 word analyst description of what the company does and for whom")
    overview: str = Field(
        default="",
        description="2-4 sentence analyst summary: what / who for / apparent stage",
    )
    thesis: str = Field(description="Falsifiable investment thesis in one sentence")
    recommendation: Recommendation
    conviction: str = Field(
        default="Medium",
        description="High | Medium | Low — confidence in the verdict itself",
    )
    recommendation_rationale: str = Field(
        description="Walk from driver scores + decisive evidence to the verdict"
    )
    founders: List[Founder] = Field(default_factory=list)
    market: Optional[Market] = Field(default=None, description="Market context from evidence")
    traction: Optional[TractionSignals] = None
    hiring: Optional[HiringSignals] = None
    recent_press: List[PressItem] = Field(default_factory=list)
    funding_history: List[FundingRound] = Field(default_factory=list)
    competitive_positioning: Optional[CompetitivePositioning] = None
    decision_drivers: List[ScoreDriver] = Field(
        default_factory=list,
        description="Exactly 4 scored drivers: Asymmetry, Defensibility, Timing, Founder grit",
    )
    contradictions: List[Contradiction] = Field(
        default_factory=list,
        description="Claims from the company site cross-checked against independent web evidence",
    )
    failure_paths: List[str] = Field(
        default_factory=list,
        description="3 company-specific failure paths",
    )
    diligence_questions: List[str] = Field(
        default_factory=list,
        description="3-5 sharp questions for the founder targeting gaps/risks/unverified claims",
    )
    hidden_insight: Optional[str] = Field(
        default=None,
        description="Inference connecting two cited facts; introduces no new named entity",
    )
    next_action: Optional[str] = Field(
        default=None,
        description="The one thing a human must do that the system can't",
    )
    research_log: List[ResearchStep] = Field(
        default_factory=list,
        description="One step per source actually used — shows the research trail",
    )
    data_completeness: Optional[DataCompleteness] = Field(
        default=None,
        description="Which sources returned data and known gaps",
    )
    red_flags: List[RedFlag] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list, description="URLs referenced during synthesis")
