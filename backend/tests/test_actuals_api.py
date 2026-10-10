from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_broker_csv import TR_SAMPLE

PASSWORD = "correct-horse-battery"
TODAY = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    for target in ("kontor.api.actuals.current_month", "kontor.api.depot.current_month"):
        monkeypatch.setattr(target, lambda: TODAY)


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


def _position(client: TestClient, **over: str) -> dict:
    body = {
        "kind": "etf",
        "name": "Invesco MSCI World",
        "isin": "IE00B60SX394",
        "expected_return_percent": "6",
        "cost_percent": "0.05",
        "entry_fee_percent": "0",
        "start": "2026-08",
        "start_value": "0",
        "monthly_rate": "250",
        **over,
    }
    r = client.post("/api/depot/instruments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_value_entry_and_corrections(client: TestClient) -> None:
    _login(client)
    p = _position(client)
    put = lambda **b: client.put("/api/actuals/values", json={"instrument_id": p["id"], **b})  # noqa: E731

    assert put(month="2026-11", value="100").status_code == 422  # the future
    assert put(month="2026-07", value="100").status_code == 422  # before the start
    assert put(month="2026-08", value="250").status_code == 200
    # a closed month needs a reason to be overwritten
    assert put(month="2026-08", value="260").status_code == 422
    ok = put(month="2026-08", value="260", reason="Kontoauszug abgeglichen")
    assert ok.status_code == 200 and ok.json()["value"] == 260
    # the current month stays freely editable
    assert put(month="2026-10", value="700").status_code == 200
    assert put(month="2026-10", value="710").status_code == 200

    values = client.get("/api/actuals/values", params={"instrument_id": p["id"]}).json()
    assert [(v["month"], v["value"]) for v in values] == [("2026-10", 710), ("2026-08", 260)]
    log = client.get("/api/audit").json()
    correction = next(e for e in log if e["action"] == "correction")
    assert correction["reason"] == "Kontoauszug abgeglichen" and correction["subject"] == p["name"]


def test_other_households_cannot_touch_positions(client: TestClient) -> None:
    _login(client)
    p = _position(client)
    client.post("/api/auth/logout")
    _login(client, "other@example.com")
    r = client.put(
        "/api/actuals/values", json={"instrument_id": p["id"], "month": "2026-09", "value": "1"}
    )
    assert r.status_code == 404
    assert client.get("/api/actuals/values").json() == []


def test_import_preview_then_import_is_idempotent(client: TestClient) -> None:
    _login(client)
    p = _position(client)

    preview = client.post("/api/actuals/import/preview", json={"csv": TR_SAMPLE})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["new_count"] == 3 and body["duplicate_count"] == 0
    assert [u["isin"] for u in body["unmatched"]] == ["US0378331005"]  # the Apple dividend
    assert body["skipped"] == {"CASH/CUSTOMER_INBOUND": 1, "CASH/CARD_TRANSACTION": 1}
    assert len(body["errors"]) == 1
    assert {r["instrument_id"] for r in body["rows"] if r["isin"] == "IE00B60SX394"} == {p["id"]}

    done = client.post("/api/actuals/import", json={"csv": TR_SAMPLE}).json()
    assert done == {"imported": 3, "duplicates": 0, "unmatched": 1}
    again = client.post("/api/actuals/import", json={"csv": TR_SAMPLE}).json()
    assert again == {"imported": 0, "duplicates": 3, "unmatched": 1}
    assert (
        client.post("/api/actuals/import/preview", json={"csv": TR_SAMPLE}).json()[
            "duplicate_count"
        ]
        == 3
    )

    txs = client.get("/api/actuals/transactions").json()
    assert len(txs) == 3 and {t["source"] for t in txs} == {"csv"}
    assert txs[0]["day"] == "2026-09-10"  # newest first


def test_mapping_assigns_unknown_isins_to_a_position(client: TestClient) -> None:
    _login(client)
    p = _position(client, isin=None)
    r = client.post(
        "/api/actuals/import", json={"csv": TR_SAMPLE, "mapping": {"IE00B60SX394": p["id"]}}
    )
    assert r.json()["imported"] == 3
    foreign = client.post("/api/actuals/import", json={"csv": TR_SAMPLE, "mapping": {"X": 9999}})
    assert foreign.status_code == 404


def test_bad_files_are_rejected_with_a_message(client: TestClient) -> None:
    _login(client)
    r = client.post("/api/actuals/import/preview", json={"csv": "foo,bar\n1,2\n"})
    assert r.status_code == 422 and "Transaktionsexport" in r.json()["detail"]


def test_manual_transactions_and_delete(client: TestClient) -> None:
    _login(client)
    p = _position(client)
    body = {
        "instrument_id": p["id"],
        "day": "2026-09-05",
        "kind": "buy",
        "amount": "250",
        "fee": "1",
    }
    created = client.post("/api/actuals/transactions", json=body)
    assert created.status_code == 201, created.text
    assert (
        client.post("/api/actuals/transactions", json={**body, "day": "2026-12-05"}).status_code
        == 422
    )
    assert client.delete(f"/api/actuals/transactions/{created.json()['id']}").status_code == 204
    assert client.get("/api/actuals/transactions").json() == []


def test_plan_vs_actual(client: TestClient) -> None:
    _login(client)
    p = _position(client, start_value="0")  # 250 per month from Aug 2026
    other = _position(client, name="Ohne Ist-Werte", isin=None, monthly_rate="100")
    for month, value in (("2026-08", "250"), ("2026-09", "480"), ("2026-10", "760")):
        r = client.put(
            "/api/actuals/values", json={"instrument_id": p["id"], "month": month, "value": value}
        )
        assert r.status_code == 200, r.text
    client.post("/api/actuals/import", json={"csv": TR_SAMPLE})

    r = client.get("/api/actuals/compare")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["first"], body["last"]) == ("2026-08", "2026-10")
    pts = {x["month"]: x for x in body["points"]}
    assert pts["2026-09"]["actual"] == 480
    assert pts["2026-09"]["planned_tracked"] > 500  # 2 x 250 plus a little growth
    assert pts["2026-09"]["planned_total"] > pts["2026-09"]["planned_tracked"]  # includes the other
    # deposits only count positions with transactions
    assert pts["2026-09"]["actual_deposit"] == 250 - 74
    assert pts["2026-08"]["actual_deposit"] == 250

    rows = {x["id"]: x for x in body["instruments"]}
    mine, untouched = rows[p["id"]], rows[other["id"]]
    assert mine["actual_value"] == 760 and mine["actual_month"] == "2026-10"
    assert mine["deviation"] == pytest.approx(760 - mine["planned_value"], abs=0.01)
    assert mine["actual_net_invested"] == 250 + 250 - 74
    assert untouched["actual_value"] is None and untouched["planned_value"] > 0
    assert untouched["actual_net_invested"] is None


