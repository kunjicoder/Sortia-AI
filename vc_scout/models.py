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


class Brief(BaseModel):
    company_name: str
    one_liner: str
    founders: List[Founder]
    traction: TractionSignals
    hiring: HiringSignals
    recent_press: List[PressItem] = Field(default_factory=list)
    funding_history: List[FundingRound] = Field(default_factory=list)
    competitive_positioning: CompetitivePositioning
    red_flags: List[RedFlag] = Field(default_factory=list)
    recommendation: Recommendation
    recommendation_rationale: str = Field(description="Why this recommendation, in 2-3 sentences")
    sources: List[str] = Field(default_factory=list, description="URLs referenced during synthesis")
