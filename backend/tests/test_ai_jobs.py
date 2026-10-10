import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kontor.core.config import get_settings
from tests.test_ai_api import FakeAi, _b64, _pdf, fake  # noqa: F401

STATEMENT = "Kontoauszug August und September 2026 " * 6


def _wait(client: TestClient, job_id: str, *states: str) -> dict[str, Any]:
    for _ in range(200):
        body = client.get(f"/api/ai/jobs/{job_id}").json()
        if body["status"] in states:
            return body  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError(f"job stuck in {body['status']}")


def _start(client: TestClient, kind: str, raw: bytes, **extra: Any) -> dict[str, Any]:
    r = client.post(
        "/api/ai/jobs",
        json={"kind": kind, "filename": "x.pdf", "content_base64": _b64(raw), **extra},
    )
    assert r.status_code == 202, r.text
    return r.json()  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def _quick_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTOR_AI_WAIT_MINUTES", "1")
    monkeypatch.setenv("KONTOR_AI_RETRY_SECONDS", "1")
    get_settings.cache_clear()


def test_statement_job_runs_in_the_background_and_keeps_its_result(
    client: TestClient,
    fake: FakeAi,  # noqa: F811
) -> None:
    fake.pdf_lines = [
        {"date": "2026-08-05", "amount": -12.99, "counterparty": "Netflix", "purpose": "Abo"},
        {"date": "2026-09-05", "amount": -12.99, "counterparty": "Netflix", "purpose": "Abo"},
    ]
    job = _start(client, "statement", _pdf(STATEMENT))
    assert job["status"] in ("queued", "running", "done")
    assert "result" not in job  # the list never carries the payload
    done = _wait(client, job["id"], "done", "failed")
    assert done["status"] == "done", done
    assert done["result"]["candidates"][0]["name"] == "Netflix"
    assert [j["id"] for j in client.get("/api/ai/jobs").json()] == [job["id"]]
    assert client.delete(f"/api/ai/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/ai/jobs/{job['id']}").status_code == 404
    assert client.get("/api/ai/jobs").json() == []


def test_job_reports_why_a_document_cannot_be_used(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.doc_kind = "loan_contract"
    job = _start(client, "statement", _pdf("Darlehensvertrag " * 10))
    failed = _wait(client, job["id"], "failed", "done")
    assert failed["status"] == "failed" and "Finanzierungen" in failed["error"]


def test_job_waits_for_a_sleeping_ai_machine(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    fake.down = True
    job = _start(client, "statement", _pdf(STATEMENT))
    assert _wait(client, job["id"], "waiting")["status"] == "waiting"
    fake.down = False  # the machine has woken up and loaded its model
    fake.pdf_lines = [
        {"date": "2026-08-05", "amount": -12.99, "counterparty": "Netflix", "purpose": "Abo"},
        {"date": "2026-09-05", "amount": -12.99, "counterparty": "Netflix", "purpose": "Abo"},
    ]
    assert _wait(client, job["id"], "done", "failed")["status"] == "done"


def test_jobs_belong_to_their_owner(client: TestClient, fake: FakeAi) -> None:  # noqa: F811
    job = _start(client, "contract", _pdf(STATEMENT))
    _wait(client, job["id"], "done", "failed")
    other = TestClient(client.app)
    assert other.get(f"/api/ai/jobs/{job['id']}").status_code == 401
    assert (
        client.post(
            "/api/ai/jobs", json={"kind": "depot", "filename": "a", "content_base64": "###"}
        ).status_code
        == 422
    )
