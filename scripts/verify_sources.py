"""Verify real GitHub and App Store collector implementations.

Usage:
    python scripts/verify_sources.py

Exits non-zero if any assertion fails.
"""

from __future__ import annotations

import sys
import textwrap

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from vc_scout.sources.github import fetch_repo_signals
from vc_scout.sources.appstore import fetch_app_signals


def _header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _row(label: str, value: object) -> None:
    print(f"  {label:<20} {value}")


def verify_github() -> None:
    _header("GitHub — ollama/ollama (public, high-star repo)")
    data = fetch_repo_signals("https://github.com/ollama/ollama")

    print()
    for k, v in data.items():
        _row(k, v)

    assert data, "fetch_repo_signals returned empty dict"
    assert "stars" in data, f"Missing 'stars' in {list(data)}"
    assert data["stars"] > 0, f"stars={data['stars']} — expected > 0"
    assert "source_url" in data, "Missing 'source_url'"

    print("\n  PASS — GitHub signals verified.")


def verify_appstore() -> None:
    _header("App Store — 'Wispr Flow' (iOS app)")
    data = fetch_app_signals("Wispr Flow")

    print()
    for k, v in data.items():
        _row(k, v)

    assert data, "fetch_app_signals returned empty dict"
    assert "rating" in data or "review_count" in data, (
        f"Expected at least rating or review_count — got {list(data)}"
    )
    if "rating" in data:
        assert 1.0 <= data["rating"] <= 5.0, f"rating={data['rating']} out of range"

    print("\n  PASS — App Store signals verified.")


def print_research_log_sample() -> None:
    """Show what the deterministic research_log looks like for a short collector_log."""
    _header("Research log — deterministic rebuild sample")

    from vc_scout.sources.base import Signal
    from vc_scout.orchestrator import _make_research_steps

    collector_log = [
        {"source": "SERP API",   "examined": "Web search for 'Ollama' (10 results)"},
        {"source": "GitHub",     "examined": "https://github.com/ollama/ollama"},
        {"source": "ATS",        "examined": "No careers URL found"},
    ]
    fake_signals = [
        Signal(section="traction", fact="GitHub: 90,000 stars, 800 contributors", url="https://github.com/ollama/ollama", source="GitHub", trust="high"),
        Signal(section="traction", fact="GitHub: 1,200 open issues", url="https://github.com/ollama/ollama", source="GitHub", trust="high"),
    ]

    steps = _make_research_steps(collector_log, fake_signals)
    print()
    print(f"  {'Source':<18} {'Examined':<35} {'Found'[:50]:<50}")
    print(f"  {'-'*18} {'-'*35} {'-'*50}")
    for step in steps:
        found_preview = textwrap.shorten(step.found, 50, placeholder="…")
        examined_preview = textwrap.shorten(step.examined, 35, placeholder="…")
        print(f"  {step.source:<18} {examined_preview:<35} {found_preview}")

    assert len(steps) == 3, f"Expected 3 steps, got {len(steps)}"
    github_step = next(s for s in steps if s.source == "GitHub")
    assert "stars" in github_step.found.lower() or "signal" in github_step.found.lower(), (
        f"GitHub step found should mention signals: {github_step.found!r}"
    )
    print("\n  PASS — research_log rebuild verified.")


if __name__ == "__main__":
    errors: list[str] = []

    for fn in (verify_github, verify_appstore, print_research_log_sample):
        try:
            fn()
        except AssertionError as e:
            print(f"\n  FAIL: {e}")
            errors.append(str(e))
        except Exception as e:
            print(f"\n  ERROR in {fn.__name__}: {type(e).__name__}: {e}")
            errors.append(f"{fn.__name__}: {e}")

    print()
    if errors:
        print(f"{'=' * 60}")
        print(f"  {len(errors)} check(s) FAILED:")
        for err in errors:
            print(f"    - {err}")
        sys.exit(1)
    else:
        print(f"{'=' * 60}")
        print("  All checks passed.")
