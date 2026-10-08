from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.test_broker_csv import TR_SAMPLE

PASSWORD = "correct-horse-battery"
TODAY = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    for target in (
        "kontor.api.depot.current_month",
        "kontor.api.actuals.current_month",
        "kontor.api.cashflow.current_month",
    ):
        monkeypatch.setattr(target, lambda: TODAY)


def _register(client: TestClient, email: str = "nils@example.com", **extra: str) -> dict:
    body = {"email": email, "password": PASSWORD, "display_name": "Nils", **extra}
    if "invite_code" not in extra:
        body["household_name"] = "Haushalt"
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201, r.text
    client.headers["X-CSRF-Token"] = client.cookies.get("kontor_csrf") or ""
    return r.json()


def _position(client: TestClient, person_id: int | None = None, **over: str) -> dict:
    body = {
        "kind": "etf",
        "name": "MSCI World",
        "isin": "IE00B60SX394",
        "expected_return_percent": "6",
        "cost_percent": "0.2",
        "entry_fee_percent": "0",
        "start": "2026-01",
        "start_value": "1000",
        "monthly_rate": "100",
        **over,
    }
    if person_id is not None:
        body["person_id"] = person_id
    r = client.post("/api/depot/instruments", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _child(client: TestClient, name: str = "Margo") -> dict:
    r = client.post("/api/people", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_registration_creates_a_person_for_the_user(client: TestClient) -> None:
    _register(client)
    people = client.get("/api/people").json()
    assert [(p["name"], p["has_login"], p["is_me"]) for p in people] == [("Nils", True, True)]


def test_children_can_be_added_renamed_and_removed(client: TestClient) -> None:
    _register(client)
    kid = _child(client)
    assert kid["has_login"] is False and kid["is_me"] is False
    renamed = client.put(f"/api/people/{kid['id']}", json={"name": "Margo K."}).json()
    assert renamed["name"] == "Margo K."
    assert client.delete(f"/api/people/{kid['id']}").status_code == 204
    assert len(client.get("/api/people").json()) == 1


def test_a_person_with_positions_or_a_login_cannot_be_deleted(client: TestClient) -> None:
    _register(client)
    me = client.get("/api/people").json()[0]
    assert client.delete(f"/api/people/{me['id']}").status_code == 409
    kid = _child(client)
    _position(client, kid["id"])
    r = client.delete(f"/api/people/{kid['id']}")
    assert r.status_code == 409 and "Depotpositionen" in r.json()["detail"]


def test_positions_belong_to_a_person_and_default_to_the_signed_in_one(client: TestClient) -> None:
    _register(client)
    me = client.get("/api/people").json()[0]
    kid = _child(client)
    mine = _position(client, name="Meiner")
    theirs = _position(client, kid["id"], name="Kinder-ETF")
    assert mine["person_id"] == me["id"] and theirs["person_id"] == kid["id"]

    only_kid = client.get(f"/api/depot?person={kid['id']}").json()
    assert [i["name"] for i in only_kid["instruments"]] == ["Kinder-ETF"]
    everyone = client.get("/api/depot").json()
    assert {i["name"] for i in everyone["instruments"]} == {"Meiner", "Kinder-ETF"}
    assert everyone["base_rate"] == 200


def test_a_position_can_be_handed_to_another_person(client: TestClient) -> None:
    _register(client)
    kid = _child(client)
    p = _position(client)
    r = client.put(f"/api/depot/instruments/{p['id']}/person", json={"person_id": kid["id"]})
    assert r.status_code == 200 and r.json()["person_id"] == kid["id"]
    assert client.get(f"/api/depot?person={kid['id']}").json()["instruments"][0]["id"] == p["id"]


def test_tax_settings_and_projection_are_per_person(client: TestClient) -> None:
    _register(client)
    me = client.get("/api/people").json()[0]
    kid = _child(client)
    _position(client, name="Meiner", start_value="50000", monthly_rate="0")
    _position(client, kid["id"], name="Kinder-ETF", start_value="50000", monthly_rate="0")
    client.put(
        "/api/tax/settings?person=" + str(me["id"]),
        json={"church_tax_percent": 9, "allowance": "0", "base_interest_percent": "3.2"},
    )
    assert client.get(f"/api/tax/settings?person={kid['id']}").json()["church_tax_percent"] == 0
    assert client.get("/api/tax/settings").json()["church_tax_percent"] == 9  # default: me

    def last_tax(person: int | None) -> float:
        url = "/api/depot/projection?years=20" + (f"&person={person}" if person else "")
        p = client.get(url).json()["points"][-1]
        return p["tax_on_sale"] + p["tax_paid"]

    both = last_tax(None)
    assert both == pytest.approx(last_tax(me["id"]) + last_tax(kid["id"]), abs=0.05)
    assert last_tax(me["id"]) > last_tax(kid["id"])  # church tax and no allowance


def test_actual_data_follows_the_person(client: TestClient) -> None:
    _register(client)
    kid = _child(client)
    _position(client, name="Meiner")
    _position(client, kid["id"], name="Kinder-ETF", isin="IE00B4L5Y983")
    ours = client.get("/api/actuals/compare").json()["instruments"]
    assert len(ours) == 2
    only = client.get(f"/api/actuals/compare?person={kid['id']}").json()["instruments"]
    assert [i["name"] for i in only] == ["Kinder-ETF"]


def test_csv_import_matches_the_chosen_persons_positions(client: TestClient) -> None:
    _register(client)
    kid = _child(client)
    mine = _position(client, name="Meiner")  # holds IE00B60SX394, the fund of the sample file
    theirs = _position(client, kid["id"], name="Kinder-ETF")
    for_kid = client.post(
        "/api/actuals/import/preview", json={"csv": TR_SAMPLE, "person_id": kid["id"]}
    ).json()
    targets = {r["instrument_id"] for r in for_kid["rows"] if r["isin"] == "IE00B60SX394"}
    assert targets == {theirs["id"]}
    default = client.post("/api/actuals/import/preview", json={"csv": TR_SAMPLE}).json()
    assert {r["instrument_id"] for r in default["rows"] if r["isin"] == "IE00B60SX394"} == {
        mine["id"]
    }
    client.post("/api/actuals/import", json={"csv": TR_SAMPLE, "person_id": kid["id"]})
    kid_txs = client.get(f"/api/actuals/transactions?person={kid['id']}").json()
    assert len(kid_txs) == 3
    assert client.get("/api/actuals/transactions").json()  # the household sees everything


def test_other_households_people_are_not_reachable(client: TestClient) -> None:
    _register(client, "a@example.com")
    kid = _child(client)
    client.cookies.clear()
    _register(client, "b@example.com")
    assert client.get(f"/api/depot?person={kid['id']}").status_code == 404
    assert client.put(f"/api/people/{kid['id']}", json={"name": "x"}).status_code == 404
    assert (
        client.post("/api/depot/instruments", json={**_BODY, "person_id": kid["id"]}).status_code
        == 404
    )


_BODY = {
    "kind": "etf",
    "name": "X",
    "expected_return_percent": "6",
    "start": "2026-01",
}


# --- household administration ------------------------------------------------------------


def test_invite_code_can_be_renewed_and_new_members_get_a_person(client: TestClient) -> None:
    _register(client)
    old = client.get("/api/household").json()["invite_code"]
    new = client.post("/api/household/invite-code").json()["invite_code"]
    assert new != old

    client.cookies.clear()
    joined = client.post(
        "/api/auth/register",
        json={
            "email": "partner@example.com",
            "password": PASSWORD,
            "display_name": "Partnerin",
            "invite_code": old,
        },
    )
    assert joined.status_code == 404  # the old code no longer works
    _register(client, "partner@example.com", invite_code=new, display_name="Partnerin")
    household = client.get("/api/household").json()
    assert [m["display_name"] for m in household["members"]] == ["Nils", "Partnerin"]
    assert {p["name"] for p in client.get("/api/people").json()} == {"Nils", "Partnerin"}


def test_removing_a_member_keeps_their_depot_as_a_person_without_login(client: TestClient) -> None:
    _register(client)
    code = client.get("/api/household").json()["invite_code"]
    other = TestClient(client.app)
    _register(other, "partner@example.com", invite_code=code, display_name="Partnerin")
    partner_person = next(p for p in other.get("/api/people").json() if p["is_me"])
    _position(other, partner_person["id"], name="Ihr ETF")

    members = client.get("/api/household").json()["members"]
    partner = next(m for m in members if not m["is_me"])
    me = next(m for m in members if m["is_me"])
    assert client.delete(f"/api/household/members/{me['id']}").status_code == 409
    assert client.delete(f"/api/household/members/{partner['id']}").status_code == 204

    assert other.get("/api/auth/me").status_code == 401  # their sessions are gone
    left = next(p for p in client.get("/api/people").json() if p["name"] == "Partnerin")
    assert left["has_login"] is False and left["positions"] == 1


def test_household_rename_profile_and_password(client: TestClient) -> None:
    _register(client)
    assert client.put("/api/household", json={"name": "Familie"}).json()["name"] == "Familie"
    r = client.put("/api/auth/profile", json={"display_name": "Nils H."})
    assert r.status_code == 200
    assert client.get("/api/people").json()[0]["name"] == "Nils H."

    wrong = client.post(
        "/api/auth/password", json={"current_password": "nope", "new_password": "another-long-pass"}
    )
    assert wrong.status_code == 403
    ok = client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "another-long-pass"},
    )
    assert ok.status_code == 204
    client.cookies.clear()
    login = client.post(
        "/api/auth/login", json={"email": "nils@example.com", "password": "another-long-pass"}
    )
    assert login.status_code == 200
