"""Collector registry.

Import all collectors here. The orchestrator imports COLLECTORS and runs them.
Add new collectors by appending to COLLECTORS — no other changes needed.

Collector categories:
  Universal    — applies_to() always True (run for every company)
  Adaptive     — applies_to() checks company_type or URL presence
  DEEP-mode    — applies_to() also requires settings.deep=True (heavy async, not on live path)
"""

from __future__ import annotations

from .appstore import AppStoreCollector
from .ats import ATSCollector
from .github import GitHubCollector
from .glassdoor import GlassdoorCollector
from .linkedin import LinkedInCompanyCollector
from .linkedin_people import LinkedInPeopleCollector
from .reviews import ReviewsCollector
from .scraping_browser import CompanySiteCollector
from .serp import SerpCollector

COLLECTORS = [
    # ── Universal ──────────────────────────────────────────────────────────────
    SerpCollector(),
    CompanySiteCollector(),
    LinkedInCompanyCollector(),
    ATSCollector(),

    # ── Adaptive (company-type routing) ───────────────────────────────────────
    AppStoreCollector(),      # consumer_app — iOS rating/reviews/ranking
    GitHubCollector(),        # dev_tool     — stars/contributors/commit cadence (STUB)
    ReviewsCollector(),       # b2b_saas     — G2/Capterra review velocity (STUB)
    GlassdoorCollector(),     # all types    — sentiment/churn red flags (STUB, always False)

    # ── DEEP-mode only (gate: settings.deep=True) ─────────────────────────────
    LinkedInPeopleCollector(),  # founder pedigree: university, priors, exits
]
