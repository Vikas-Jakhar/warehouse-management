from tests.conftest import register_and_login


def test_register_creates_customer_and_owner(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "customer_name": "Globex Inc",
            "full_name": "Jane Owner",
            "email": "jane@globex.example.com",
            "password": "Sup3rSecret!",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body


def test_register_duplicate_email_rejected(client):
    payload = {
        "customer_name": "Globex Inc",
        "full_name": "Jane Owner",
        "email": "dup@globex.example.com",
        "password": "Sup3rSecret!",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_success_and_wrong_password(client):
    client.post(
        "/api/v1/auth/register",
        json={"customer_name": "Initech", "full_name": "Bob", "email": "bob@initech.example.com", "password": "Sup3rSecret!"},
    )
    ok = client.post("/api/v1/auth/login", json={"email": "bob@initech.example.com", "password": "Sup3rSecret!"})
    assert ok.status_code == 200

    bad = client.post("/api/v1/auth/login", json={"email": "bob@initech.example.com", "password": "wrong"})
    assert bad.status_code == 401


def test_me_requires_authentication(client):
    resp = client.get("/api/v1/users/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    headers = register_and_login(client, "Hooli", "user@hooli.example.com")
    resp = client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "user@hooli.example.com"
    assert body["role"] == "owner"


def test_refresh_token_issues_new_access_token(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"customer_name": "Umbrella", "full_name": "Rita", "email": "r@umbrella.example.com", "password": "Sup3rSecret!"},
    )
    refresh_token = resp.json()["refresh_token"]
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert "access_token" in refreshed.json()


def test_forgot_password_always_returns_202(client):
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@nowhere.example.com"})
    assert resp.status_code == 202
