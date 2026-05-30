"""GitHub collector — dev-tool traction signals (stars, contributors, commit cadence).

Adaptive: applies_to() returns True when company_type=dev_tool OR github_url is present.
Uses Bright Data Scraping Browser to render the GitHub repo page.

STUB — not yet implemented.
Roadmap: fetch stars, forks, contributor count, commit frequency, open issues.
These are independent (GitHub's own data) and high-trust traction signals for dev tools.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class GitHubCollector:
    """Collector: GitHub repo signals (stars, contributors, commit cadence).

    STUB — not implemented yet.
    Applies to: company_type=dev_tool OR github_url present in EntityContext.
    """
    name = "GitHub"

    def applies_to(self, ctx) -> bool:
        return bool(ctx.github_url) or ctx.company_type == "dev_tool"

    def collect(self, ctx) -> list:
        log.info("GitHub: collector not yet implemented — skipping.")
        return []
