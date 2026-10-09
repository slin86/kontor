from fastapi.testclient import TestClient

from tests.test_people_api import _register


def _names(client: TestClient) -> list[str]:
    return [h["name"] for h in client.get("/api/households").json()]


def test_second_household_is_independent(client: TestClient) -> None:
    _register(client)
    first = client.get("/api/household").json()
    client.post("/api/people", json={"name": "Kind"})
    assert {p["name"] for p in client.get("/api/people").json()} == {"Nils", "Kind"}
    cats_before = len(client.get("/api/categories").json())

    r = client.post("/api/households", json={"name": "Ferienhaus"})
    assert r.status_code == 201
    assert [h["is_active"] for h in r.json()] == [False, True]
    second = client.get("/api/household").json()
    assert second["id"] != first["id"] and second["name"] == "Ferienhaus"
    assert second["invite_code"] != first["invite_code"]
    # nothing leaks over: only the own person, but the default categories are seeded
    assert [p["name"] for p in client.get("/api/people").json()] == ["Nils"]
    assert len(client.get("/api/categories").json()) == cats_before
    assert client.get("/api/auth/me").json()["household"]["id"] == second["id"]

    switched = client.post(f"/api/households/{first['id']}/switch")
    assert [h["is_active"] for h in switched.json()] == [True, False]
    assert {p["name"] for p in client.get("/api/people").json()} == {"Nils", "Kind"}


def test_cannot_switch_to_a_foreign_household(client: TestClient) -> None:
    _register(client)
    other = TestClient(client.app)
    other_body = {
        "email": "fremd@example.com",
        "password": "correct-horse-battery",
        "display_name": "Fremd",
        "household_name": "Fremd",
    }
    assert other.post("/api/auth/register", json=other_body).status_code == 201
    foreign = other.get("/api/household").json()["id"]
    assert client.post(f"/api/households/{foreign}/switch").status_code == 404


def test_join_with_invite_code_and_remove_keeps_the_account(client: TestClient) -> None:
    _register(client)
    code = client.get("/api/household").json()["invite_code"]
    other = TestClient(client.app)
    _register(other, "partner@example.com", household_name="Partner", display_name="Partnerin")
    own = other.get("/api/household").json()["id"]

    assert other.post("/api/households/join", json={"invite_code": "nope"}).status_code == 404
    joined = other.post("/api/households/join", json={"invite_code": code})
    assert joined.status_code == 200 and len(joined.json()) == 2
    assert {p["name"] for p in client.get("/api/people").json()} == {"Nils", "Partnerin"}
    assert other.post("/api/households/join", json={"invite_code": code}).status_code == 200
    assert len(other.get("/api/households").json()) == 2  # joining twice adds nothing

    members = client.get("/api/household").json()["members"]
    partner = next(m for m in members if not m["is_me"])
    assert client.delete(f"/api/household/members/{partner['id']}").status_code == 204
    # the account survives in its own household and is switched there
    assert other.get("/api/auth/me").status_code == 200
    assert other.get("/api/household").json()["id"] == own
    assert len(other.get("/api/households").json()) == 1


def test_profile_rename_applies_to_every_household(client: TestClient) -> None:
    _register(client)
    client.post("/api/households", json={"name": "Zweit"})
    client.put("/api/auth/profile", json={"display_name": "Nils H."})
    assert client.get("/api/people").json()[0]["name"] == "Nils H."
    first = client.get("/api/households").json()[0]["id"]
    client.post(f"/api/households/{first}/switch")
    assert client.get("/api/people").json()[0]["name"] == "Nils H."
