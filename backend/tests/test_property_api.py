from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_financing_api import LOAN, _create, _login
from tests.test_wealth_api import fixed_today  # noqa: F401

TODAY = date(2026, 10, 1)

HOUSE = {
    "name": "Wohnung Hamburg",
    "usage": "rented",
    "purchase_month": "2020-01",
    "purchase_price": "250000",
    "closing_costs": "20000",
    "value": "300000",
    "value_as_of": "2026-10",
    "growth_percent": "2",
    "share_percent": "50",
}


def _house(client: TestClient, **over: object) -> dict:
    r = client.post("/api/properties", json={**HOUSE, **over})
    assert r.status_code == 201, r.text
    return r.json()


def test_property_value_share_and_works(client: TestClient) -> None:
    _login(client)
    p = _house(client)
    assert p["current_value"] == 300000
    assert p["my_value"] == 150000
    r = client.post(
        f"/api/properties/{p['id']}/works",
        json={"month": "2026-11", "name": "Bad", "cost": "10000", "value_gain": "15000"},
    )
    assert r.status_code == 201
    out = r.json()
    assert len(out["works"]) == 1
    assert out["invested"] == 270000  # a future work is not yet paid
    w = client.get("/api/wealth", params={"years": 2, "back_months": 0}).json()
    idx = next(i for i, s in enumerate(w["series"]) if s["group"] == "property")
    values = {pt["month"]: pt["values"][idx] for pt in w["points"]}
    assert values["2026-10"] == 150000
    assert values["2026-11"] > 150000 + 7000  # half of the 15 000 gain, plus growth
    r = client.delete(f"/api/properties/{p['id']}/works/{out['works'][0]['id']}")
    assert r.json()["works"] == []


def test_links_drive_equity_and_yield(client: TestClient) -> None:
    _login(client)
    p = _house(client, share_percent="100")
    f = _create(client, {**LOAN, "start": "2026-01"})
    cats = client.get("/api/categories").json()
    income = next(c for c in cats if c["kind"] == "income")
    item = client.post(
        "/api/cashflow/items",
        json={
            "name": "Miete",
            "category_id": income["id"],
            "amount": "1200",
            "frequency": "monthly",
            "valid_from": "2026-01",
        },
    )
    assert item.status_code == 201, item.text
    r = client.put(
        f"/api/properties/{p['id']}/links",
        json={"financing_ids": [f["id"]], "item_ids": [item.json()["id"]]},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["income"] == 1200
    assert out["debt"] > 0
    assert out["equity"] == pytest.approx(out["my_value"] - out["debt"])
    assert out["net_cashflow"] == pytest.approx(1200 - out["financing_payment"])
    assert out["yield_percent"] == pytest.approx(1200 * 12 / 300000 * 100, abs=0.01)
    bad = client.put(f"/api/properties/{p['id']}/links", json={"item_ids": [9999]})
    assert bad.status_code == 422
    assert client.put(f"/api/properties/{p['id']}/links", json={}).json()["debt"] == 0


def test_delete_unlinks(client: TestClient) -> None:
    _login(client)
    p = _house(client)
    f = _create(client, {**LOAN, "start": "2026-01"})
    client.put(f"/api/properties/{p['id']}/links", json={"financing_ids": [f["id"]]})
    assert client.delete(f"/api/properties/{p['id']}").status_code == 204
    assert client.get("/api/properties").json() == []
    assert client.get(f"/api/financings/{f['id']}").status_code == 200
