"""Password reset: request -> emailed token -> reset -> old sessions and
old password stop working. Same single-use token mechanism as email
verification (fastauthx.service.AuthService._create_verification_token)."""

from httpx import AsyncClient

PASSWORD = "supersecret123"
NEW_PASSWORD = "a-new-secret-456"


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Test User"},
    )
    assert response.status_code == 201
    return response.json()


async def test_forgot_password_does_not_reveal_whether_email_exists(
    client: AsyncClient,
) -> None:
    registered = await client.post(
        "/auth/forgot-password", json={"email": "unregistered@example.com"}
    )
    assert registered.status_code == 202


async def test_forgot_password_sends_reset_email_for_known_user(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    await _register(client, unique_email)
    fake_email_sender.sent.clear()

    response = await client.post("/auth/forgot-password", json={"email": unique_email})
    assert response.status_code == 202

    sent = [e for e in fake_email_sender.sent if e.to == unique_email]
    assert len(sent) == 1
    assert sent[0].subject == "Reset your password"


async def test_reset_password_with_valid_token_changes_password(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    await _register(client, unique_email)
    fake_email_sender.sent.clear()
    await client.post("/auth/forgot-password", json={"email": unique_email})
    token = fake_email_sender.extract_token(unique_email)

    reset = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reset.status_code == 200

    old_login = await client.post(
        "/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/auth/login", json={"email": unique_email, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


async def test_reset_password_token_is_single_use(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    await _register(client, unique_email)
    fake_email_sender.sent.clear()
    await client.post("/auth/forgot-password", json={"email": unique_email})
    token = fake_email_sender.extract_token(unique_email)

    first = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert first.status_code == 200

    second = await client.post(
        "/auth/reset-password", json={"token": token, "new_password": "yet-another-1"}
    )
    assert second.status_code == 400


async def test_reset_password_revokes_existing_sessions(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    await _register(client, unique_email)
    refresh_cookie_before = client.cookies["refresh_token"]

    fake_email_sender.sent.clear()
    await client.post("/auth/forgot-password", json={"email": unique_email})
    token = fake_email_sender.extract_token(unique_email)
    await client.post(
        "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}
    )

    client.cookies.set("refresh_token", refresh_cookie_before)
    response = await client.post("/auth/refresh")
    assert response.status_code == 401