def test_months_with_a_missing_value_have_no_actual(client: TestClient) -> None:
    _login(client)
    p = _position(client)
    client.put(
        "/api/actuals/values", json={"instrument_id": p["id"], "month": "2026-08", "value": "250"}
    )
    client.put(
        "/api/actuals/values", json={"instrument_id": p["id"], "month": "2026-10", "value": "760"}
    )
    pts = {x["month"]: x for x in client.get("/api/actuals/compare").json()["points"]}
    assert pts["2026-09"]["actual"] is None and pts["2026-10"]["actual"] == 760


def test_empty_household_compares_nothing(client: TestClient) -> None:
    _login(client)
    body = client.get("/api/actuals/compare").json()
    assert body["instruments"] == [] and len(body["points"]) == 1


def test_overview_without_values_has_no_verdict(client: TestClient) -> None:
    _login(client)
    _position(client)
    body = client.get("/api/actuals/overview?years=5").json()
    assert body["status"] == "no_data" and body["anchor"] is None
    assert body["forecast_end"] is None and body["plan_end"] > 0
    assert all(p["actual"] is None and p["forecast"] is None for p in body["points"])


def test_overview_forecast_starts_at_the_latest_real_value(client: TestClient) -> None:
    _login(client)
    p = _position(client)  # 250 per month from Aug 2026
    other = _position(client, name="Ohne Ist-Werte", isin=None, monthly_rate="100")
    for month, value in (("2026-08", "250"), ("2026-09", "400"), ("2026-10", "500")):
        client.put(
            "/api/actuals/values", json={"instrument_id": p["id"], "month": month, "value": value}
        )
    body = client.get("/api/actuals/overview?years=10").json()
    assert body["anchor"] == "2026-10" and body["tracked"] == [p["name"]]
    assert body["untracked"] == [other["name"]]
    assert body["status"] == "behind" and body["deviation"] < 0
    pts = {x["month"]: x for x in body["points"]}
    assert pts["2026-10"]["actual"] == pts["2026-10"]["forecast"]  # the lines meet
    assert pts["2026-11"]["actual"] is None and pts["2026-11"]["forecast"] > 0
    assert pts["2026-09"]["forecast"] is None
    # being behind today means ending behind the plan, too
    assert body["end"] == "2036-10" and body["end_gap"] < 0
    assert body["forecast_end"] == pytest.approx(body["plan_end"] + body["end_gap"], abs=0.02)


def test_overview_on_plan_when_the_values_match(client: TestClient) -> None:
    _login(client)
    p = _position(client, start_value="1000", monthly_rate="0")
    planned = {x["month"]: x for x in client.get("/api/actuals/overview").json()["points"]}
    client.put(
        "/api/actuals/values",
        json={
            "instrument_id": p["id"],
            "month": "2026-10",
            "value": str(planned["2026-10"]["plan"]),
        },
    )
    body = client.get("/api/actuals/overview").json()
    assert body["status"] == "on_track" and body["deviation"] == 0
    assert body["forecast_end"] == pytest.approx(body["plan_end"], abs=0.02)
