import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kontor.core.clock import current_month, format_month
from kontor.services import ai
from tests.test_statements import CSV

PASSWORD = "correct-horse-battery"


def _login(client: TestClient, email: str = "nils@example.com") -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Nils",
            "household_name": f"Haushalt {email}",
        },
    )
    assert r.status_code == 201, r.text
    client.headers["X-CSRF-Token"] = client.cookies.get("kontor_csrf") or ""


def _categories(client: TestClient) -> dict[str, int]:
    return {c["name"]: c["id"] for c in client.get("/api/categories").json()}


def _b64(text: str | bytes) -> str:
    raw = text.encode() if isinstance(text, str) else text
    return base64.b64encode(raw).decode()


def _pdf(text: str) -> bytes:
    """A one-page PDF with a text layer, small enough to write by hand."""
    stream = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET" if text else ""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


class FakeAi:
    """Stands in for the AI server: answers by the shape of the schema it is asked for."""

    def __init__(self, cats: dict[str, int]) -> None:
        self.cats = cats
        self.calls: list[dict[str, Any]] = []
        self.down = False
        self.pdf_lines: list[dict[str, Any]] = []
        self.doc_kind = "bank_statement"
        # answers by the name of the schema's first property, for the document endpoints
        self.answers: dict[str, dict[str, Any]] = {}

    def __call__(
        self, system: str, user: str, schema: dict[str, Any], *, allow_cloud: bool = False
    ) -> ai.AiAnswer:
        self.calls.append({"user": user, "allow_cloud": allow_cloud})
        if self.down:
            raise ai.AiUnavailable("aus")
        props = schema["properties"]
        if "kind" in props and len(props) == 1:
            return ai.AiAnswer({"kind": self.doc_kind}, "local")
        first = next(iter(props))
        if first in self.answers:
            return ai.AiAnswer(self.answers[first], "local")
        if "lines" in props:
            return ai.AiAnswer({"lines": self.pdf_lines}, "local")
        if "items" in props:
            rows = []
            for line in user.split("Zahlungen:\n")[1].splitlines():
                index = int(line.split(":", 1)[0])
                if "Netflix" in line:
                    rows.append(self._row(index, "Abos", 1, "Streaming-Abo"))
                elif "Shell" in line:
                    rows.append(self._row(index, None, 0, "Tankstelle"))
                elif "Fitness" in line:
                    rows.append(self._row(index, "Freizeit und Urlaub", 1, "Studio-Beitrag"))
                else:
                    rows.append(self._row(index, 99999, 1, "falsche Kategorie"))
            return ai.AiAnswer({"items": rows}, "local")
        name = user.rsplit("Posten: ", 1)[1]
        category = "Abos" if "Spotify" in name else "Lebensmittel"
        return ai.AiAnswer(
            {
                "category_id": self.cats[category],
                "recurring": "Spotify" in name,
                "months": 1 if "Spotify" in name else 0,
                "reason": "Test",
            },
            "cloud" if allow_cloud else "local",
        )

    def _row(
        self, index: int, category: str | int | None, months: int, reason: str
    ) -> dict[str, Any]:
        cid = self.cats[category] if isinstance(category, str) else category
        return {
            "index": index,
            "category_id": cid,
            "recurring": months > 0,
            "months": months,
            "reason": reason,
        }


