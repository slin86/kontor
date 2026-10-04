from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


def _register(client: TestClient, email: str = "nils@example.com", **extra: str) -> dict:
    payload = {
        "email": email,
        "password": PASSWORD,
        "display_name": "Nils",
        "household_name": "Familie",
        **extra,
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_register_creates_household_and_session(client: TestClient) -> None:
    body = _register(client)
    assert body["user"]["email"] == "nils@example.com"
    assert body["household"]["name"] == "Familie"
    assert body["household"]["invite_code"]
    assert client.get("/api/auth/me").status_code == 200


def test_register_requires_exactly_one_of_household_or_invite(client: TestClient) -> None:
    r = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": PASSWORD, "display_name": "A"},
    )
    assert r.status_code == 422


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    _register(client)
    r = client.post(
        "/api/auth/register",
        json={
            "email": "NILS@example.com",
            "password": PASSWORD,
            "display_name": "Other",
            "household_name": "X",
        },
    )
    assert r.status_code == 409


def test_second_member_joins_via_invite_code(client: TestClient) -> None:
    first = _register(client)
    code = first["household"]["invite_code"]
    client.cookies.clear()

    r = client.post(
        "/api/auth/register",
        json={
            "email": "partner@example.com",
            "password": PASSWORD,
            "display_name": "Partner",
            "invite_code": code,
        },
    )
    assert r.status_code == 201
    household = r.json()["household"]
    assert household["id"] == first["household"]["id"]
    assert {m["display_name"] for m in household["members"]} == {"Nils", "Partner"}


def test_invalid_invite_code(client: TestClient) -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "email": "p@example.com",
            "password": PASSWORD,
            "display_name": "P",
            "invite_code": "nope",
        },
    )
    assert r.status_code == 404


def test_login_and_wrong_password(client: TestClient) -> None:
    _register(client)
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login", json={"email": "nils@example.com", "password": "wrong"})
    assert bad.status_code == 401
    unknown = client.post("/api/auth/login", json={"email": "x@example.com", "password": "wrong"})
    assert unknown.status_code == 401

    ok = client.post("/api/auth/login", json={"email": "Nils@Example.com", "password": PASSWORD})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_logout_requires_csrf_and_invalidates_session(client: TestClient) -> None:
    _register(client)
    assert client.post("/api/auth/logout").status_code == 403

    csrf = client.cookies.get("kontor_csrf")
    assert csrf
    r = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_short_password_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/auth/register",
        json={
            "email": "s@example.com",
            "password": "short",
            "display_name": "S",
            "household_name": "H",
        },
    )
    assert r.status_code == 422
