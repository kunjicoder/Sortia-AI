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


def _client() -> tuple[OpenAI, str]:
    """Return (client, default_model) for the configured provider.

    Both Grok (xAI) and AI/ML API are OpenAI-compatible, so the same SDK
    works for both — we just swap api_key, base_url, and the default model.
    """
    if settings.llm_provider == "grok":
        if not settings.grok_api_key:
            raise RuntimeError(
                "GROK_API_KEY is missing. Copy .env.example to .env and fill it in."
            )
        return (
            OpenAI(api_key=settings.grok_api_key, base_url=settings.grok_base_url),
            settings.grok_model,
        )

    # Default: AI/ML API (partner).
    if not settings.aiml_api_key:
        raise RuntimeError(
            "AIML_API_KEY is missing. Copy .env.example to .env and fill it in "
            "(or set LLM_PROVIDER=grok to use Grok)."
        )
    return (
        OpenAI(api_key=settings.aiml_api_key, base_url=settings.aiml_base_url),
        settings.aiml_model,
    )


def complete(prompt: str, system: str = "", model: str | None = None) -> str:
    """Plain text completion. Returns the assistant's reply as a string."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client, default_model = _client()
    resp = client.chat.completions.create(
        model=model or default_model,
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

    return schema.model_validate(_coerce_null_lists(data, schema))


def _coerce_null_lists(obj, schema: type[BaseModel] | None = None):
    """Recursively replace null list fields with [] so Pydantic List fields don't reject them.

    Only coerces to [] when the corresponding schema field is typed as a list
    (not Optional[int] etc.), avoiding clobbering genuinely nullable scalars.
    """
    if not isinstance(obj, dict):
        return obj

    fields = schema.model_fields if schema is not None else {}
    result = {}
    for k, v in obj.items():
        field = fields.get(k)
        if v is None and field is not None:
            ann = field.annotation
            origin = getattr(ann, "__origin__", None)
            # list or List[X] — null → []
            if origin is list:
                result[k] = []
                continue
        # recurse into nested dicts with the nested schema if available
        nested_schema = None
        if field is not None and isinstance(v, dict):
            ann = field.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                nested_schema = ann
        result[k] = _coerce_null_lists(v, nested_schema) if isinstance(v, dict) else v
    return result