@pytest.fixture
def fake(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> FakeAi:
    _login(client)
    f = FakeAi(_categories(client))
    monkeypatch.setattr("kontor.api.ai.ai.complete_json", f)
    return f


def test_status_without_configuration(client: TestClient) -> None:
    _login(client)
    body = client.get("/api/ai/status").json()
    assert body == {
        "local_configured": False,
        "local_reachable": False,
        "local_model": None,
        "cloud_configured": False,
    }


def test_suggest_uses_the_ai_and_validates_the_category(client: TestClient, fake: FakeAi) -> None:
    r = client.post("/api/ai/suggest", json={"name": "Spotify Premium"}).json()
    assert r["category_id"] == fake.cats["Abos"] and r["recurring"] is True
    assert r["frequency"] == "monthly" and r["source"] == "cloud"
    r = client.post("/api/ai/suggest", json={"name": "Wocheneinkauf"}).json()
    assert r["recurring"] is False and r["frequency"] is None
    # income items only offer income categories
    fake.cats["Lebensmittel"] = fake.cats["Abos"]
    r = client.post("/api/ai/suggest", json={"name": "Wocheneinkauf", "income": True}).json()
    assert r["category_id"] is None


def test_suggest_prefers_an_existing_item(client: TestClient, fake: FakeAi) -> None:
    client.post(
        "/api/cashflow/items",
        json={
            "name": "Netflix",
            "category_id": fake.cats["Abos"],
            "amount": "13",
            "valid_from": format_month(current_month()),
        },
    )
    r = client.post("/api/ai/suggest", json={"name": "netflix"}).json()
    assert r["source"] == "existing" and r["category_id"] == fake.cats["Abos"]
    assert not any("Netflix" in c["user"] for c in fake.calls)


def test_suggest_without_ai_still_answers(client: TestClient, fake: FakeAi) -> None:
    fake.down = True
    r = client.post("/api/ai/suggest", json={"name": "Spotify"}).json()
    assert r["source"] == "none" and r["category_id"] is None


def test_statement_analysis_finds_recurring_payments(client: TestClient, fake: FakeAi) -> None:
    client.post(
        "/api/cashflow/items",
        json={
            "name": "Stadtwerke",
            "category_id": fake.cats["Strom und Gas"],
            "amount": "80",
            "valid_from": format_month(current_month()),
        },
    )
    body = client.post(
        "/api/ai/statements/analyze", json={"filename": "a.csv", "content_base64": _b64(CSV)}
    ).json()
    assert body["format"] == "csv" and body["lines"] == 8 and body["ai"]["used"] is True
    by_name = {c["name"]: c for c in body["candidates"]}
    netflix = by_name["Netflix International B.V."]
    assert netflix["source"] == "pattern" and netflix["frequency"] == "monthly"
    assert netflix["category_id"] == fake.cats["Abos"] and netflix["reason"] == "Streaming-Abo"
    # an unknown category from the model is dropped instead of trusted
    assert by_name["Arbeitgeber GmbH"]["category_id"] is None
    # known item: reused category and a marker so the UI can skip it
    assert by_name["Stadtwerke"]["existing_item_id"] is not None
    assert by_name["Stadtwerke"]["category_id"] == fake.cats["Strom und Gas"]
    # a single payment (Tankstelle) that the AI calls one-off does not show up
    assert "Shell Tankstelle 4711" not in by_name
    # nothing leaves for the cloud
    assert all(c["allow_cloud"] is False for c in fake.calls)


def test_single_payment_judged_recurring_by_the_ai(client: TestClient, fake: FakeAi) -> None:
    csv = "Buchungstag;Name;Verwendungszweck;Betrag\n03.10.2026;Fitness First;Beitrag;-29,90\n"
    body = client.post(
        "/api/ai/statements/analyze", json={"filename": "a.csv", "content_base64": _b64(csv)}
    ).json()
    (only,) = body["candidates"]
    assert only["source"] == "ai" and only["occurrences"] == 1 and only["amount"] == 29.9
    assert only["category_id"] == fake.cats["Freizeit und Urlaub"]


def test_statement_analysis_works_without_ai_but_says_so(client: TestClient, fake: FakeAi) -> None:
    fake.down = True
    body = client.post(
        "/api/ai/statements/analyze", json={"filename": "a.csv", "content_base64": _b64(CSV)}
    ).json()
    assert body["ai"]["used"] is False and "nicht erreichbar" in body["ai"]["note"]
    assert body["unrated"] == 1 and len(body["candidates"]) == 3
    assert all(c["category_id"] is None for c in body["candidates"])


def test_pdf_statement_is_read_by_the_local_model(client: TestClient, fake: FakeAi) -> None:
    fake.pdf_lines = [
        {"date": "2026-08-05", "amount": -12.99, "counterparty": "Netflix", "purpose": "Abo"},
        {"date": "2026-09-05", "amount": -12.99, "counterparty": "Netflix", "purpose": "Abo"},
        {"date": "kaputt", "amount": 1, "counterparty": "x", "purpose": ""},
    ]
    text = "Kontoauszug August und September 2026 " * 6
    body = client.post(
        "/api/ai/statements/analyze", json={"filename": "a.pdf", "content_base64": _b64(_pdf(text))}
    ).json()
    assert body["format"] == "pdf" and body["lines"] == 2  # the unreadable row is skipped
    assert [c["name"] for c in body["candidates"]] == ["Netflix"]


def test_pdf_without_text_and_without_ai(client: TestClient, fake: FakeAi) -> None:
    r = client.post(
        "/api/ai/statements/analyze",
        json={"filename": "scan.pdf", "content_base64": _b64(_pdf(""))},
    )
    assert r.status_code == 422 and "Scan" in r.json()["detail"]
    fake.down = True
    text = "Kontoauszug August und September 2026 " * 6
    r = client.post(
        "/api/ai/statements/analyze", json={"filename": "a.pdf", "content_base64": _b64(_pdf(text))}
    )
    assert r.status_code == 503 and "KI-Server" in r.json()["detail"]


def test_bad_uploads_are_rejected(client: TestClient, fake: FakeAi) -> None:
    r = client.post("/api/ai/statements/analyze", json={"filename": "a", "content_base64": "###"})
    assert r.status_code == 422
    fake.answers["header_row"] = {  # the AI finds no usable columns either
        "header_row": 0,
        "date": 7,
        "amount": None,
        "debit": None,
        "credit": None,
        "counterparty": None,
        "purpose": None,
    }
    r = client.post(
        "/api/ai/statements/analyze",
        json={"filename": "a.csv", "content_base64": _b64("x;y\n1;2\n")},
    )
    assert r.status_code == 422


def test_ai_endpoints_need_a_login(client: TestClient) -> None:
    assert client.get("/api/ai/status").status_code == 401
    assert client.post("/api/ai/suggest", json={"name": "x"}).status_code == 401
