from datetime import date

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kontor.api.catalog.current_month", lambda: date(2026, 10, 1))


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


def test_search_by_name_isin_and_index(client: TestClient) -> None:
    _login(client)
    everything = client.get("/api/catalog", params={"limit": 200}).json()
    assert everything["total"] >= 50
    assert "MSCI World" in everything["facets"]["indexes"]
    isins = [e["isin"] for e in everything["items"]]
    assert len(isins) == len(set(isins)), "reference data must be seeded exactly once"

    by_isin = client.get("/api/catalog", params={"q": "IE00B4L5Y983"}).json()
    assert [e["name"] for e in by_isin["items"]] == ["iShares Core MSCI World UCITS ETF USD (Acc)"]
    assert by_isin["items"][0]["ter_percent"] == 0.2 and by_isin["items"][0]["builtin"]

    words = client.get("/api/catalog", params={"q": "vanguard all-world"}).json()
    assert words["total"] == 2 and all("Vanguard" in e["name"] for e in words["items"])

    index = client.get("/api/catalog", params={"index": "S&P 500", "limit": 200}).json()
    assert index["total"] > 5 and {e["index_name"] for e in index["items"]} == {"S&P 500"}


def test_filters_and_sorting(client: TestClient) -> None:
    _login(client)
    cheap = client.get(
        "/api/catalog",
        params={
            "index": "MSCI World",
            "max_ter": "0.1",
            "distribution": "accumulating",
            "sort": "ter",
        },
    ).json()
    ters = [e["ter_percent"] for e in cheap["items"]]
    assert ters and ters == sorted(ters) and max(ters) <= 0.1
    assert {e["distribution"] for e in cheap["items"]} == {"accumulating"}

    by_size = client.get("/api/catalog", params={"index": "MSCI World"}).json()["items"]
    sizes = [e["fund_size_m_eur"] for e in by_size]
    assert sizes == sorted(sizes, reverse=True)

    page = client.get("/api/catalog", params={"limit": 5, "offset": 5}).json()
    assert len(page["items"]) == 5 and page["total"] > 5


def test_own_entries_are_private_and_deletable(client: TestClient) -> None:
    _login(client)
    body = {
        "kind": "private_equity",
        "name": "Mein PE Fonds",
        "ter_percent": "2.5",
        "index_name": "Buyout",
    }
    created = client.post("/api/catalog", json=body)
    assert created.status_code == 201, created.text
    entry = created.json()
    assert not entry["builtin"] and entry["source"] == "Eigener Eintrag"
    assert client.get("/api/catalog", params={"q": "Mein PE"}).json()["total"] == 1

    client.post("/api/auth/logout")
    _login(client, "other@example.com")
    assert client.get("/api/catalog", params={"q": "Mein PE"}).json()["total"] == 0
    assert client.delete(f"/api/catalog/{entry['id']}").status_code == 404

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "nils@example.com", "password": PASSWORD})
    client.headers["X-CSRF-Token"] = client.cookies.get("kontor_csrf") or ""
    assert client.delete(f"/api/catalog/{entry['id']}").status_code == 204
    assert client.get("/api/catalog", params={"q": "Mein PE"}).json()["total"] == 0


def test_built_in_entries_cannot_be_deleted(client: TestClient) -> None:
    _login(client)
    first = client.get("/api/catalog").json()["items"][0]
    assert client.delete(f"/api/catalog/{first['id']}").status_code == 404


def test_compare_shows_what_the_ter_costs(client: TestClient) -> None:
    _login(client)
    items = {
        e["isin"]: e for e in client.get("/api/catalog", params={"limit": 200}).json()["items"]
    }
    expensive = items["IE00B0M62Q58"]["id"]  # iShares MSCI World (Dist), 0.50 %
    cheap = items["IE00B60SX394"]["id"]  # Invesco MSCI World, 0.05 %
    r = client.get(
        "/api/catalog/compare",
        params={"ids": f"{expensive},{cheap}", "monthly": 300, "years": 30, "expected_return": 6},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["paid_in"] == 300 * 360
    res = {x["entry"]["id"]: x for x in body["results"]}
    assert res[cheap]["extra_vs_cheapest"] == 0
    assert res[expensive]["extra_vs_cheapest"] > 20000
    assert res[expensive]["total_costs"] > res[cheap]["total_costs"] > 0
    assert res[cheap]["final_value"] > res[expensive]["final_value"]


def test_compare_validates_input(client: TestClient) -> None:
    _login(client)
    assert client.get("/api/catalog/compare", params={"ids": "x"}).status_code == 422
    assert client.get("/api/catalog/compare", params={"ids": "999999"}).status_code == 404
    too_many = ",".join(str(i) for i in range(1, 9))
    assert client.get("/api/catalog/compare", params={"ids": too_many}).status_code == 422
