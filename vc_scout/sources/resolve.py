"""Resolver: build EntityContext from a company name + initial SERP results.

Called once at the start of build_brief. Extracts all discoverable entity
metadata (domain, LinkedIn company URL, people URLs, careers URL, GitHub URL,
App Store/Play Store URLs) and classifies company type.

Company-type classification uses a domain/keyword heuristic:
  dev_tool     — github.com result, keywords: "open-source", "developer", "SDK", "API", "CLI"
  consumer_app — app store result, keywords: "app", "ios", "android", "download"
  b2b_saas     — g2/capterra result, keywords: "enterprise", "pricing", "integrations", "SaaS"
  unknown      — fallback

Classification is intentionally cheap — no LLM call on this path.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from .base import EntityContext

log = logging.getLogger(__name__)

_DIRECTORY_DOMAINS = {
    "crunchbase.com", "linkedin.com", "techcrunch.com", "forbes.com",
    "bloomberg.com", "reuters.com", "wsj.com", "ycombinator.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "github.com", "wikipedia.org", "glassdoor.com", "pitchbook.com",
    "g2.com", "capterra.com", "producthunt.com", "apps.apple.com",
    "play.google.com", "ashbyhq.com", "greenhouse.io", "lever.co",
}

_ATS_RE = re.compile(r"(ashbyhq\.com|greenhouse\.io|lever\.co|jobs\.[a-z0-9-]+\.|/careers)", re.I)
_GITHUB_RE = re.compile(r"github\.com/[^/]+/[^/?]+", re.I)
_APPSTORE_RE = re.compile(r"apps\.apple\.com", re.I)
_PLAYSTORE_RE = re.compile(r"play\.google\.com/store", re.I)
_LINKEDIN_COMPANY_RE = re.compile(r"linkedin\.com/company/", re.I)
_LINKEDIN_PEOPLE_RE = re.compile(r"linkedin\.com/in/", re.I)

_DEV_KEYWORDS = re.compile(
    r"\b(open.?source|developer|sdk|api\b|cli\b|library|package|framework|repo|"
    r"contributors?|github|npm|pypi|cargo|brew)\b", re.I)
_CONSUMER_KEYWORDS = re.compile(
    r"\b(app\b|ios|android|download|install|mobile|app store|google play|"
    r"users?|subscribers?|downloads?)\b", re.I)
_B2B_KEYWORDS = re.compile(
    r"\b(enterprise|b2b|saas|pricing|integrations?|dashboard|workflow|crm|"
    r"platform|customers?|g2|capterra|salesforce)\b", re.I)


def resolve(company: str, serp_results: list[dict]) -> EntityContext:
    """Build EntityContext from SERP results for a company name."""
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    ctx = EntityContext(company=company, serp_results=serp_results)

    for item in serp_results:
        url = item.get("url", "")
        if not url:
            continue
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().removeprefix("www.")

        # Company domain — first non-directory result that slug-matches
        if not ctx.domain and netloc not in _DIRECTORY_DOMAINS:
            if slug in netloc.replace(".", "").replace("-", ""):
                ctx.domain = netloc
            elif not ctx.domain:
                ctx.domain = netloc  # best fallback (set once, keep first)

        # LinkedIn company
        if not ctx.linkedin_company_url and _LINKEDIN_COMPANY_RE.search(url):
            ctx.linkedin_company_url = url.split("?")[0]

        # LinkedIn people
        if _LINKEDIN_PEOPLE_RE.search(url):
            clean = url.split("?")[0]
            if clean not in ctx.linkedin_people_urls:
                ctx.linkedin_people_urls.append(clean)

        # Careers / ATS
        if not ctx.careers_url and _ATS_RE.search(url):
            ctx.careers_url = url.split("?")[0]

        # GitHub
        if not ctx.github_url and _GITHUB_RE.search(url):
            m = _GITHUB_RE.search(url)
            if m:
                ctx.github_url = f"https://{m.group(0).rstrip('/')}"

        # App Store / Play Store
        if not ctx.appstore_url and _APPSTORE_RE.search(url):
            ctx.appstore_url = url.split("?")[0]
        if not ctx.playstore_url and _PLAYSTORE_RE.search(url):
            ctx.playstore_url = url.split("?")[0]

    # Fix domain: ensure we didn't accidentally grab a directory domain
    if ctx.domain and any(ctx.domain.endswith(d) for d in _DIRECTORY_DOMAINS):
        ctx.domain = ""

    ctx.company_type = _classify(serp_results, ctx)
    log.info(
        "Resolved '%s': domain=%s type=%s linkedin=%s github=%s appstore=%s careers=%s "
        "people_urls=%d",
        company, ctx.domain, ctx.company_type,
        bool(ctx.linkedin_company_url), bool(ctx.github_url),
        bool(ctx.appstore_url), bool(ctx.careers_url),
        len(ctx.linkedin_people_urls),
    )
    return ctx


def _classify(results: list[dict], ctx: EntityContext) -> str:
    """Cheap heuristic: classify company type from SERP domains + snippets."""
    # Hard domain signals
    if ctx.github_url:
        return "dev_tool"
    if ctx.appstore_url or ctx.playstore_url:
        return "consumer_app"

    # Keyword scan across snippets
    dev_score = consumer_score = b2b_score = 0
    for item in results:
        text = f"{item.get('title', '')} {item.get('description', '')} {item.get('url', '')}"
        dev_score += len(_DEV_KEYWORDS.findall(text))
        consumer_score += len(_CONSUMER_KEYWORDS.findall(text))
        b2b_score += len(_B2B_KEYWORDS.findall(text))

    best = max(dev_score, consumer_score, b2b_score)
    if best == 0:
        return "unknown"
    if dev_score == best:
        return "dev_tool"
    if consumer_score == best:
        return "consumer_app"
    return "b2b_saas"
