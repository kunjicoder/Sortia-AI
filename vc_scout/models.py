"""Pydantic schemas for the investment memo.

InvestmentMemo mirrors the real 1-3 page deal memo a VC analyst submits,
ordered Market → Team → Product → Traction → ... → Verdict.

Every field obeys anti-hallucination: omit/empty when no evidence.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Recommendation(str, Enum):
    TAKE_CALL = "take_call"
    PASS = "pass"
    DIG_DEEPER = "dig_deeper"


class EvidencePoint(BaseModel):
    fact: str = Field(description="Quoted or derived fact from the source")
    url: str
    source: str = Field(description="SERP | Scraping Browser | LinkedIn | ATS | App Store | GitHub | ...")
    trust: str = Field(description="high | medium | low")


class Founder(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = Field(default=None, description="e.g. 'CEO & Co-founder'")
    university: Optional[str] = Field(default=None, description="Only if found in evidence; never guess")
    prior_companies: List[str] = Field(default_factory=list, description="Named only if in evidence")
    prior_exits_or_scaling: Optional[str] = Field(default=None, description="e.g. 'co-founded X (acq. 2021)'; null if not in evidence")
    domain_fit: Optional[str] = Field(default=None, description="1 sentence on why their background fits this problem")
    linkedin_url: Optional[str] = None
    evidence: List[EvidencePoint] = Field(default_factory=list, description="Where pedigree facts came from")


class MemoSection(BaseModel):
    summary: str = Field(description="Analyst prose for this section, from evidence only")
    key_points: List[str] = Field(default_factory=list)
    evidence: List[EvidencePoint] = Field(default_factory=list)
    confidence: str = Field(description="High | Medium | Low — based on independent source coverage")


class FundingRound(BaseModel):
    round: Optional[str] = Field(default=None, description="e.g. 'Seed', 'Series A'")
    amount: Optional[str] = None
    date: Optional[str] = None
    investors: List[str] = Field(default_factory=list)


class ScoreDriver(BaseModel):
    name: str = Field(description="Asymmetry | Defensibility | Timing | Founder grit")
    score: int = Field(ge=1, le=10)
    confidence: str = Field(description="High | Medium | Low")
    rationale: str = Field(description="1-2 sentences quoting the specific fact behind the score")
    supporting_evidence: List[EvidencePoint] = Field(default_factory=list)


class Contradiction(BaseModel):
    claim: str
    claim_url: str
    web_evidence: str
    evidence_url: str
    severity: str = Field(description="high | medium | low")
    is_contradiction: bool


class RedFlag(BaseModel):
    category: str = Field(description="e.g. 'missing_footprint', 'unverifiable_claim', 'leadership_churn'")
    detail: str


class ResearchStep(BaseModel):
    source: str
    examined: str
    found: str
    inference: str = Field(default="", description="Investor-relevant takeaway, or 'Inconclusive'")


class DataCompleteness(BaseModel):
    serp: bool
    company_site: bool
    linkedin: bool
    ats: bool
    linkedin_people: bool = False
    appstore: bool = False
    github: bool = False
    notes: str = Field(default="")


class InvestmentMemo(BaseModel):
    """Full investment memo — mirrors the real VC analyst deal memo."""
    company_name: str
    one_liner: str = Field(description="10-15 word analyst description: what it does and for whom")
    executive_summary: str = Field(description="3-5 sentences: opportunity, why interesting, the read")
    recommendation: Recommendation
    conviction: str = Field(default="Medium", description="High | Medium | Low — confidence in the verdict")
    recommendation_rationale: str = Field(description="Walk driver scores + decisive evidence → verdict; show the reasoning")

    # Memo sections in VC order (Optional so LLM can omit sections with no evidence)
    market: Optional[MemoSection] = None
    team: List[Founder] = Field(default_factory=list)
    team_assessment: Optional[MemoSection] = None
    product: Optional[MemoSection] = None
    traction: Optional[MemoSection] = None
    business_model: Optional[MemoSection] = None
    competition: Optional[MemoSection] = None
    funding: List[FundingRound] = Field(default_factory=list)
    hiring_gtm: Optional[MemoSection] = None

    @field_validator("funding")
    @classmethod
    def _filter_empty_funding(cls, v: list) -> list:
        return [r for r in v if r.round]

    @field_validator("team")
    @classmethod
    def _filter_empty_team(cls, v: list) -> list:
        return [f for f in v if f.name]

    # Verdict machinery
    decision_drivers: List[ScoreDriver] = Field(
        default_factory=list,
        description="Exactly 4: Asymmetry | Defensibility | Timing | Founder grit",
    )
    contradictions: List[Contradiction] = Field(default_factory=list)
    risks_red_flags: List[RedFlag] = Field(default_factory=list)
    failure_paths: List[str] = Field(default_factory=list)
    diligence_questions: List[str] = Field(
        default_factory=list,
        description="3-5 sharp questions targeting gaps not publicly sourceable",
    )
    hidden_insight: str = Field(default="", description="One inference connecting two cited facts; no new named entity")

    # Research provenance — populated deterministically after LLM synthesis
    research_log: List[ResearchStep] = Field(default_factory=list)
    data_completeness: Optional[DataCompleteness] = None
    sources: List[str] = Field(default_factory=list)

    @field_validator("research_log")
    @classmethod
    def _filter_unknown_sources(cls, v: list) -> list:
        known = frozenset({
            "SERP API", "Scraping Browser", "LinkedIn", "ATS",
            "GitHub", "App Store", "LinkedIn People", "G2/Capterra", "Glassdoor",
        })
        return [step for step in v if step.source in known]
