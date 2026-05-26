"""LLM client. Grok primary (via openai SDK + base_url override), Gemini fallback.

We use the openai SDK as the client for Grok because xAI's API is OpenAI-compatible.
This means we get structured output support, retries, and async for free.
"""

from __future__ import annotations

import json
import logging
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _client() -> OpenAI:
    if not settings.grok_api_key:
        raise RuntimeError(
            "GROK_API_KEY is missing. Copy .env.example to .env and fill it in."
        )
    return OpenAI(api_key=settings.grok_api_key, base_url=settings.grok_base_url)


def complete(prompt: str, system: str = "", model: str | None = None) -> str:
    """Plain text completion. Returns the assistant's reply as a string."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = _client().chat.completions.create(
        model=model or settings.grok_model,
        messages=messages,
    )
    return resp.choices[0].message.content or ""


def complete_structured(
    prompt: str,
    schema: Type[T],
    system: str = "",
    model: str | None = None,
) -> T:
    """Structured completion. Asks the LLM for JSON matching `schema` and validates."""
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    system_with_schema = (
        f"{system}\n\nRespond with valid JSON only, matching this schema:\n{schema_json}"
    ).strip()

    raw = complete(prompt, system=system_with_schema, model=model)
    # Strip code fences if the model wraps the JSON
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("LLM returned non-JSON: %s", raw[:500])
        raise RuntimeError(f"LLM did not return valid JSON: {e}") from e

    return schema.model_validate(data)
