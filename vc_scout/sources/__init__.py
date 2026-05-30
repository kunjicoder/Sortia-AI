"""Bright Data source integrations — collector registry pattern.

Collector protocol (base.py): applies_to(ctx) -> bool, collect(ctx) -> list[Signal]

Universal collectors (run for every company):
    serp              -> SERP API
    scraping_browser  -> Scraping Browser (CDP/Playwright)
    linkedin          -> Web Scraper API (LinkedIn company)
    ats               -> Scraping Browser (ATS/careers pages)

Adaptive collectors (apply based on company_type or URL presence):
    appstore          -> Scraping Browser (iOS App Store — consumer_app)
    github            -> Scraping Browser (GitHub repo — dev_tool) [STUB]
    reviews           -> Scraping Browser (G2/Capterra — b2b_saas) [STUB]
    glassdoor         -> Scraping Browser (Glassdoor — risks) [STUB, always False]

DEEP-mode only (settings.deep=True):
    linkedin_people   -> Web Scraper API (LinkedIn people — founder pedigree)

Resolver: resolve.py builds EntityContext from SERP results.
Registry: registry.py holds COLLECTORS list; orchestrator imports it.
"""
