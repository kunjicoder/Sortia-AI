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
    background: str = Field(description="2-3 sentence summary of prior work and education")
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


class ScoreDriver(BaseModel):
    name: str = Field(description="Asymmetry | Defensibility | Timing | Founder grit")
    score: int = Field(ge=1, le=10)
    rationale: str = Field(description="One sentence justification naming the evidence")
    evidence_url: str = Field(default="", description="Primary URL supporting this score")
    confidence: str = Field(description="High | Medium | Low")


class Brief(BaseModel):
    company_name: str
    one_liner: str
    thesis: str = Field(description="Investment thesis in one sentence")
    founders: List[Founder]
    traction: TractionSignals
    hiring: HiringSignals
    recent_press: List[PressItem] = Field(default_factory=list)
    funding_history: List[FundingRound] = Field(default_factory=list)
    competitive_positioning: CompetitivePositioning
    red_flags: List[RedFlag] = Field(default_factory=list)
    contradictions: List[Contradiction] = Field(
        default_factory=list,
        description="Claims from the company site cross-checked against independent web evidence",
    )
    decision_drivers: List[ScoreDriver] = Field(
        default_factory=list,
        description="Scored drivers: Asymmetry, Defensibility, Timing, Founder grit",
    )
    failure_paths: List[str] = Field(
        default_factory=list,
        description="3 likeliest ways this company fails",
    )
    hidden_insight: Optional[str] = Field(
        default=None,
        description="Non-obvious signal grounded in a specific piece of evidence",
    )
    next_action: Optional[str] = Field(
        default=None,
        description="The one thing a human must do that the system can't",
    )
    recommendation: Recommendation
    recommendation_rationale: str = Field(description="Why this recommendation, in 2-3 sentences")
    sources: List[str] = Field(default_factory=list, description="URLs referenced during synthesis")
