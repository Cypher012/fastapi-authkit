"""AuthService.login_or_register_with_google carries all the actual
decision-making for Google sign-in (identity matching, account linking,
auto-verification). Tested directly against the real DB, bypassing HTTP
and Authlib's Google handshake entirely — that handshake is Authlib's
job to get right, not ours to re-test."""

from uuid import uuid4

import pytest

from fastauthx.exceptions import OAuthAccountError
from fastauthx.schemas import RegisterRequest
from fastauthx.service import AuthService, GoogleProfile

PASSWORD = "supersecret123"


def _google_profile(email: str, *, email_verified: bool = True) -> GoogleProfile:
    return GoogleProfile(
        sub=uuid4().hex,
        email=email,
        name="Google User",
        avatar_url="https://example.com/avatar.png",
        email_verified=email_verified,
    )


async def test_new_google_user_is_created_and_auto_verified(
    auth_service: AuthService, unique_email: str
) -> None:
    profile = _google_profile(unique_email)

    user, access_token, refresh_token = await auth_service.login_or_register_with_google(
        profile
    )

    assert user.email == unique_email
    assert user.email_verified is True
    assert access_token
    assert refresh_token


async def test_repeat_google_login_reuses_the_same_user(
    auth_service: AuthService, unique_email: str
) -> None:
    profile = _google_profile(unique_email)

    first_user, _, _ = await auth_service.login_or_register_with_google(profile)
    second_user, _, _ = await auth_service.login_or_register_with_google(profile)

    assert first_user.id == second_user.id


async def test_google_login_with_unverified_email_still_creates_new_user(
    auth_service: AuthService, unique_email: str
) -> None:
    """A brand-new account isn't "hijacking" anyone — there's no existing
    user to protect — so Google's email_verified=False here doesn't block
    account creation, it just means we don't inherit that trust."""
    profile = _google_profile(unique_email, email_verified=False)

    user, _, _ = await auth_service.login_or_register_with_google(profile)

    assert user.email == unique_email
    assert user.email_verified is False


async def test_google_login_links_to_existing_password_account_when_verified(
    auth_service: AuthService, unique_email: str
) -> None:
    registered = await auth_service.register(
        RegisterRequest(email=unique_email, password=PASSWORD, name="Password User")
    )
    password_user_id = registered[0].id

    profile = _google_profile(unique_email, email_verified=True)
    linked_user, _, _ = await auth_service.login_or_register_with_google(profile)

    assert linked_user.id == password_user_id
    assert linked_user.email_verified is True


async def test_google_login_refuses_to_link_when_email_unverified(
    auth_service: AuthService, unique_email: str
) -> None:
    """Blocks a Google account with an unverified-but-matching email from
    taking over a pre-existing local account."""
    await auth_service.register(
        RegisterRequest(email=unique_email, password=PASSWORD, name="Password User")
    )

    profile = _google_profile(unique_email, email_verified=False)

    with pytest.raises(OAuthAccountError):
        await auth_service.login_or_register_with_google(profile)
