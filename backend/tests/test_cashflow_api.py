from datetime import date

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend it is October 2026, so September and earlier are locked history."""
    monkeypatch.setattr("kontor.api.cashflow.current_month", lambda: date(2026, 10, 1))


def _login_new_household(client: TestClient, email: str = "nils@example.com") -> dict:
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
    return r.json()


def _category_id(client: TestClient, name: str) -> int:
    cats = client.get("/api/categories").json()
    return next(c["id"] for c in cats if c["name"] == name)


def _create_item(
    client: TestClient,
    name: str,
    category: str,
    amount: str,
    valid_from: str = "2026-01",
    frequency: str = "monthly",
) -> dict:
    r = client.post(
        "/api/cashflow/items",
        json={
            "name": name,
            "category_id": _category_id(client, category),
            "amount": amount,
            "frequency": frequency,
            "valid_from": valid_from,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_default_categories_are_seeded(client: TestClient) -> None:
    _login_new_household(client)
    names = {c["name"] for c in client.get("/api/categories").json()}
    assert {"Gehalt", "Wohnen", "Nebenkosten", "Lebensmittel"} <= names


def test_create_category_validates_parent(client: TestClient) -> None:
    _login_new_household(client)
    wohnen = _category_id(client, "Wohnen")
    ok = client.post(
        "/api/categories", json={"name": "Garten", "kind": "expense", "parent_id": wohnen}
    )
    assert ok.status_code == 201
    too_deep = client.post(
        "/api/categories",
        json={"name": "Beet", "kind": "expense", "parent_id": ok.json()["id"]},
    )
    assert too_deep.status_code == 422
    wrong_kind = client.post(
        "/api/categories", json={"name": "Bonus", "kind": "income", "parent_id": wohnen}
    )
    assert wrong_kind.status_code == 422


def test_item_is_listed_only_in_months_where_it_applies(client: TestClient) -> None:
    _login_new_household(client)
    _create_item(client, "Miete", "Wohnen", "1200", valid_from="2026-03")
    in_month = client.get("/api/cashflow/items", params={"month": "2026-05"}).json()
    assert [i["name"] for i in in_month] == ["Miete"]
    assert in_month[0]["active"]["amount"] == 1200
    before = client.get("/api/cashflow/items", params={"month": "2026-02"}).json()
    assert before == []
    everything = client.get(
        "/api/cashflow/items", params={"month": "2026-02", "include_inactive": "true"}
    ).json()
    assert len(everything) == 1


def test_quarterly_and_yearly_items_are_normalised_to_months(client: TestClient) -> None:
    _login_new_household(client)
    _create_item(client, "Haftpflicht", "Versicherungen", "120", frequency="yearly")
    _create_item(client, "Wasser", "Nebenkosten", "90", frequency="quarterly")
    summary = client.get("/api/cashflow/summary", params={"month": "2026-06"}).json()
    assert summary["expenses"] == 40.0  # 10 + 30


def test_future_change_keeps_history_untouched(client: TestClient) -> None:
    _login_new_household(client)
    item = _create_item(client, "Strom", "Strom und Gas", "80")
    r = client.post(
        f"/api/cashflow/items/{item['id']}/change",
        json={"effective_from": "2026-12", "amount": "95", "frequency": "monthly"},
    )
    assert r.status_code == 200, r.text
    versions = r.json()["versions"]
    assert [(v["amount"], v["valid_from"], v["valid_to"]) for v in versions] == [
        (80, "2026-01", "2026-12"),
        (95, "2026-12", None),
    ]
    sep = client.get("/api/cashflow/summary", params={"month": "2026-09"}).json()
    jan = client.get("/api/cashflow/summary", params={"month": "2027-01"}).json()
    assert sep["expenses"] == 80 and jan["expenses"] == 95


def test_change_in_closed_month_is_rejected(client: TestClient) -> None:
    _login_new_household(client)
    item = _create_item(client, "Strom", "Strom und Gas", "80")
    r = client.post(
        f"/api/cashflow/items/{item['id']}/change",
        json={"effective_from": "2026-09", "amount": "95", "frequency": "monthly"},
    )
    assert r.status_code == 409
    assert "Korrektur" in r.json()["detail"]
    # current month is still open
    ok = client.post(
        f"/api/cashflow/items/{item['id']}/change",
        json={"effective_from": "2026-10", "amount": "95", "frequency": "monthly"},
    )
    assert ok.status_code == 200


def test_end_item_from_future_month(client: TestClient) -> None:
    _login_new_household(client)
    item = _create_item(client, "Kita", "Kita und Schule", "300")
    r = client.post(f"/api/cashflow/items/{item['id']}/end", json={"end_from": "2027-08"})
    assert r.status_code == 200
    assert (
        client.get("/api/cashflow/summary", params={"month": "2027-07"}).json()["expenses"] == 300
    )
    assert client.get("/api/cashflow/summary", params={"month": "2027-08"}).json()["expenses"] == 0
    closed = client.post(f"/api/cashflow/items/{item['id']}/end", json={"end_from": "2026-06"})
    assert closed.status_code == 409


def test_correction_changes_history_with_reason_and_audit_trail(client: TestClient) -> None:
    _login_new_household(client)
    item = _create_item(client, "Miete", "Wohnen", "1200")
    version_id = item["versions"][0]["id"]
    assert item["versions"][0]["locked"] is True

    no_reason = client.post(f"/api/cashflow/versions/{version_id}/correct", json={"amount": "1250"})
    assert no_reason.status_code == 422

    r = client.post(
        f"/api/cashflow/versions/{version_id}/correct",
        json={"amount": "1250", "reason": "Tippfehler bei der Erfassung"},
    )
    assert r.status_code == 200, r.text
    assert (
        client.get("/api/cashflow/summary", params={"month": "2026-03"}).json()["expenses"] == 1250
    )

    log = client.get("/api/audit").json()
    correction = next(e for e in log if e["action"] == "correction")
    assert correction["reason"] == "Tippfehler bei der Erfassung"
    assert correction["subject"] == "Miete"
    assert correction["before"]["amount"] == "1200.00"
    assert correction["after"]["amount"] == "1250.00"
    # creating an item in a closed month is recorded as a backfill
    assert any(e["action"] == "backfill" for e in log)


def test_households_are_isolated(client: TestClient) -> None:
    _login_new_household(client, "a@example.com")
    item = _create_item(client, "Miete", "Wohnen", "1000")
    version_id = item["versions"][0]["id"]
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)

    _login_new_household(client, "b@example.com")
    assert client.get("/api/cashflow/items", params={"month": "2026-05"}).json() == []
    change = client.post(
        f"/api/cashflow/items/{item['id']}/change",
        json={"effective_from": "2027-01", "amount": "1", "frequency": "monthly"},
    )
    assert change.status_code == 404
    fix = client.post(
        f"/api/cashflow/versions/{version_id}/correct",
        json={"amount": "1", "reason": "fremder Posten"},
    )
    assert fix.status_code == 404
    other_cat = client.post(
        "/api/cashflow/items",
        json={
            "name": "x",
            "category_id": 1,  # belongs to household A
            "amount": "5",
            "frequency": "monthly",
            "valid_from": "2026-10",
        },
    )
    assert other_cat.status_code == 422


def test_summary_and_sankey_for_a_month(client: TestClient) -> None:
    _login_new_household(client)
    _create_item(client, "Netto Nils", "Gehalt", "3000")
    _create_item(client, "Miete", "Wohnen", "1000")
    _create_item(client, "Strom", "Strom und Gas", "100")
    _create_item(client, "Essen", "Lebensmittel", "500")

    s = client.get("/api/cashflow/summary", params={"month": "2026-10"}).json()
    assert (s["income"], s["expenses"], s["balance"]) == (3000, 1600, 1400)
    assert s["savings_rate"] == pytest.approx(0.4667, abs=1e-4)
    wohnen = next(g for g in s["expense_groups"] if g["name"] == "Wohnen")
    assert wohnen["total"] == 1100
    assert [c["name"] for c in wohnen["children"]] == ["Strom und Gas", "Ohne Unterkategorie"]
    assert [c["total"] for c in wohnen["children"]] == [100, 1000]

    sk = client.get("/api/cashflow/sankey", params={"month": "2026-10"}).json()
    ids = {n["id"] for n in sk["nodes"]}
    assert "hub" in ids and "surplus" in ids
    surplus = next(link for link in sk["links"] if link["target"] == "surplus")
    assert surplus["value"] == 1400


def test_series_covers_each_month(client: TestClient) -> None:
    _login_new_household(client)
    item = _create_item(client, "Netto", "Gehalt", "2000")
    client.post(
        f"/api/cashflow/items/{item['id']}/change",
        json={"effective_from": "2026-12", "amount": "2200", "frequency": "monthly"},
    )
    r = client.get("/api/cashflow/series", params={"from": "2026-11", "to": "2027-01"})
    assert [(p["month"], p["income"]) for p in r.json()] == [
        ("2026-11", 2000),
        ("2026-12", 2200),
        ("2027-01", 2200),
    ]
    bad = client.get("/api/cashflow/series", params={"from": "2027-01", "to": "2026-11"})
    assert bad.status_code == 422


def test_invalid_month_is_rejected(client: TestClient) -> None:
    _login_new_household(client)
    assert client.get("/api/cashflow/summary", params={"month": "2026-13"}).status_code == 422


def test_requires_login(client: TestClient) -> None:
    assert client.get("/api/cashflow/summary").status_code == 401
