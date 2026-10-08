from datetime import date

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"
TODAY = {"value": date(2026, 10, 1)}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    TODAY["value"] = date(2026, 10, 1)
    for target in ("kontor.api.cashflow.current_month", "kontor.api.financings.current_month"):
        monkeypatch.setattr(target, lambda: TODAY["value"])


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


LOAN = {
    "kind": "loan",
    "name": "Haus",
    "purpose": "real_estate",
    "principal": "100000",
    "annual_rate_percent": "3.6",
    "initial_repayment_percent": "2",
    "start": "2026-10",
}

BAUSPAR = {
    "kind": "building_savings",
    "name": "Bausparer",
    "contract_sum": "60000",
    "monthly_saving": "200",
    "start": "2026-01",
    "allocation": "2036-01",
    "fee_percent": "1",
    "deposit_rate_percent": "0",
    "loan_rate_percent": "2.5",
    "loan_payment": "300",
}


def _create(client: TestClient, body: dict) -> dict:
    r = client.post("/api/financings", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_loan_is_created_with_payment_from_initial_repayment(client: TestClient) -> None:
    _login(client)
    f = _create(client, LOAN)
    assert f["regular_payment"] == 466.67
    assert f["payment_this_month"] == 466.67
    assert f["phase"] == "loan"
    assert f["start"] == "2026-10" and f["end_month"] == "2055-06"
    assert f["total_interest"] == pytest.approx(60402.55)
    first = f["schedule"][0]
    assert (first["interest"], first["principal"], first["balance"]) == (300.0, 166.67, 99833.33)
    assert f["input"]["monthly_payment"] == "466.67"


def test_loan_input_is_validated(client: TestClient) -> None:
    _login(client)
    both = {**LOAN, "monthly_payment": "500"}
    assert client.post("/api/financings", json=both).status_code == 422
    neither = {k: v for k, v in LOAN.items() if k != "initial_repayment_percent"}
    assert client.post("/api/financings", json=neither).status_code == 422
    too_low = {k: v for k, v in LOAN.items() if k != "initial_repayment_percent"}
    too_low["monthly_payment"] = "100"
    r = client.post("/api/financings", json=too_low)
    assert r.status_code == 422
    assert "Zinsen" in r.json()["detail"]


def test_bauspar_has_saving_and_loan_phase(client: TestClient) -> None:
    _login(client)
    f = _create(client, BAUSPAR)
    assert f["phase"] == "saving"
    assert f["saved"] == 1800.0  # Jan-Sep 2026 lie before the current month: 9 x 200
    assert f["remaining_debt"] is None
    assert f["start"] == "2026-01" and f["end_month"] == "2047-08"
    assert f["schedule"][0]["fee"] == 600.0
    assert f["schedule"][0]["phase"] == "saving"
    assert {r["phase"] for r in f["schedule"]} == {"saving", "loan"}


def test_bauspar_oversaving_is_rejected(client: TestClient) -> None:
    _login(client)
    r = client.post("/api/financings", json={**BAUSPAR, "monthly_saving": "600"})
    assert r.status_code == 422
    assert "angespart" in r.json()["detail"]


def test_events_only_in_open_months_and_inside_the_term(client: TestClient) -> None:
    _login(client)
    f = _create(client, LOAN)
    base = f"/api/financings/{f['id']}/events"

    closed = {"month": "2026-09", "kind": "special_repayment", "value": "5000"}
    past = client.post(base, json=closed)
    assert past.status_code == 409
    after_end = client.post(
        base, json={"month": "2060-01", "kind": "special_repayment", "value": "100"}
    )
    assert after_end.status_code == 422
    # a rate the payment cannot cover is rejected with the reason
    too_high = client.post(base, json={"month": "2027-01", "kind": "rate_change", "value": "10"})
    assert too_high.status_code == 422
    assert "Zinsen" in too_high.json()["detail"]
    assert client.get(f"/api/financings/{f['id']}").json()["events"] == []

    rate = client.post(base, json={"month": "2027-01", "kind": "rate_change", "value": "4.2"})
    assert rate.status_code == 200, rate.text
    ok = client.post(base, json={"month": "2027-10", "kind": "special_repayment", "value": "10000"})
    assert ok.status_code == 200, ok.text
    detail = ok.json()
    assert [e["kind"] for e in detail["events"]] == ["rate_change", "special_repayment"]
    assert detail["events"][0]["value"] == 4.2  # percent per year
    special = next(r for r in detail["schedule"] if r["month"] == "2027-10")
    assert special["special"] == 10000.0


def test_event_before_the_loan_starts_is_rejected(client: TestClient) -> None:
    _login(client)
    f = _create(client, {**LOAN, "start": "2027-06"})
    r = client.post(
        f"/api/financings/{f['id']}/events",
        json={"month": "2027-01", "kind": "special_repayment", "value": "1000"},
    )
    assert r.status_code == 422
    assert "Beginn" in r.json()["detail"]


def test_special_repayment_shortens_the_term_and_can_be_removed(client: TestClient) -> None:
    _login(client)
    f = _create(client, LOAN)
    base = f"/api/financings/{f['id']}/events"
    added = client.post(
        base, json={"month": "2027-10", "kind": "special_repayment", "value": "10000"}
    )
    shorter = added.json()
    assert shorter["end_month"] == "2051-01"  # was 2055-06
    assert shorter["total_interest"] < f["total_interest"]

    event_id = shorter["events"][0]["id"]
    removed = client.delete(f"{base}/{event_id}")
    assert removed.status_code == 200
    assert removed.json()["end_month"] == "2055-06"
    assert removed.json()["events"] == []


def test_closed_events_cannot_be_removed(client: TestClient) -> None:
    _login(client)
    f = _create(client, LOAN)
    base = f"/api/financings/{f['id']}/events"
    added = client.post(
        base, json={"month": "2027-01", "kind": "special_repayment", "value": "1000"}
    )
    event_id = added.json()["events"][0]["id"]
    TODAY["value"] = date(2027, 3, 1)  # time passes
    r = client.delete(f"{base}/{event_id}")
    assert r.status_code == 409
    assert "Korrektur" in r.json()["detail"] or "korrigiere" in r.json()["detail"]


def test_correction_requires_a_reason_and_is_audited(client: TestClient) -> None:
    _login(client)
    f = _create(client, LOAN)
    url = f"/api/financings/{f['id']}/correct"
    fixed = {**LOAN, "annual_rate_percent": "3.9"}
    assert client.post(url, json={"data": fixed}).status_code == 422
    r = client.post(url, json={"reason": "Zins laut Vertrag", "data": fixed})
    assert r.status_code == 200, r.text
    assert r.json()["schedule"][0]["interest"] == 325.0  # 100000 * 0.039 / 12
    wrong_kind = client.post(url, json={"reason": "Versuch", "data": BAUSPAR})
    assert wrong_kind.status_code == 422

    log = client.get("/api/audit").json()
    entry = next(e for e in log if e["action"] == "correction" and e["entity"] == "financing")
    assert entry["subject"] == "Haus"
    assert entry["reason"] == "Zins laut Vertrag"
    assert entry["before"]["annual_rate_percent"] == "3.6"
    assert entry["after"]["annual_rate_percent"] == "3.9"


def test_financings_are_isolated_between_households(client: TestClient) -> None:
    _login(client, "a@example.com")
    f = _create(client, LOAN)
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    _login(client, "b@example.com")
    assert client.get("/api/financings").json() == []
    assert client.get(f"/api/financings/{f['id']}").status_code == 404
    assert (
        client.post(
            f"/api/financings/{f['id']}/events",
            json={"month": "2027-01", "kind": "special_repayment", "value": "5"},
        ).status_code
        == 404
    )


def _income(client: TestClient, amount: str) -> None:
    cats = client.get("/api/categories").json()
    cid = next(c["id"] for c in cats if c["name"] == "Gehalt")
    r = client.post(
        "/api/cashflow/items",
        json={
            "name": "Netto",
            "category_id": cid,
            "amount": amount,
            "frequency": "monthly",
            "valid_from": "2026-10",
        },
    )
    assert r.status_code == 201, r.text


def test_financings_flow_into_summary_sankey_and_series(client: TestClient) -> None:
    _login(client)
    _income(client, "4000")
    _create(client, LOAN)
    _create(client, {**BAUSPAR, "start": "2026-10", "allocation": "2036-10"})

    s = client.get("/api/cashflow/summary", params={"month": "2026-10"}).json()
    assert s["income"] == 4000
    assert s["expenses"] == 0
    # loan 466.67 + Bauspar 200 saving + 600 fee
    assert s["financing"] == pytest.approx(1266.67)
    assert s["balance"] == pytest.approx(2733.33)
    haus = next(f for f in s["financing_flows"] if f["name"] == "Haus")
    assert (haus["interest"], haus["principal"]) == (300.0, 166.67)

    sk = client.get("/api/cashflow/sankey", params={"month": "2026-10"}).json()
    ids = {n["id"] for n in sk["nodes"]}
    assert {
        "financing",
        "purpose:interest",
        "purpose:principal",
        "purpose:saving",
        "purpose:fee",
    } <= ids

    series = client.get("/api/cashflow/series", params={"from": "2026-10", "to": "2026-11"}).json()
    assert series[0]["financing"] == pytest.approx(1266.67)
    assert series[1]["financing"] == pytest.approx(666.67)  # the fee is only due once


def test_outlook_shows_budget_freed_when_a_financing_ends(client: TestClient) -> None:
    _login(client)
    _income(client, "4000")
    small = {
        **LOAN,
        "name": "Kredit",
        "purpose": "consumer",
        "principal": "12000",
        "annual_rate_percent": "0",
        "initial_repayment_percent": None,
        "monthly_payment": "500",
    }
    small.pop("initial_repayment_percent")
    _create(client, small)

    r = client.get("/api/outlook", params={"years": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["points"]) == 60
    assert body["points"][0]["free"] == 3500
    assert body["points"][-1]["free"] == 4000
    ends = [e for e in body["events"] if e["kind"] == "financing_end"]
    assert [(e["month"], e["label"], e["monthly_change"]) for e in ends] == [
        ("2028-10", "Kredit ist abbezahlt", 500.0)
    ]
    # first month without the loan
    by_month = {p["month"]: p["free"] for p in body["points"]}
    assert by_month["2028-09"] == 3500 and by_month["2028-10"] == 4000


def test_outlook_includes_ending_items_and_growth(client: TestClient) -> None:
    _login(client)
    _income(client, "4000")
    cats = client.get("/api/categories").json()
    kita = next(c["id"] for c in cats if c["name"] == "Kita und Schule")
    item = client.post(
        "/api/cashflow/items",
        json={
            "name": "Kita",
            "category_id": kita,
            "amount": "300",
            "frequency": "monthly",
            "valid_from": "2026-10",
        },
    ).json()
    client.post(f"/api/cashflow/items/{item['id']}/end", json={"end_from": "2027-08"})

    flat = client.get("/api/outlook", params={"years": 2}).json()
    assert [(e["month"], e["label"], e["monthly_change"]) for e in flat["events"]] == [
        ("2027-08", "Kita endet", 300.0)
    ]
    assert flat["points"][0]["free"] == 3700 and flat["points"][-1]["free"] == 4000

    grown = client.get("/api/outlook", params={"years": 2, "income_growth": 3}).json()
    assert grown["points"][-1]["income"] > flat["points"][-1]["income"]
    assert grown["points"][0]["income"] == 4000


def test_outlook_validates_parameters(client: TestClient) -> None:
    _login(client)
    assert client.get("/api/outlook", params={"years": 0}).status_code == 422
    assert client.get("/api/outlook", params={"income_growth": 50}).status_code == 422


def test_outlook_ignores_one_off_special_repayments(client: TestClient) -> None:
    _login(client)
    _income(client, "4000")
    f = _create(client, LOAN)
    base = f"/api/financings/{f['id']}/events"
    client.post(base, json={"month": "2027-10", "kind": "special_repayment", "value": "10000"})

    outlook = {
        p["month"]: p for p in client.get("/api/outlook", params={"years": 3}).json()["points"]
    }
    series = {
        p["month"]: p
        for p in client.get(
            "/api/cashflow/series", params={"from": "2027-09", "to": "2027-11"}
        ).json()
    }
    # the actual month carries the special repayment, the outlook stays on the regular budget
    assert series["2027-10"]["financing"] > outlook["2027-10"]["financing"] + 9000
    assert outlook["2027-10"]["financing"] == pytest.approx(outlook["2027-09"]["financing"], abs=50)


def test_delete_financing_removes_it_from_all_views(client: TestClient) -> None:
    _login(client)
    f = _create(client, LOAN)
    client.post(
        f"/api/financings/{f['id']}/events",
        json={"month": "2027-10", "kind": "special_repayment", "value": "1000"},
    )
    assert client.delete(f"/api/financings/{f['id']}").status_code == 204
    assert client.get(f"/api/financings/{f['id']}").status_code == 404
    assert client.get("/api/financings").json() == []
    assert client.get("/api/cashflow/summary", params={"month": "2026-10"}).json()["financing"] == 0
    assert any(e["action"] == "delete" for e in client.get("/api/audit").json())
    assert client.delete(f"/api/financings/{f['id']}").status_code == 404


def test_bauspar_fee_can_be_entered_in_euros(client: TestClient) -> None:
    _login(client)
    body = {**BAUSPAR, "contract_sum": "27000", "fee_amount": "432"}
    del body["fee_percent"]
    f = _create(client, body)
    assert f["schedule"][0]["fee"] == 432.0
    assert f["input"]["fee_amount"] == "432"


def test_bauspar_fee_percent_is_still_capped(client: TestClient) -> None:
    _login(client)
    r = client.post("/api/financings", json={**BAUSPAR, "fee_percent": "432"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == "fee_percent"


CREDIT_LINE = {
    "kind": "credit_line",
    "name": "Rahmenkredit",
    "limit": "20000",
    "balance": "10000",
    "annual_rate_percent": "6",
    "monthly_payment": "500",
    "start": "2026-10",
}


def test_credit_line_shows_limit_and_what_is_still_available(client: TestClient) -> None:
    _login(client)
    f = _create(client, CREDIT_LINE)
    assert f["kind"] == "credit_line"
    assert f["credit_limit"] == 20000
    assert f["remaining_debt"] == 10000
    assert f["available"] == 10000
    assert f["regular_payment"] == 500


def test_credit_line_deposit_withdrawal_and_rate_change(client: TestClient) -> None:
    _login(client)
    f = _create(client, CREDIT_LINE)
    url = f"/api/financings/{f['id']}/events"
    r = client.post(url, json={"month": "2026-12", "kind": "drawdown", "value": "4000"})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["schedule"] if x["month"] == "2026-12")
    assert row["drawn"] == 4000
    assert (
        client.post(
            url, json={"month": "2027-02", "kind": "special_repayment", "value": "1000"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            url, json={"month": "2027-03", "kind": "payment_change", "value": "700"}
        ).status_code
        == 200
    )
    # the limit is a hard ceiling for everything that is drawn at one time
    over = client.post(url, json={"month": "2026-12", "kind": "drawdown", "value": "9000"})
    assert over.status_code == 422
    assert "Rahmen" in over.json()["detail"]


def test_credit_line_cannot_start_above_its_limit(client: TestClient) -> None:
    _login(client)
    r = client.post("/api/financings", json={**CREDIT_LINE, "balance": "25000"})
    assert r.status_code == 422


def test_drawdown_is_not_a_cashflow_outflow(client: TestClient) -> None:
    _login(client)
    f = _create(client, CREDIT_LINE)
    client.post(
        f"/api/financings/{f['id']}/events",
        json={"month": "2026-12", "kind": "drawdown", "value": "4000"},
    )
    summary = client.get("/api/cashflow/summary?month=2026-12").json()
    assert (
        summary["financing"] == 500 or summary["financing"] > 0
    )  # interest + repayment only, no negative flow
    assert summary["financing"] < 1000
