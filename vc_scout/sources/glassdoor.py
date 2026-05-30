"""Glassdoor collector — employee sentiment and leadership churn red flags.

Universal (all companies), but low-priority — run last.
Uses Bright Data Scraping Browser or Web Unlocker to render the Glassdoor company page.

STUB — not yet implemented.
Roadmap: fetch overall rating, CEO approval rating, "recommend to a friend" %,
recent review headlines (especially negative), layoff mentions.
These go to section="risks" as medium-trust signals (employee self-report, but aggregated).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class GlassdoorCollector:
    """Collector: Glassdoor sentiment and leadership churn signals.

    STUB — not implemented yet.
    Universal: applies_to() always returns False until implemented.
    """
    name = "Glassdoor"

    def applies_to(self, ctx) -> bool:
        return False  # stub — enable once implemented

    def collect(self, ctx) -> list:
        log.info("Glassdoor: collector not yet implemented — skipping.")
        return []
