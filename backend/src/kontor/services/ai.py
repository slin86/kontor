"""Small client for the AI helper: a local OpenAI-compatible server and an optional cloud fallback.

The local server (Ollama, LM Studio, ...) is the default and the only one that ever sees documents.
The cloud key is a fallback for short texts such as an item name: callers opt in per request with
``allow_cloud``. Both ask for JSON that matches a schema, so callers never parse prose.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from kontor.core.config import get_settings

CLOUD_URL = "https://api.anthropic.com/v1/messages"
CLOUD_VERSION = "2023-06-01"


class AiUnavailable(RuntimeError):
    """No configured AI server could answer."""


@dataclass(frozen=True)
class AiAnswer:
    data: dict[str, Any]
    via: Literal["local", "cloud"]


@dataclass(frozen=True)
class AiStatus:
    local_configured: bool
    local_reachable: bool
    local_model: str | None
    cloud_configured: bool


def _local_base() -> str:
    return get_settings().ai_local_url.rstrip("/")


def status() -> AiStatus:
    s = get_settings()
    reachable = False
    if _local_base():
        try:
            r = httpx.get(f"{_local_base()}/v1/models", timeout=httpx.Timeout(2.0))
            reachable = r.is_success
        except httpx.HTTPError:
            reachable = False
    return AiStatus(
        local_configured=bool(_local_base()),
        local_reachable=reachable,
        local_model=s.ai_local_model or None,
        cloud_configured=bool(s.ai_cloud_api_key),
    )


def _json_from_text(text: str) -> dict[str, Any]:
    """Models sometimes wrap the JSON in prose or code fences; take the outermost object."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Die KI hat kein JSON-Objekt geliefert.")
    return value


def _local(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    body = {
        "model": s.ai_local_model,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": True, "schema": schema},
        },
    }
    timeout = httpx.Timeout(s.ai_local_timeout_seconds, connect=3.0)
    r = httpx.post(f"{_local_base()}/v1/chat/completions", json=body, timeout=timeout)
    r.raise_for_status()
    content: str = r.json()["choices"][0]["message"]["content"]
    return _json_from_text(content)


def _cloud(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    body = {
        "model": s.ai_cloud_model,
        "max_tokens": 1024,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "tools": [{"name": "answer", "description": "Antwort", "input_schema": schema}],
        "tool_choice": {"type": "tool", "name": "answer"},
    }
    headers = {"x-api-key": s.ai_cloud_api_key, "anthropic-version": CLOUD_VERSION}
    r = httpx.post(CLOUD_URL, json=body, headers=headers, timeout=httpx.Timeout(30.0, connect=5.0))
    r.raise_for_status()
    for block in r.json().get("content", []):
        if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            result: dict[str, Any] = block["input"]
            return result
    raise ValueError("Die Cloud-KI hat keine strukturierte Antwort geliefert.")


def complete_json(
    system: str, user: str, schema: dict[str, Any], *, allow_cloud: bool = False
) -> AiAnswer:
    """Ask for a JSON answer; local server first, cloud only when ``allow_cloud`` and configured."""
    s = get_settings()
    errors: list[str] = []
    if _local_base() and s.ai_local_model:
        try:
            return AiAnswer(_local(system, user, schema), "local")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            errors.append(f"lokal: {exc}")
    if allow_cloud and s.ai_cloud_api_key:
        try:
            return AiAnswer(_cloud(system, user, schema), "cloud")
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"Cloud: {exc}")
    raise AiUnavailable("; ".join(errors) or "Keine KI konfiguriert.")
