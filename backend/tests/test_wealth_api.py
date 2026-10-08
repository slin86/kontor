from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_financing_api import BAUSPAR, _create, _login

TODAY = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    for target in (
        "kontor.api.wealth.current_month",
        "kontor.api.depot.current_month",
        "kontor.api.financings.current_month",
        "kontor.services.financing_book.current_month",
    ):
        try:
            monkeypatch.setattr(target, lambda: TODAY)
        except AttributeError:
            continue


def _asset(client: TestClient, **over: object) -> dict:
    body = {
        "name": "Haus",
        "kind": "property",
        "value": "400000",
        "as_of": "2026-10",
        "growth_percent": "2",
        **over,
    }
    r = client.post("/api/assets", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_assets_crud(client: TestClient) -> None:
    _login(client)
    a = _asset(client)
    assert client.get("/api/assets").json()[0]["name"] == "Haus"
    r = client.put(f"/api/assets/{a['id']}", json={**a, "value": "410000", "as_of": "2026-10"})
    assert r.status_code == 200 and r.json()["value"] == 410000
    assert client.delete(f"/api/assets/{a['id']}").status_code == 204
    assert client.get("/api/assets").json() == []


def test_net_worth_combines_assets_and_debts(client: TestClient) -> None:
    _login(client)
    _asset(client)
    _create(client, {**BAUSPAR, "start": "2026-01", "allocation": "2036-01"})
    w = client.get("/api/wealth", params={"years": 5, "back_months": 6}).json()
    names = {s["name"]: s["group"] for s in w["series"]}
    assert names["Haus"] == "asset"
    now = next(p for p in w["points"] if p["month"] == "2026-10")
    assert now["assets"] >= 400000
    assert now["net"] == pytest.approx(now["assets"] - now["debts"])
    growth = [p["net"] for p in w["points"]]
    assert growth[-1] > growth[0]  # the house grows 2 % a year
    for p in w["points"]:
        assert len(p["values"]) == len(w["series"])


def test_inflation_reduces_future_values(client: TestClient) -> None:
    _login(client)
    _asset(client, growth_percent="0")
    plain = client.get("/api/wealth", params={"years": 10}).json()["points"][-1]["net"]
    real = client.get("/api/wealth", params={"years": 10, "inflation": 2}).json()["points"][-1][
        "net"
    ]
    assert real < plain
