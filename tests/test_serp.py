"""Unit tests for sources/serp.py _parse_serp_response.

No live API calls — all fixtures are inline dicts.
"""

from __future__ import annotations

import json

import pytest

from vc_scout.sources.serp import _parse_serp_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_organic_item(title="Acme raises $5M", url="https://tc.com/acme", desc="Big news"):
    return {"title": title, "link": url, "description": desc}


def _make_news_item(title="Acme launches v2", url="https://news.com/acme", desc="Launch"):
    return {"name": title, "href": url, "snippet": desc}


# ---------------------------------------------------------------------------
# Organic results
# ---------------------------------------------------------------------------

def test_organic_results_parsed():
    raw = {"organic": [_make_organic_item()]}
    results = _parse_serp_response(raw)
    assert len(results) == 1
    assert results[0]["title"] == "Acme raises $5M"
    assert results[0]["url"] == "https://tc.com/acme"
    assert results[0]["description"] == "Big news"
    assert results[0]["source"] == "organic"


def test_organic_results_multiple():
    raw = {"organic": [_make_organic_item(title=f"Item {i}", url=f"https://x.com/{i}") for i in range(5)]}
    assert len(_parse_serp_response(raw)) == 5


# ---------------------------------------------------------------------------
# News results
# ---------------------------------------------------------------------------

def test_news_results_parsed():
    raw = {"news": [_make_news_item()]}
    results = _parse_serp_response(raw)
    assert len(results) == 1
    assert results[0]["title"] == "Acme launches v2"
    assert results[0]["url"] == "https://news.com/acme"
    assert results[0]["source"] == "news"


def test_organic_and_news_combined():
    raw = {
        "organic": [_make_organic_item()],
        "news": [_make_news_item()],
    }
    results = _parse_serp_response(raw)
    assert len(results) == 2
    sources = {r["source"] for r in results}
    assert sources == {"organic", "news"}


# ---------------------------------------------------------------------------
# Alternate section names (organic_results / news_results)
# ---------------------------------------------------------------------------

def test_organic_results_key():
    raw = {"organic_results": [_make_organic_item(url="https://alt.com/1")]}
    results = _parse_serp_response(raw)
    assert len(results) == 1
    assert results[0]["url"] == "https://alt.com/1"
    assert results[0]["source"] == "organic_results"


def test_news_results_key():
    raw = {"news_results": [_make_news_item(url="https://alt.com/2")]}
    results = _parse_serp_response(raw)
    assert len(results) == 1
    assert results[0]["source"] == "news_results"


# ---------------------------------------------------------------------------
# Wrapped {"body": "<json string>"} shape
# ---------------------------------------------------------------------------

def test_wrapped_body_string_parsed():
    inner = {"organic": [_make_organic_item(title="Wrapped result", url="https://wrap.com/1")]}
    raw = {"body": json.dumps(inner)}
    results = _parse_serp_response(raw)
    assert len(results) == 1
    assert results[0]["title"] == "Wrapped result"


def test_wrapped_body_invalid_json_returns_empty():
    raw = {"body": "not valid json {{{{"}
    assert _parse_serp_response(raw) == []


# ---------------------------------------------------------------------------
# Empty / garbage input
# ---------------------------------------------------------------------------

def test_empty_dict_returns_empty():
    assert _parse_serp_response({}) == []


def test_none_sections_skipped():
    raw = {"organic": None, "news": None}
    assert _parse_serp_response(raw) == []


def test_non_dict_top_level_returns_empty():
    assert _parse_serp_response([]) == []
    assert _parse_serp_response("garbage") == []
    assert _parse_serp_response(None) == []


def test_non_dict_items_in_section_skipped():
    raw = {"organic": ["not a dict", 42, None, _make_organic_item()]}
    results = _parse_serp_response(raw)
    assert len(results) == 1


def test_missing_fields_return_empty_strings():
    raw = {"organic": [{}]}
    results = _parse_serp_response(raw)
    assert len(results) == 1
    assert results[0]["title"] == ""
    assert results[0]["url"] == ""
    assert results[0]["description"] == ""
