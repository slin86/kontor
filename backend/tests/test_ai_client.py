import json
from typing import Any

import httpx
import pytest

from kontor.core.config import get_settings
from kontor.services import ai

SCHEMA: dict[str, Any] = {"type": "object", "properties": {"x": {"type": "integer"}}}


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTOR_AI_LOCAL_URL", "http://pc.lan:11434/")
    monkeypatch.setenv("KONTOR_AI_LOCAL_MODEL", "qwen")
    monkeypatch.setenv("KONTOR_AI_CLOUD_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _response(payload: dict[str, Any], url: str = "http://x") -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


def test_local_answer_with_json_in_prose(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def post(url: str, **kw: Any) -> httpx.Response:
        seen.update(url=url, body=kw["json"])
        return _response({"choices": [{"message": {"content": 'Hier: ```json\n{"x": 3}\n```'}}]})

    monkeypatch.setattr(httpx, "post", post)
    answer = ai.complete_json("s", "u", SCHEMA)
    assert answer.data == {"x": 3} and answer.via == "local"
    assert seen["url"] == "http://pc.lan:11434/v1/chat/completions"
    assert (
        seen["body"]["model"] == "qwen" and seen["body"]["response_format"]["type"] == "json_schema"
    )


def test_cloud_is_only_used_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTOR_AI_CLOUD_API_KEY", "key")
    get_settings.cache_clear()
    calls: list[str] = []

    def post(url: str, **kw: Any) -> httpx.Response:
        calls.append(url)
        if "pc.lan" in url:
            raise httpx.ConnectError("down")
        return _response({"content": [{"type": "tool_use", "input": {"x": 1}}]})

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(ai.AiUnavailable):
        ai.complete_json("s", "u", SCHEMA, allow_cloud=False)
    assert calls == ["http://pc.lan:11434/v1/chat/completions"]
    answer = ai.complete_json("s", "u", SCHEMA, allow_cloud=True)
    assert answer.data == {"x": 1} and answer.via == "cloud"


def test_nothing_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTOR_AI_LOCAL_URL", "")
    get_settings.cache_clear()
    with pytest.raises(ai.AiUnavailable):
        ai.complete_json("s", "u", SCHEMA, allow_cloud=True)
    assert not ai.status().local_configured


def test_status_reports_an_unreachable_server(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url: str, **kw: Any) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", get)
    s = ai.status()
    assert s.local_configured and not s.local_reachable and s.local_model == "qwen"
    assert json.dumps(s.local_model)
