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

    # Log a redacted view of the endpoint so we can see it's well-formed without
    # leaking the password.
    log.info("Scraping Browser: endpoint=%s", _redact(settings.brightdata_browser_url))

    try:
        text = _fetch(url, settings.brightdata_browser_url)
        log.info("Scraping Browser: OK — %d chars extracted from %s", len(text), url)
        return text
    except ImportError as exc:
        log.error("Scraping Browser: Playwright not installed (%s). Run: pip install playwright", exc)
        return ""
    except Exception as exc:
        # Full traceback + exception type so we can tell a bad endpoint from a
        # navigation timeout from an auth/zone error.
        log.error(
            "Scraping Browser FAILED for %s — %s: %s",
            url, type(exc).__name__, exc,
            exc_info=True,
        )
        return ""


def _fetch(page_url: str, browser_ws_url: str) -> str:
    from playwright.sync_api import sync_playwright

    texts: list[str] = []

    with sync_playwright() as p:
        log.info("Scraping Browser: connecting over CDP…")
        browser = p.chromium.connect_over_cdp(browser_ws_url)
        log.info("Scraping Browser: connected (contexts=%d)", len(browser.contexts))
        try:
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            # Cap all page operations so a stalled CDP session can't hang the pipeline.
            # evaluate() and wait_for_* both respect this limit.
            page.set_default_timeout(12_000)

            # Main page
            # NOTE: use "domcontentloaded", NOT "networkidle". Through the Bright Data
            # Scraping Browser proxy, analytics/long-polling keep the network busy so
            # "networkidle" never fires and goto times out (30s). DOM-ready plus a short
            # settle for client-rendered content is reliable.
            log.info("Scraping Browser: navigating to %s", page_url)
            page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2_500)  # let client-side JS paint
            log.info("Scraping Browser: loaded %s", page.url)
            main_text = _extract_text(page)
            if main_text:
                texts.append(f"[{page_url}]\n{main_text}")

            # Best-effort sub-pages — skip if 404 / redirect off-domain
            base = page_url.rstrip("/")
            for path in _EXTRA_PATHS:
                try:
                    sub_url = base + path
                    resp = page.goto(sub_url, wait_until="domcontentloaded", timeout=12_000)
                    page.wait_for_timeout(1_500)
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


def _redact(ws_url: str) -> str:
    """Mask the password in a wss://user:pass@host endpoint for safe logging."""
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", ws_url)


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


# ── Collector wrapper ────────────────────────────────────────────────────────

class CompanySiteCollector:
    """Collector: Scraping Browser → product / team / pricing signals from site."""
    name = "Scraping Browser"

    def applies_to(self, ctx) -> bool:
        return bool(ctx.domain)

    def collect(self, ctx) -> list:
        from .base import Signal
        url = f"https://{ctx.domain}"
        site_text = fetch_site_text(url)
        if not site_text:
            return []
        # Return one signal carrying the raw text; bundle.py splits it into claims
        return [Signal(
            section="product",
            fact=site_text[:3000],
            url=url,
            source="Scraping Browser",
            trust="low",
            key="site_text",
            value=site_text,
        )]
