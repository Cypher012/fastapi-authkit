"""Covers the core definition of done: register, log in, access a
protected endpoint, refresh an expired access token, and log out — plus
the failure paths that make those guarantees meaningful."""

from httpx import AsyncClient

PASSWORD = "supersecret123"


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Test User"},
    )
    assert response.status_code == 201
    return response.json()


async def test_register_returns_access_token_and_sets_refresh_cookie(
    client: AsyncClient, unique_email: str
) -> None:
    body = await _register(client, unique_email)

    assert body["access_token"]
    assert body["user"]["email"] == unique_email
    assert "refresh_token" in client.cookies


async def test_register_duplicate_email_is_rejected(
    client: AsyncClient, unique_email: str
) -> None:
    await _register(client, unique_email)

    response = await client.post(
        "/auth/register",
        json={"email": unique_email, "password": PASSWORD, "name": "Test User"},
    )

    assert response.status_code == 409


async def test_login_with_correct_password_succeeds(
    client: AsyncClient, unique_email: str
) -> None:
    await _register(client, unique_email)
    client.cookies.clear()

    response = await client.post(
        "/auth/login", json={"email": unique_email, "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" in client.cookies


async def test_login_with_wrong_password_is_rejected(
    client: AsyncClient, unique_email: str
) -> None:
    await _register(client, unique_email)

    response = await client.post(
        "/auth/login", json={"email": unique_email, "password": "wrong-password"}
    )

    assert response.status_code == 401


async def test_me_requires_a_valid_access_token(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_returns_current_user_with_valid_access_token(
    client: AsyncClient, unique_email: str
) -> None:
    body = await _register(client, unique_email)

    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == unique_email


async def test_refresh_rotates_the_refresh_token(
    client: AsyncClient, unique_email: str
) -> None:
    await _register(client, unique_email)
    old_refresh_cookie = client.cookies["refresh_token"]

    response = await client.post("/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert client.cookies["refresh_token"] != old_refresh_cookie


async def test_refresh_rejects_a_reused_rotated_token(
    client: AsyncClient, unique_email: str
) -> None:
    await _register(client, unique_email)
    old_refresh_cookie = client.cookies["refresh_token"]
    await client.post("/auth/refresh")

    client.cookies.set("refresh_token", old_refresh_cookie)
    response = await client.post("/auth/refresh")

    assert response.status_code == 401


async def test_logout_revokes_the_refresh_token(
    client: AsyncClient, unique_email: str
) -> None:
    await _register(client, unique_email)

    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 204

    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 401
