"""Business rules for authentication.

AuthService depends on abstractions it's handed (a repository, a password
hasher, a JWT service, an email service, optional hooks) rather than
constructing them or reaching for global config — that's what makes it
swappable and unit-testable without a real database, email provider, or
FastAPI request in play (dependency inversion).

Deliberately knows nothing about organizations, roles, or tenancy — see
fastauthx.hooks.AuthHooks for how a host app reacts to new users.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastauthx.config import TokenConfig, VerificationConfig
from fastauthx.email_service import AuthEmailService
from fastauthx.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidVerificationTokenError,
    OAuthAccountError,
)
from fastauthx.hooks import AuthHooks
from fastauthx.models import ProviderEnum, Users, VerificationTypeEnum
from fastauthx.repository import AuthRepository
from fastauthx.schemas import LoginRequest, RegisterRequest
from fastauthx.security import (
    JWTService,
    PasswordService,
    generate_opaque_token,
    hash_opaque_token,
)


@dataclass(frozen=True)
class GoogleProfile:
    """The subset of Google's OIDC claims AuthService actually needs —
    keeps the route layer from handing raw provider claims down into
    business logic (ISP: depend on the slice you use, not Google's
    full claim set)."""

    sub: str
    email: str
    name: str
    avatar_url: str | None
    email_verified: bool


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        password_service: PasswordService,
        jwt_service: JWTService,
        email_service: AuthEmailService,
        token_config: TokenConfig,
        verification_config: VerificationConfig,
        hooks: AuthHooks | None = None,
    ) -> None:
        self._repository = repository
        self._password_service = password_service
        self._jwt_service = jwt_service
        self._email_service = email_service
        self._token_config = token_config
        self._verification_config = verification_config
        self._hooks = hooks or AuthHooks()

    async def register(self, data: RegisterRequest) -> tuple[Users, str, str]:
        """Register flow: hash password -> create user -> run
        on_user_created hook -> issue tokens, all in one transaction so a
        failure midway (including inside the hook) leaves nothing behind.
        The verification email is sent only after that transaction
        commits, so a flaky email provider never undoes a successful
        registration."""
        if await self._repository.get_user_by_email(data.email) is not None:
            raise EmailAlreadyRegisteredError()

        user = await self._repository.create_user(email=data.email, name=data.name)

        password_hash = self._password_service.hash(data.password)
        await self._repository.create_password_account(
            user_id=user.id, password_hash=password_hash
        )

        if self._hooks.on_user_created is not None:
            await self._hooks.on_user_created(user, self._repository.session)

        verification_token = await self._create_verification_token(
            user_id=user.id,
            type_=VerificationTypeEnum.EMAIL_VERIFICATION,
            expires_in=timedelta(hours=self._verification_config.email_expire_hours),
        )
        access_token, refresh_token = await self._issue_tokens(user.id)
        await self._repository.commit()

        await self._email_service.send_verification_email(
            to_email=user.email, name=user.name, raw_token=verification_token
        )
        return user, access_token, refresh_token

    async def login(self, data: LoginRequest) -> tuple[Users, str, str]:
        user = await self._repository.get_user_by_email(data.email)
        if user is None:
            raise InvalidCredentialsError()

        account = await self._repository.get_password_account(user.id)
        if account is None or account.password_hash is None:
            raise InvalidCredentialsError()

        if not self._password_service.verify(data.password, account.password_hash):
            raise InvalidCredentialsError()

        access_token, refresh_token = await self._issue_tokens(user.id)
        await self._repository.commit()
        return user, access_token, refresh_token

    async def refresh(self, raw_refresh_token: str) -> tuple[str, str]:
        """Rotates the refresh token on every use: the old one is revoked
        and a new one issued, so a stolen-but-unused token becomes useless
        the moment the legitimate client refreshes again."""
        token_hash = hash_opaque_token(raw_refresh_token)
        session_row = await self._repository.get_active_session_by_token_hash(
            token_hash
        )
        if session_row is None:
            raise InvalidRefreshTokenError()

        await self._repository.revoke_session(session_row)
        access_token, new_refresh_token = await self._issue_tokens(
            session_row.user_id
        )
        await self._repository.commit()
        return access_token, new_refresh_token

    async def logout(self, raw_refresh_token: str) -> None:
        """Idempotent: logging out with an already-invalid or unknown
        token is not an error, it's just a no-op."""
        token_hash = hash_opaque_token(raw_refresh_token)
        session_row = await self._repository.get_active_session_by_token_hash(
            token_hash
        )
        if session_row is not None:
            await self._repository.revoke_session(session_row)
            await self._repository.commit()

    async def verify_email(self, raw_token: str) -> None:
        token_hash = hash_opaque_token(raw_token)
        verification = await self._repository.get_active_verification_by_token_hash(
            token_hash, VerificationTypeEnum.EMAIL_VERIFICATION
        )
        if verification is None:
            raise InvalidVerificationTokenError()

        user = await self._repository.get_user_by_id(verification.user_id)
        if user is None:
            raise InvalidVerificationTokenError()

        await self._repository.mark_email_verified(user)
        await self._repository.delete_verification(verification)
        await self._repository.commit()

    async def resend_verification_email(self, user: Users) -> None:
        if user.email_verified:
            return

        verification_token = await self._create_verification_token(
            user_id=user.id,
            type_=VerificationTypeEnum.EMAIL_VERIFICATION,
            expires_in=timedelta(hours=self._verification_config.email_expire_hours),
        )
        await self._repository.commit()
        await self._email_service.send_verification_email(
            to_email=user.email, name=user.name, raw_token=verification_token
        )

    async def request_password_reset(self, email: str) -> None:
        """Always succeeds from the caller's perspective, whether or not
        the email belongs to an account — that's what stops this endpoint
        from being usable to enumerate registered users."""
        user = await self._repository.get_user_by_email(email)
        if user is None:
            return

        reset_token = await self._create_verification_token(
            user_id=user.id,
            type_=VerificationTypeEnum.PASSWORD_RESET,
            expires_in=timedelta(
                minutes=self._verification_config.password_reset_expire_minutes
            ),
        )
        await self._repository.commit()
        await self._email_service.send_password_reset_email(
            to_email=user.email, name=user.name, raw_token=reset_token
        )

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        """Also revokes every existing session for the user: a password
        reset is often triggered because the account was compromised, so
        anything logged in under the old password should not survive it."""
        token_hash = hash_opaque_token(raw_token)
        verification = await self._repository.get_active_verification_by_token_hash(
            token_hash, VerificationTypeEnum.PASSWORD_RESET
        )
        if verification is None:
            raise InvalidVerificationTokenError()

        account = await self._repository.get_password_account(verification.user_id)
        if account is None:
            raise InvalidVerificationTokenError()

        password_hash = self._password_service.hash(new_password)
        await self._repository.update_password_hash(account, password_hash)
        await self._repository.delete_verification(verification)
        await self._repository.revoke_all_sessions_for_user(verification.user_id)
        await self._repository.commit()

    async def login_or_register_with_google(
        self, profile: GoogleProfile
    ) -> tuple[Users, str, str]:
        """Google's `sub` (not email) is the durable identity key — see
        AuthRepository.get_account_by_provider. Email is only consulted
        the *first* time we see this Google identity, to decide whether
        to link it to an existing password account or create a new user.
        On every later login the (provider, sub) lookup alone decides who
        the user is, so a Google-side email change can never hijack a
        different local account."""
        account = await self._repository.get_account_by_provider(
            provider=ProviderEnum.GOOGLE, provider_account_id=profile.sub
        )

        if account is not None:
            user = await self._repository.get_user_by_id(account.user_id)
            if user is None:
                raise OAuthAccountError("Linked account no longer exists.")
        else:
            user = await self._repository.get_user_by_email(profile.email)
            if user is not None:
                # Linking Google to an *existing* account is only safe if
                # Google itself vouches for the email — otherwise a Google
                # account with an unverified but matching email could hijack
                # someone else's local account.
                if not profile.email_verified:
                    raise OAuthAccountError(
                        "Your Google account's email is not verified."
                    )
            else:
                user = await self._repository.create_user(
                    email=profile.email,
                    name=profile.name,
                    avatar_url=profile.avatar_url,
                )
                if self._hooks.on_user_created is not None:
                    await self._hooks.on_user_created(user, self._repository.session)

            await self._repository.create_oauth_account(
                user_id=user.id,
                provider=ProviderEnum.GOOGLE,
                provider_account_id=profile.sub,
            )

        if profile.email_verified and not user.email_verified:
            await self._repository.mark_email_verified(user)

        access_token, refresh_token = await self._issue_tokens(user.id)
        await self._repository.commit()
        return user, access_token, refresh_token

    async def _issue_tokens(self, user_id: UUID) -> tuple[str, str]:
        access_token = self._jwt_service.create_access_token(user_id)

        raw_refresh_token = generate_opaque_token()
        token_hash = hash_opaque_token(raw_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=self._token_config.refresh_expire_days
        )
        await self._repository.create_session(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        return access_token, raw_refresh_token

    async def _create_verification_token(
        self, *, user_id: UUID, type_: VerificationTypeEnum, expires_in: timedelta
    ) -> str:
        raw_token = generate_opaque_token()
        token_hash = hash_opaque_token(raw_token)
        expires_at = datetime.now(timezone.utc) + expires_in
        await self._repository.create_verification(
            user_id=user_id, type_=type_, token_hash=token_hash, expires_at=expires_at
        )
        return raw_token
