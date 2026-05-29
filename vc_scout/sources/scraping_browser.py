"""Bright Data Scraping Browser source.

Connects via Playwright connect_over_cdp to the Bright Data Scraping Browser
endpoint (settings.brightdata_browser_url). Fetches a company's site text for
claim extraction.

Degrades to "" if BRIGHTDATA_BROWSER_URL is unset or the connection fails.
The rest of the pipeline continues on SERP-only in that case.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

_TRUNCATE_CHARS = 5000

_BOILERPLATE_RE = re.compile(
    r"(cookie[s]?\s+policy|privacy\s+policy|terms\s+(of\s+service|and\s+conditions)"
    r"|©\s*\d{4}|all\s+rights\s+reserved|sign\s+(in|up)|log\s+in|subscribe)",
    re.IGNORECASE,
)

# Sub-pages worth fetching for pricing/team/product depth
_EXTRA_PATHS = ("/about", "/pricing", "/product", "/features")


def fetch_site_text(url: str) -> str:
    """Return visible text from the company site via Bright Data Scraping Browser.

    Tries the homepage plus /about and /pricing. Returns "" on any failure.
    """
    from ..config import settings

    if not settings.brightdata_browser_url:
        log.warning("BRIGHTDATA_BROWSER_URL not set — skipping Scraping Browser fetch")
        return ""

    try:
        return _fetch(url, settings.brightdata_browser_url)
    except Exception as exc:
        log.warning("Scraping Browser failed for %s: %s", url, exc)
        return ""


def _fetch(page_url: str, browser_ws_url: str) -> str:
    from playwright.sync_api import sync_playwright

    texts: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(browser_ws_url)
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()

            # Main page
            page.goto(page_url, wait_until="networkidle", timeout=30_000)
            main_text = _extract_text(page)
            if main_text:
                texts.append(f"[{page_url}]\n{main_text}")

            # Best-effort sub-pages — skip if 404 / redirect off-domain
            base = page_url.rstrip("/")
            for path in _EXTRA_PATHS:
                try:
                    sub_url = base + path
                    resp = page.goto(sub_url, wait_until="networkidle", timeout=15_000)
                    # Only keep if we stayed on the same domain
                    if resp and resp.ok and _same_domain(page.url, page_url):
                        sub_text = _extract_text(page)
                        if sub_text:
                            texts.append(f"[{sub_url}]\n{sub_text}")
                except Exception:
                    pass

            page.close()
        finally:
            browser.close()

    combined = "\n\n---\n\n".join(texts)
    return _clean_and_truncate(combined)


def _extract_text(page) -> str:
    """Extract visible body text, excluding nav/header/footer/scripts."""
    return page.evaluate("""() => {
        const dead = ['nav','header','footer','script','style','noscript',
                      '[class*="cookie"]','[class*="banner"]','[id*="cookie"]',
                      '[aria-hidden="true"]'];
        dead.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => el.remove());
        });
        return document.body ? document.body.innerText.trim() : '';
    }""")


def _same_domain(url_a: str, url_b: str) -> bool:
    """Rough check: both URLs share the same netloc."""
    from urllib.parse import urlparse
    return urlparse(url_a).netloc == urlparse(url_b).netloc


def _clean_and_truncate(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not _BOILERPLATE_RE.search(line)
    ]
    return "\n".join(lines)[:_TRUNCATE_CHARS]
