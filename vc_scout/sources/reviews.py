"""G2 / Capterra reviews collector — B2B SaaS traction signals.

Adaptive: applies_to() returns True when company_type=b2b_saas.
Uses Bright Data Scraping Browser to render G2 or Capterra profile pages.

STUB — not yet implemented.
Roadmap: fetch review count, average rating, review velocity (newest review date),
named customer logos (from G2 "Used by" or Capterra "Features" section).
These are independent traction signals — reviewers are verified purchasers.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class ReviewsCollector:
    """Collector: G2/Capterra review signals.

    STUB — not implemented yet.
    Applies to: company_type=b2b_saas.
    """
    name = "G2/Capterra"

    def applies_to(self, ctx) -> bool:
        return ctx.company_type == "b2b_saas"

    def collect(self, ctx) -> list:
        log.info("G2/Capterra: collector not yet implemented — skipping.")
        return []
