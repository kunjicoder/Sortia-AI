"""Bake a live pipeline run into the demo cache.

Usage:
    python scripts/bake_cache.py "Wispr Flow"
    python scripts/bake_cache.py "GodHands"

Writes vc_scout/demo_cache/<slug>.json (UTF-8, no ASCII escaping).
USE_DEMO_CACHE must be unset or false so we hit the live pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

# Make sure imports resolve whether run from repo root or scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from vc_scout.orchestrator import ScoutInput, build_brief  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bake_cache")

_CACHE_DIR = Path(__file__).parent.parent / "vc_scout" / "demo_cache"


def _slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def bake(company: str) -> None:
    from vc_scout.config import settings
    if settings.use_demo_cache:
        log.warning(
            "USE_DEMO_CACHE=true — bake_cache would just re-read the cache. "
            "Set USE_DEMO_CACHE=false (or unset) to run the live pipeline."
        )
        sys.exit(1)

    log.info("Running live pipeline for: %s", company)
    result = build_brief(ScoutInput(company_name=company))

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _CACHE_DIR / f"{_slug(company)}.json"

    payload = json.loads(result.memo.model_dump_json())
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log.info("Written %s (%d bytes)", out_path.name, out_path.stat().st_size)
    log.info("Stats: %s", result.stats_line())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/bake_cache.py <company name>")
        sys.exit(1)
    bake(" ".join(sys.argv[1:]))
