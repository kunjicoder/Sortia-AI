"""LLM client. Grok primary (via openai SDK + base_url override), Gemini fallback.

We use the openai SDK as the client for Grok because xAI's API is OpenAI-compatible.
This means we get structured output support, retries, and async for free.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Type, TypeVar

from openai import APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

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
    """Plain text completion with one retry on transient errors."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client, default_model = _client()
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=model or default_model,
                messages=messages,
                max_tokens=4096,
                timeout=60,
            )
            return resp.choices[0].message.content or ""
        except (APITimeoutError, RateLimitError) as e:
            if attempt == 0:
                log.warning("LLM transient error (%s), retrying in 3s…", type(e).__name__)
                time.sleep(3)
            else:
                raise RuntimeError(f"LLM unavailable after retry: {e}") from e
        except APIError as e:
            raise RuntimeError(f"LLM API error: {e}") from e
    return ""  # unreachable


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
        log.error("LLM returned non-JSON (first 300 chars): %.300s", raw)
        raise RuntimeError(
            f"LLM returned malformed JSON — try again. Detail: {e}"
        ) from e

    try:
        return schema.model_validate(_coerce_null_lists(data, schema))
    except ValidationError as e:
        log.error("Brief schema validation failed: %s", e)
        raise RuntimeError(
            f"LLM output didn't match expected schema — try again. Detail: {e}"
        ) from e


def _coerce_null_lists(obj, schema: type[BaseModel] | None = None):
    """Recursively replace null list fields with [] so Pydantic List fields don't reject them.

    Only coerces null→[] when the corresponding schema field annotation is list[X].
    Recurses into nested dicts (sub-models) and list items so deeply nested null
    list fields (e.g. FundingRound.investors inside funding_history) are also fixed.
    """
    if isinstance(obj, list):
        return [_coerce_null_lists(item, schema) for item in obj]
    if not isinstance(obj, dict):
        return obj

    import typing
    fields = schema.model_fields if schema is not None else {}
    result = {}
    for k, v in obj.items():
        field = fields.get(k)
        ann = field.annotation if field is not None else None
        origin = getattr(ann, "__origin__", None)

        if v is None and origin is list:
            result[k] = []
            continue

        # Determine the nested schema to pass when recursing
        nested_schema = None
        if ann is not None:
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                nested_schema = ann
            elif origin is list:
                # List[SomeModel] — unwrap the element type
                args = getattr(ann, "__args__", ())
                if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    nested_schema = args[0]

        if isinstance(v, dict):
            result[k] = _coerce_null_lists(v, nested_schema)
        elif isinstance(v, list):
            result[k] = [_coerce_null_lists(item, nested_schema) if isinstance(item, dict) else item for item in v]
        else:
            result[k] = v
    return result
