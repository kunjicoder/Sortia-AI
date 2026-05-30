"""GitHub REST API collector — dev-tool traction signals.

Adaptive: applies_to() returns True when company_type=dev_tool AND ctx.github_url is present.
Uses the public GitHub REST API (no auth required; GITHUB_TOKEN raises rate limit 60→5000/h).

Signals emitted (section="traction", trust="high" — GitHub's own data, not self-reported):
  - Stars, contributors, last commit date (adoption + activity proxy)
  - Open issues count (community size proxy)

API endpoints used:
  GET /repos/{owner}/{repo}                   → stars, forks, open_issues, language
  GET /repos/{owner}/{repo}/commits?per_page=1 → last commit ISO date
  GET /repos/{owner}/{repo}/contributors?per_page=1 → contributor count from Link header

Degrades to [] if github_url is missing, repo not found, or any request fails.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from ..config import settings
from .base import EntityContext, Signal

log = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_REPO_PATH_RE = re.compile(r"github\.com/([^/]+)/([^/?#\s]+)", re.I)
_TIMEOUT = 15


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github.v3+json", "User-Agent": "vc-scout/1.0"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


def _parse_owner_repo(github_url: str) -> tuple[str, str] | None:
    m = _REPO_PATH_RE.search(github_url)
    if not m:
        return None
    owner = m.group(1).strip()
    repo = m.group(2).strip().removesuffix(".git")
    if not owner or not repo:
        return None
    return owner, repo


def fetch_repo_signals(github_url: str) -> dict[str, Any]:
    """Return GitHub repo metrics, or {} on any failure.

    Output keys (only present fields included):
      stars, forks, open_issues, language, contributors, last_commit, source_url
    """
    if not github_url:
        return {}

    parsed = _parse_owner_repo(github_url)
    if not parsed:
        log.warning("GitHub: could not parse owner/repo from %s", github_url)
        return {}
    owner, repo = parsed
    h = _headers()

    try:
        # ── 1. Repo info ─────────────────────────────────────────────────────
        resp = requests.get(f"{_API_BASE}/repos/{owner}/{repo}", headers=h, timeout=_TIMEOUT)
        if not resp.ok:
            log.warning("GitHub: /repos/%s/%s returned %d", owner, repo, resp.status_code)
            return {}
        data = resp.json()
        out: dict[str, Any] = {
            "source_url": f"https://github.com/{owner}/{repo}",
        }
        if data.get("stargazers_count") is not None:
            out["stars"] = int(data["stargazers_count"])
        if data.get("forks_count") is not None:
            out["forks"] = int(data["forks_count"])
        if data.get("open_issues_count") is not None:
            out["open_issues"] = int(data["open_issues_count"])
        if data.get("language"):
            out["language"] = data["language"]

        # ── 2. Last commit date ───────────────────────────────────────────────
        try:
            cr = requests.get(
                f"{_API_BASE}/repos/{owner}/{repo}/commits",
                headers=h, params={"per_page": 1}, timeout=_TIMEOUT,
            )
            if cr.ok:
                commits = cr.json()
                if isinstance(commits, list) and commits:
                    date_str = (
                        commits[0].get("commit", {})
                        .get("committer", {})
                        .get("date", "")
                    )
                    if date_str:
                        out["last_commit"] = date_str[:10]  # YYYY-MM-DD
        except Exception:
            pass  # last_commit is optional

        # ── 3. Contributor count (from Link header) ───────────────────────────
        try:
            contr = requests.get(
                f"{_API_BASE}/repos/{owner}/{repo}/contributors",
                headers=h, params={"per_page": 1, "anon": "true"}, timeout=_TIMEOUT,
            )
            if contr.ok:
                link = contr.headers.get("Link", "")
                m = re.search(r'page=(\d+)>;\s*rel="last"', link)
                if m:
                    out["contributors"] = int(m.group(1))
                elif isinstance(contr.json(), list):
                    # Repos with ≤1 contributor have no Link header
                    out["contributors"] = len(contr.json())
        except Exception:
            pass  # contributors is optional

        log.info("GitHub: %s/%s — stars=%s contributors=%s last_commit=%s",
                 owner, repo,
                 out.get("stars"), out.get("contributors"), out.get("last_commit"))
        return out

    except Exception as exc:
        log.error("GitHub fetch FAILED for %s — %s: %s", github_url, type(exc).__name__, exc)
        return {}


# ── Collector wrapper ────────────────────────────────────────────────────────

class GitHubCollector:
    """Collector: GitHub repo signals (stars, contributors, commit cadence).

    Adaptive: applies_to() requires BOTH company_type=dev_tool AND a resolved github_url.
    Signals are trust="high" — GitHub's own platform data, not self-reported by the company.
    """
    name = "GitHub"

    def applies_to(self, ctx: EntityContext) -> bool:
        return ctx.company_type == "dev_tool" and bool(ctx.github_url)

    def collect(self, ctx: EntityContext) -> list[Signal]:
        data = fetch_repo_signals(ctx.github_url)
        if not data:
            return []

        url = data["source_url"]
        signals: list[Signal] = []

        # Primary traction signal — stars + contributors + last commit
        parts: list[str] = []
        if "stars" in data:
            parts.append(f"{data['stars']:,} stars")
        if "contributors" in data:
            parts.append(f"{data['contributors']:,} contributors")
        if "last_commit" in data:
            parts.append(f"last commit {data['last_commit']}")
        if "language" in data:
            parts.append(f"primary language: {data['language']}")

        if parts:
            signals.append(Signal(
                section="traction",
                fact=f"GitHub: {', '.join(parts)} (independent adoption proxy).",
                url=url, source="GitHub", trust="high",
                key="github_traction", value=data,
            ))

        # Open issues as a community-size proxy
        if "open_issues" in data:
            signals.append(Signal(
                section="traction",
                fact=f"GitHub: {data['open_issues']:,} open issues — proxy for community size.",
                url=url, source="GitHub", trust="high",
                key="open_issues", value=data["open_issues"],
            ))

        log.info("GitHub collector: emitted %d signals from %s", len(signals), url)
        return signals
