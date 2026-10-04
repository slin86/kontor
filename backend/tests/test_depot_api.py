from datetime import date

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"
TODAY = {"value": date(2026, 10, 1)}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    TODAY["value"] = date(2026, 10, 1)
    monkeypatch.setattr("kontor.api.depot.current_month", lambda: TODAY["value"])
    monkeypatch.setattr("kontor.api.cashflow.current_month", lambda: TODAY["value"])


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


ETF = {
    "kind": "etf",
    "name": "MSCI World",
    "isin": "IE00B4L5Y983",
    "expected_return_percent": "6",
    "cost_percent": "0.2",
    "entry_fee_percent": "0",
    "start": "2026-01",
    "start_value": "5000",
    "monthly_rate": "300",
}
EQT = {
    "kind": "private_equity",
    "name": "Private Equity Fonds",
    "expected_return_percent": "9",
    "cost_percent": "2",
    "entry_fee_percent": "3",
    "start": "2026-10",
    "start_value": "0",
    "monthly_rate": "100",
}


def _create(client: TestClient, body: dict) -> dict:
    r = client.post("/api/depot/instruments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_base_rate_is_the_sum_of_all_rates(client: TestClient) -> None:
    _login(client)
    _create(client, ETF)
    _create(client, EQT)
    body = client.get("/api/depot").json()
    assert body["base_rate"] == 400
    assert {i["name"]: i["current_rate"] for i in body["instruments"]} == {
        "MSCI World": 300,
        "Private Equity Fonds": 100,
    }
    msci = next(i for i in body["instruments"] if i["name"] == "MSCI World")
    assert msci["paid_in"] == 5000 + 10 * 300  # Jan..Oct
    assert msci["planned_value"] > msci["paid_in"]


def test_households_are_isolated_and_isin_is_validated(client: TestClient) -> None:
    _login(client)
    created = _create(client, ETF)
    assert client.post("/api/depot/instruments", json={**ETF, "isin": "nope"}).status_code == 422
    client.post("/api/auth/logout")
    _login(client, "other@example.com")
    assert client.get(f"/api/depot/instruments/{created['id']}").status_code == 404
    assert client.get("/api/depot").json()["instruments"] == []


def test_rate_change_keeps_later_changes_and_locks_the_past(client: TestClient) -> None:
    _login(client)
    i = _create(client, ETF)
    base = f"/api/depot/instruments/{i['id']}/rate"
    assert client.post(base, json={"effective_from": "2028-01", "amount": "500"}).status_code == 200
    r = client.post(base, json={"effective_from": "2027-01", "amount": "400"})
    assert r.status_code == 200, r.text
    rates = [(x["valid_from"], x["valid_to"], x["amount"]) for x in r.json()["rates"]]
    assert rates == [
        ("2026-01", "2027-01", 300),
        ("2027-01", "2028-01", 400),
        ("2028-01", None, 500),
    ]
    assert client.post(base, json={"effective_from": "2026-09", "amount": "1"}).status_code == 409
    assert client.post(base, json={"effective_from": "2026-10", "amount": "0"}).status_code == 200
    assert client.get("/api/depot").json()["base_rate"] == 0


def test_one_offs_are_validated_and_removable(client: TestClient) -> None:
    _login(client)
    i = _create(client, ETF)
    base = f"/api/depot/instruments/{i['id']}/one-offs"
    ok = client.post(base, json={"month": "2027-06", "amount": "2000", "note": "Bonus"})
    assert ok.status_code == 200, ok.text
    assert client.post(base, json={"month": "2026-09", "amount": "5"}).status_code == 409
    assert client.post(base, json={"month": "2027-06", "amount": "0"}).status_code == 422
    too_much = client.post(base, json={"month": "2027-07", "amount": "-900000"})
    assert too_much.status_code == 422
    assert "übersteigt" in too_much.json()["detail"]

    one_off = ok.json()["one_offs"][0]
    assert one_off["amount"] == 2000 and not one_off["locked"]
    gone = client.delete(f"{base}/{one_off['id']}")
    assert gone.status_code == 200 and gone.json()["one_offs"] == []


def test_correction_needs_a_reason_and_is_audited(client: TestClient) -> None:
    _login(client)
    i = _create(client, ETF)
    url = f"/api/depot/instruments/{i['id']}/correct"
    bad = client.post(url, json={"start": "2025-06", "start_value": "4000", "reason": ""})
    assert bad.status_code == 422
    ok = client.post(url, json={"start": "2025-06", "start_value": "4000", "reason": "Kontoauszug"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["start"] == "2025-06" and body["rates"][0]["valid_from"] == "2025-06"
    log = client.get("/api/audit").json()
    entry = next(e for e in log if e["action"] == "correction")
    assert entry["reason"] == "Kontoauszug" and entry["subject"] == "MSCI World"


def test_assumption_update_changes_the_projection(client: TestClient) -> None:
    _login(client)
    i = _create(client, ETF)
    before = client.get("/api/depot/projection", params={"years": 10}).json()["points"][-1]["value"]
    r = client.put(
        f"/api/depot/instruments/{i['id']}",
        json={**ETF, "expected_return_percent": "3"},
    )
    assert r.status_code == 200, r.text
    after = client.get("/api/depot/projection", params={"years": 10}).json()["points"][-1]["value"]
    assert after < before


def test_projection_history_future_scenarios_and_inflation(client: TestClient) -> None:
    _login(client)
    _create(client, ETF)
    _create(client, EQT)
    r = client.get("/api/depot/projection", params={"years": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["first"] == "2026-01" and body["last"] == "2046-10"
    assert [x["name"] for x in body["instruments"]] == ["MSCI World", "Private Equity Fonds"]
    points = body["points"]
    assert len(points) == 12 * 20 + 10
    assert points[0]["balances"][1] == 0  # the PE position starts in October
    assert points[-1]["value"] == pytest.approx(sum(points[-1]["balances"]), abs=0.05)
    assert body["base_rate"] == 400

    low = client.get("/api/depot/projection", params={"years": 20, "return_shift": -2}).json()
    high = client.get("/api/depot/projection", params={"years": 20, "return_shift": 2}).json()
    assert low["points"][-1]["value"] < points[-1]["value"] < high["points"][-1]["value"]

    real = client.get("/api/depot/projection", params={"years": 20, "inflation": 2}).json()
    assert real["points"][-1]["value"] < points[-1]["value"]
    assert real["points"][-1]["paid_in"] == points[-1]["paid_in"]

    later = client.get("/api/depot/projection", params={"years": 20, "start": "2030-01"}).json()
    assert later["points"][0]["month"] == "2030-01"
    assert later["points"][0]["value"] == next(
        p["value"] for p in points if p["month"] == "2030-01"
    )


def test_empty_depot_projects_nothing(client: TestClient) -> None:
    _login(client)
    body = client.get("/api/depot/projection", params={"years": 1}).json()
    assert body["instruments"] == [] and body["points"][0]["value"] == 0


def test_delete_position_keeps_the_audit_trail(client: TestClient) -> None:
    _login(client)
    i = _create(client, ETF)
    assert client.delete(f"/api/depot/instruments/{i['id']}").status_code == 204
    assert client.get(f"/api/depot/instruments/{i['id']}").status_code == 404
    assert client.get("/api/depot").json()["instruments"] == []
    entry = next(e for e in client.get("/api/audit").json() if e["action"] == "delete")
    assert entry["before"]["name"] == "MSCI World"


def test_projection_has_net_values_and_tax_settings(client: TestClient) -> None:
    _login(client)
    client.post("/api/depot/instruments", json=ETF)
    plain = client.get("/api/depot/projection?years=20").json()
    last = plain["points"][-1]
    assert plain["tax_rate_percent"] == 26.375
    assert 0 < last["net_value"] < last["value"]
    assert last["tax_on_sale"] > 0
    assert round(last["value"] - last["tax_paid"] - last["tax_on_sale"], 1) == round(
        last["net_value"], 1
    )

    r = client.put(
        "/api/tax/settings",
        json={"church_tax_percent": 9, "allowance": "2000", "base_interest_percent": "2.5"},
    )
    assert r.status_code == 200
    assert r.json()["tax_rate_percent"] == 27.995
    assert client.get("/api/tax/settings").json()["allowance"] == 2000
    church = client.get("/api/depot/projection?years=20").json()
    assert church["tax_rate_percent"] == 27.995
    assert church["points"][-1]["net_value"] != last["net_value"]


def test_tax_settings_defaults_validation_and_isolation(client: TestClient) -> None:
    _login(client)
    d = client.get("/api/tax/settings").json()
    assert (d["church_tax_percent"], d["allowance"], d["base_interest_percent"]) == (0, 1000, 3.2)
    assert client.put("/api/tax/settings", json={"church_tax_percent": 7}).status_code == 422
    client.put("/api/tax/settings", json={"church_tax_percent": 8})
    other = TestClient(client.app)
    _login(other, "other@example.com")
    assert other.get("/api/tax/settings").json()["church_tax_percent"] == 0


def test_teilfreistellung_defaults_by_kind_and_can_be_changed(client: TestClient) -> None:
    _login(client)
    etf = client.post("/api/depot/instruments", json=ETF).json()
    eqt = client.post("/api/depot/instruments", json=EQT).json()
    assert etf["tax_exempt_percent"] == 30
    assert eqt["tax_exempt_percent"] == 0
    body = {
        "name": "MSCI World",
        "expected_return_percent": "6",
        "cost_percent": "0.2",
        "entry_fee_percent": "0",
        "tax_exempt_percent": "15",
    }
    assert (
        client.put(f"/api/depot/instruments/{etf['id']}", json=body).json()["tax_exempt_percent"]
        == 15
    )
    del body["tax_exempt_percent"]  # omitted keeps the stored value
    assert (
        client.put(f"/api/depot/instruments/{etf['id']}", json=body).json()["tax_exempt_percent"]
        == 15
    )
