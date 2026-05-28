"""Main agent loop.

Given a company name, fan out to Bright Data sources, then ask the LLM to
synthesize a structured Brief. This is the orchestration core — keep it
readable; everything that can be tucked into a sub-module should be.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import settings
from .llm import complete_structured
from .models import Brief
from .sources import serp

# NOTE: LinkedIn (Web Scraper API) is cut from the demo path — hardest scraping
# target, highest risk, no runway. Web Unlocker is added in V2 as source #2.

log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent / "demo_cache"


def _slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def _load_cache(company: str) -> Brief | None:
    path = _CACHE_DIR / f"{_slug(company)}.json"
    if path.exists():
        log.info("Demo cache hit for %s (%s)", company, path.name)
        return Brief.model_validate_json(path.read_text(encoding="utf-8"))
    return None


@dataclass
class ScoutInput:
    company_name: str
    founder_name: Optional[str] = None


SYSTEM_PROMPT = """You are a senior VC investment associate at an early-stage AI/dev-tools fund.
You are reviewing inbound deal flow. Given raw web intelligence about a company,
produce a structured investor brief. Follow these rules exactly:

SOURCES
- Populate the `sources` field with every URL that appears in the evidence you actually used.
- Do not leave `sources` empty. If the SERP results include URLs, list them.
- When you state a fact in any field (funding amount, team size, launch date, etc.),
  it must be traceable to one of those URLs.

RED FLAGS
- Only populate `red_flags` when there is concrete evidence of a problem.
- Use `missing_footprint` when the company simply lacks public signal — do NOT
  use `founder_turnover` unless there is actual evidence of a departure or co-founder split.
- Prefer omitting a red flag entirely over raising a speculative one.
- Valid categories: `missing_footprint`, `unverifiable_claim`, `founder_turnover`,
  `revenue_concentration`, `legal_regulatory`, `competitive_moat_risk`.

GENERAL
- Do not fabricate data — if a field is unknown, omit it or mark it null.
- Your recommendation must follow from the evidence; explain your reasoning in 2-3 sentences."""


def build_brief(scout_input: ScoutInput) -> Brief:
    """End-to-end: fetch web intelligence, synthesize a Brief, return it."""
    company = scout_input.company_name
    log.info("Building brief for %s", company)

    if settings.use_demo_cache:
        cached = _load_cache(company)
        if cached is not None:
            return cached

    # 1. Bright Data SERP API — recent news, funding, hiring, launch signals.
    serp_data = serp.search_company(company)

    # 2. Stitch the evidence into a synthesis prompt
    evidence = _format_evidence(company=company, serp_data=serp_data)

    # 3. Ask the LLM to produce a structured Brief
    return complete_structured(
        prompt=evidence,
        schema=Brief,
        system=SYSTEM_PROMPT,
    )


def _format_evidence(company: str, serp_data) -> str:
    """Stitch source outputs into a single prompt body."""
    return (
        f"Company: {company}\n\n"
        f"--- SEARCH RESULTS (Bright Data SERP API) ---\n{serp_data}\n"
    )


def main() -> None:
    """CLI entrypoint: `python -m vc_scout.orchestrator <company name>`"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m vc_scout.orchestrator <company name>")
        sys.exit(1)
    company = " ".join(sys.argv[1:])
    brief = build_brief(ScoutInput(company_name=company))
    print(brief.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
