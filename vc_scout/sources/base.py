"""Collector contract: Signal, EntityContext, Collector protocol.

Every source wraps itself as a Collector so the orchestrator can:
  - ask ``applies_to(ctx)`` to decide whether to run it
  - call ``collect(ctx)`` and receive a flat list of Signal objects
  - run all applicable collectors concurrently with ThreadPoolExecutor

Design notes:
- Signal.trust = "high" for independent sources (SERP, LinkedIn), "medium" for
  ATS/GitHub/App Store (first-party but structured), "low" for self-reported site copy.
- EntityContext is resolved once from the initial SERP pass and passed to every
  collector, so no source re-does the SERP lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Signal:
    section: str   # "market" | "team" | "product" | "traction" | "funding" | "competition" | "hiring" | "risks" | "business_model"
    fact: str      # quoted or derived fact
    url: str
    source: str    # human-readable source name: "SERP", "Scraping Browser", "LinkedIn", "ATS", "App Store", "GitHub", ...
    trust: str     # "high" | "medium" | "low"
    key: str = ""            # optional machine key, e.g. "employee_count", "stars"
    value: Any = None        # optional structured value
    date: str = ""


@dataclass
class EntityContext:
    """Resolved entity metadata — built once, passed to every collector."""
    company: str
    domain: str = ""
    linkedin_company_url: str = ""
    linkedin_people_urls: list[str] = field(default_factory=list)
    careers_url: str = ""
    github_url: str = ""
    appstore_url: str = ""      # iOS App Store link if found in SERP
    playstore_url: str = ""     # Google Play link if found in SERP
    company_type: str = "unknown"   # "dev_tool" | "consumer_app" | "b2b_saas" | "unknown"
    serp_results: list[dict] = field(default_factory=list)


@runtime_checkable
class Collector(Protocol):
    """Protocol every collector must satisfy."""
    name: str

    def applies_to(self, ctx: EntityContext) -> bool:
        """Return True if this collector is relevant for the given entity."""
        ...

    def collect(self, ctx: EntityContext) -> list[Signal]:
        """Run the collection; degrade to [] on any failure."""
        ...
