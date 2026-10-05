from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_cashflow_api import _category_id, _create_item, _login_new_household


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kontor.api.cashflow.current_month", lambda: date(2026, 10, 1))


def _order(client: TestClient, parent: int | None, kind: str) -> list[str]:
    cats = client.get("/api/categories").json()
    return [c["name"] for c in cats if c["parent_id"] == parent and c["kind"] == kind]


def test_rename_and_move_a_category(client: TestClient) -> None:
    _login_new_household(client)
    wohnen = _category_id(client, "Wohnen")
    auto = _category_id(client, "Auto")
    r = client.put(f"/api/categories/{auto}", json={"name": "Fahrzeuge", "parent_id": wohnen})
    assert r.status_code == 200
    assert r.json()["name"] == "Fahrzeuge" and r.json()["parent_id"] == wohnen
    back = client.put(f"/api/categories/{auto}", json={"name": "Auto", "parent_id": None})
    assert back.json()["parent_id"] is None


def test_move_rules(client: TestClient) -> None:
    _login_new_household(client)
    wohnen = _category_id(client, "Wohnen")
    kinder = _category_id(client, "Kinder")
    gehalt = _category_id(client, "Gehalt")
    nebenkosten = _category_id(client, "Nebenkosten")
    # a group with sub-categories cannot become a sub-category
    assert (
        client.put(
            f"/api/categories/{wohnen}", json={"name": "Wohnen", "parent_id": kinder}
        ).status_code
        == 422
    )
    # not under itself, not under a sub-category, not under another kind
    assert (
        client.put(
            f"/api/categories/{kinder}", json={"name": "Kinder", "parent_id": kinder}
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/categories/{kinder}", json={"name": "Kinder", "parent_id": nebenkosten}
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/categories/{kinder}", json={"name": "Kinder", "parent_id": gehalt}
        ).status_code
        == 422
    )
    assert client.put("/api/categories/99999", json={"name": "x"}).status_code == 422


def test_reorder_siblings(client: TestClient) -> None:
    _login_new_household(client)
    before = _order(client, None, "expense")
    second = _category_id(client, before[1])
    client.post(f"/api/categories/{second}/move", json={"direction": "up"})
    after = _order(client, None, "expense")
    assert after[:2] == [before[1], before[0]]
    # moving the first one further up changes nothing
    client.post(f"/api/categories/{second}/move", json={"direction": "up"})
    assert _order(client, None, "expense") == after
    client.post(f"/api/categories/{second}/move", json={"direction": "down"})
    assert _order(client, None, "expense") == before


def test_new_categories_are_appended_in_order(client: TestClient) -> None:
    _login_new_household(client)
    for name in ("Zeta", "Alpha"):
        client.post("/api/categories", json={"name": name, "kind": "expense"})
    assert _order(client, None, "expense")[-2:] == ["Zeta", "Alpha"]


def test_delete_needs_a_target_for_items_and_moves_them(client: TestClient) -> None:
    _login_new_household(client)
    item = _create_item(client, "Kita", "Kinder", "300")
    kinder = _category_id(client, "Kinder")
    abos = _category_id(client, "Abos")
    gehalt = _category_id(client, "Gehalt")
    cats = {c["id"]: c for c in client.get("/api/categories").json()}
    assert cats[kinder]["item_count"] == 1

    # sub-categories first
    assert client.delete(f"/api/categories/{kinder}").status_code == 409
    for c in cats.values():
        if c["parent_id"] == kinder:
            assert client.delete(f"/api/categories/{c['id']}").status_code == 204
    # items need a target of the same kind
    assert client.delete(f"/api/categories/{kinder}").status_code == 409
    assert client.delete(f"/api/categories/{kinder}", params={"move_to": gehalt}).status_code == 422
    assert client.delete(f"/api/categories/{kinder}", params={"move_to": kinder}).status_code == 422
    assert client.delete(f"/api/categories/{kinder}", params={"move_to": abos}).status_code == 204

    items = client.get("/api/cashflow/items", params={"month": "2026-10"}).json()
    assert next(i for i in items if i["id"] == item["id"])["category_id"] == abos
    assert kinder not in {c["id"] for c in client.get("/api/categories").json()}


def test_delete_empty_category_and_audit(client: TestClient) -> None:
    _login_new_household(client)
    created = client.post("/api/categories", json={"name": "Haustiere", "kind": "expense"}).json()
    assert client.delete(f"/api/categories/{created['id']}").status_code == 204
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert "delete" in actions and "create" in actions


def test_categories_are_private_to_the_household(client: TestClient) -> None:
    _login_new_household(client)
    mine = _category_id(client, "Wohnen")
    other = TestClient(client.app)
    _login_new_household(other, "other@example.com")
    assert other.put(f"/api/categories/{mine}", json={"name": "x"}).status_code == 422
    assert other.delete(f"/api/categories/{mine}").status_code == 422
    assert other.post(f"/api/categories/{mine}/move", json={"direction": "up"}).status_code == 422


def test_direct_items_of_a_group_with_sub_categories_show_in_the_sankey(
    client: TestClient,
) -> None:
    _login_new_household(client)
    _create_item(client, "Miete", "Wohnen", "1000")
    _create_item(client, "Strom", "Strom und Gas", "100")
    sankey = client.get("/api/cashflow/sankey", params={"month": "2026-10"}).json()
    names = {n["name"] for n in sankey["nodes"]}
    assert {"Wohnen", "Strom und Gas", "Ohne Unterkategorie"} <= names
    ids = [n["id"] for n in sankey["nodes"]]
    assert len(ids) == len(set(ids))
    wohnen = next(n["id"] for n in sankey["nodes"] if n["name"] == "Wohnen")
    out = sum(link["value"] for link in sankey["links"] if link["source"] == wohnen)
    assert out == 1100
