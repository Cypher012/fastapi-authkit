"""Email verification, backed by the `verification` table and sent
through the EmailSender port. FakeEmailSender in conftest stands in for
Resend/console/whatever a host app configures."""

from httpx import AsyncClient

PASSWORD = "supersecret123"


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Test User"},
    )
    assert response.status_code == 201
    return response.json()


async def test_register_sends_a_verification_email(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    await _register(client, unique_email)

    sent = [e for e in fake_email_sender.sent if e.to == unique_email]
    assert len(sent) == 1
    assert sent[0].subject == "Verify your email address"


async def test_verify_email_with_valid_token_marks_user_verified(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    body = await _register(client, unique_email)
    token = fake_email_sender.extract_token(unique_email)

    response = await client.post("/auth/verify-email", json={"token": token})
    assert response.status_code == 200

    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.json()["email_verified"] is True


async def test_verify_email_token_is_single_use(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    await _register(client, unique_email)
    token = fake_email_sender.extract_token(unique_email)

    first = await client.post("/auth/verify-email", json={"token": token})
    assert first.status_code == 200

    second = await client.post("/auth/verify-email", json={"token": token})
    assert second.status_code == 400


async def test_verify_email_rejects_unknown_token(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/verify-email", json={"token": "not-a-real-token"}
    )
    assert response.status_code == 400


async def test_resend_verification_email_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/auth/verify-email/resend")
    assert response.status_code == 401


async def test_resend_verification_email_sends_a_new_token(
    client: AsyncClient, unique_email: str, fake_email_sender
) -> None:
    body = await _register(client, unique_email)
    first_token = fake_email_sender.extract_token(unique_email)

    response = await client.post(
        "/auth/verify-email/resend",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert response.status_code == 202

    second_token = fake_email_sender.extract_token(unique_email)
    assert second_token != first_token

    verify = await client.post("/auth/verify-email", json={"token": second_token})
    assert verify.status_code == 200
