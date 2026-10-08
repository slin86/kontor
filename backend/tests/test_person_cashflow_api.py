from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_financing_api import LOAN

PASSWORD = "correct-horse-battery"
TODAY = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    for target in ("kontor.api.cashflow.current_month", "kontor.api.financings.current_month"):
        monkeypatch.setattr(target, lambda: TODAY)


def _register(client: TestClient, email: str = "nils@example.com", name: str = "Nils") -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": name,
            "household_name": f"Haushalt {email}",
        },
    )
    assert r.status_code == 201, r.text
    client.headers["X-CSRF-Token"] = client.cookies.get("kontor_csrf") or ""


def _mandy(client: TestClient) -> int:
    r = client.post("/api/people", json={"name": "Mandy"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _me(client: TestClient) -> int:
    return next(p["id"] for p in client.get("/api/people").json() if p["is_me"])


def _cat(client: TestClient, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def _item(client: TestClient, name: str, cat: str, amount: str, **extra: object) -> dict:
    r = client.post(
        "/api/cashflow/items",
        json={
            "name": name,
            "category_id": _cat(client, cat),
            "amount": amount,
            "frequency": "monthly",
            "valid_from": "2026-01",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _summary(client: TestClient, person: int | None = None) -> dict:
    suffix = f"&person={person}" if person is not None else ""
    return client.get(f"/api/cashflow/summary?month=2026-10{suffix}").json()


def _salary_cat(client: TestClient) -> str:
    return next(c["name"] for c in client.get("/api/categories").json() if c["kind"] == "income")


def _expense_cat(client: TestClient) -> str:
    return next(c["name"] for c in client.get("/api/categories").json() if c["kind"] == "expense")


def test_items_default_to_the_own_person_and_scope_the_summary(client: TestClient) -> None:
    _register(client)
    mandy, me = _mandy(client), _me(client)
    income, expense = _salary_cat(client), _expense_cat(client)
    _item(client, "Gehalt Nils", income, "3000")
    _item(client, "Gehalt Mandy", income, "2000", person_id=mandy)
    _item(client, "Miete", expense, "1000", person_id=mandy)

    assert _summary(client)["income"] == 5000
    assert _summary(client, me)["income"] == 3000
    assert _summary(client, me)["expenses"] == 0
    assert _summary(client, mandy)["income"] == 2000
    assert _summary(client, mandy)["expenses"] == 1000
    names = [i["name"] for i in client.get(f"/api/cashflow/items?person={mandy}").json()]
    assert sorted(names) == ["Gehalt Mandy", "Miete"]


def test_transfer_is_expense_for_sender_income_for_receiver_and_nets_out(
    client: TestClient,
) -> None:
    _register(client)
    mandy, me = _mandy(client), _me(client)
    _item(client, "Gehalt Mandy", _salary_cat(client), "2000", person_id=mandy)

    r = client.post(
        "/api/cashflow/items",
        json={
            "name": "Haushaltsgeld",
            "person_id": mandy,
            "transfer_to_id": me,
            "amount": "800",
            "frequency": "monthly",
            "valid_from": "2026-01",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["transfer_to_name"] == "Nils"

    assert _summary(client, mandy)["expenses"] == 800
    assert _summary(client, mandy)["balance"] == 1200
    mine = _summary(client, me)
    assert mine["income"] == 800
    assert [g["name"] for g in mine["income_groups"]] == ["Übertrag erhalten"]
    household = _summary(client)
    assert household["income"] == 2000
    assert household["expenses"] == 0

    incoming = next(
        i for i in client.get(f"/api/cashflow/items?person={me}").json() if i["incoming"]
    )
    assert incoming["name"] == "Übertrag von Mandy"
    assert incoming["kind"] == "income"
    series = client.get(f"/api/cashflow/series?from=2026-10&to=2026-10&person={me}").json()
    assert series[0]["income"] == 800


def test_transfer_validation(client: TestClient) -> None:
    _register(client)
    me = _me(client)
    base = {"name": "x", "amount": "10", "frequency": "monthly", "valid_from": "2026-01"}
    same = client.post("/api/cashflow/items", json={**base, "transfer_to_id": me})
    assert same.status_code == 422
    no_category = client.post("/api/cashflow/items", json=base)
    assert no_category.status_code == 422


def test_transfer_can_be_changed_like_any_item(client: TestClient) -> None:
    _register(client)
    mandy, me = _mandy(client), _me(client)
    item = client.post(
        "/api/cashflow/items",
        json={
            "name": "Haushaltsgeld",
            "person_id": mandy,
            "transfer_to_id": me,
            "amount": "800",
            "frequency": "monthly",
            "valid_from": "2026-10",
        },
    ).json()
    r = client.post(
        f"/api/cashflow/items/{item['id']}/change",
        json={"effective_from": "2026-11", "amount": "900", "frequency": "monthly"},
    )
    assert r.status_code == 200, r.text
    nov = client.get(f"/api/cashflow/summary?month=2026-11&person={me}").json()
    assert nov["income"] == 900
    moved = client.patch(f"/api/cashflow/items/{item['id']}", json={"person_id": me})
    assert moved.status_code == 422


def test_financings_belong_to_a_person(client: TestClient) -> None:
    _register(client)
    mandy, me = _mandy(client), _me(client)
    mine = client.post("/api/financings", json=LOAN)
    assert mine.status_code == 201, mine.text
    assert mine.json()["person_id"] == me
    hers = client.post(f"/api/financings?person={mandy}", json={**LOAN, "name": "Auto"})
    assert hers.json()["person_id"] == mandy

    assert len(client.get("/api/financings").json()) == 2
    assert [f["name"] for f in client.get(f"/api/financings?person={mandy}").json()] == ["Auto"]
    assert _summary(client, me)["financing"] > 0
    assert _summary(client, mandy)["financing"] > 0
    assert round(_summary(client)["financing"], 2) == round(
        _summary(client, me)["financing"] + _summary(client, mandy)["financing"], 2
    )

    moved = client.put(f"/api/financings/{hers.json()['id']}/person?person={me}")
    assert moved.status_code == 200
    assert client.get(f"/api/financings?person={mandy}").json() == []


def test_outlook_follows_the_person(client: TestClient) -> None:
    _register(client)
    mandy, me = _mandy(client), _me(client)
    _item(client, "Gehalt Mandy", _salary_cat(client), "2000", person_id=mandy)
    r = client.get(f"/api/outlook?years=1&start=2026-10&person={mandy}").json()
    assert r["points"][0]["income"] == 2000
    r = client.get(f"/api/outlook?years=1&start=2026-10&person={me}").json()
    assert r["points"][0]["income"] == 0


def test_person_with_bookings_cannot_be_deleted(client: TestClient) -> None:
    _register(client)
    mandy = _mandy(client)
    _item(client, "Gehalt Mandy", _salary_cat(client), "2000", person_id=mandy)
    assert client.delete(f"/api/people/{mandy}").status_code == 409


def test_other_household_person_is_not_found(client: TestClient) -> None:
    _register(client)
    foreign = _me(client)
    client.post("/api/auth/logout")
    _register(client, "other@example.com", "Other")
    assert client.get(f"/api/cashflow/summary?person={foreign}").status_code == 404
    assert client.get(f"/api/financings?person={foreign}").status_code == 404
