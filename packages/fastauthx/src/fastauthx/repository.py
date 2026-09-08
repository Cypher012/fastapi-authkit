"""Data-access layer for authentication.

Only queries and persistence live here — no business rules, no password
hashing, no token generation. That keeps AuthService free to orchestrate
policy while this class stays a thin, easily-mocked boundary to Postgres.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import (
    Accounts,
    ProviderEnum,
    Sessions,
    Users,
    Verification,
    VerificationTypeEnum,
)


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """Exposed deliberately: `AuthHooks.on_user_created` needs the
        same session/transaction to add its own rows (e.g. an
        organization) atomically with user creation."""
        return self._session

    async def get_user_by_email(self, email: str) -> Users | None:
        result = await self._session.exec(select(Users).where(Users.email == email))
        return result.first()

    async def get_user_by_id(self, user_id: UUID) -> Users | None:
        return await self._session.get(Users, user_id)

    async def create_user(
        self, *, email: str, name: str, avatar_url: str | None = None
    ) -> Users:
        user = Users(email=email, name=name, avatar_url=avatar_url)
        self._session.add(user)
        await self._session.flush()
        return user

    async def create_password_account(
        self, *, user_id: UUID, password_hash: str
    ) -> Accounts:
        account = Accounts(
            user_id=user_id,
            provider=ProviderEnum.PASSWORD,
            password_hash=password_hash,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def get_password_account(self, user_id: UUID) -> Accounts | None:
        result = await self._session.exec(
            select(Accounts).where(
                Accounts.user_id == user_id,
                Accounts.provider == ProviderEnum.PASSWORD,
            )
        )
        return result.first()

    async def get_account_by_provider(
        self, *, provider: ProviderEnum, provider_account_id: str
    ) -> Accounts | None:
        """The identity lookup for OAuth: `provider_account_id` (Google's
        `sub`) is the durable key, never the email — see AuthService for
        why that matters."""
        result = await self._session.exec(
            select(Accounts).where(
                Accounts.provider == provider,
                Accounts.provider_account_id == provider_account_id,
            )
        )
        return result.first()

    async def create_oauth_account(
        self, *, user_id: UUID, provider: ProviderEnum, provider_account_id: str
    ) -> Accounts:
        account = Accounts(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def create_session(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> Sessions:
        session_row = Sessions(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self._session.add(session_row)
        await self._session.flush()
        return session_row

    async def get_active_session_by_token_hash(
        self, token_hash: str
    ) -> Sessions | None:
        """"Active" means unrevoked and unexpired — callers can trust a
        row returned here without re-checking those conditions themselves."""
        result = await self._session.exec(
            select(Sessions).where(
                Sessions.token_hash == token_hash,
                Sessions.revoked_at.is_(None),
                Sessions.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.first()

    async def revoke_session(self, session_row: Sessions) -> None:
        session_row.revoked_at = datetime.now(timezone.utc)
        self._session.add(session_row)
        await self._session.flush()

    async def revoke_all_sessions_for_user(self, user_id: UUID) -> None:
        """Called after a password reset: any session that predates the
        reset should not survive it, in case the account was compromised."""
        result = await self._session.exec(
            select(Sessions).where(
                Sessions.user_id == user_id, Sessions.revoked_at.is_(None)
            )
        )
        now = datetime.now(timezone.utc)
        for session_row in result.all():
            session_row.revoked_at = now
            self._session.add(session_row)
        await self._session.flush()

    async def update_password_hash(self, account: Accounts, password_hash: str) -> None:
        account.password_hash = password_hash
        self._session.add(account)
        await self._session.flush()

    async def mark_email_verified(self, user: Users) -> None:
        user.email_verified = True
        self._session.add(user)
        await self._session.flush()

    async def create_verification(
        self,
        *,
        user_id: UUID,
        type_: VerificationTypeEnum,
        token_hash: str,
        expires_at: datetime,
    ) -> Verification:
        verification = Verification(
            user_id=user_id, type=type_, token_hash=token_hash, expires_at=expires_at
        )
        self._session.add(verification)
        await self._session.flush()
        return verification

    async def get_active_verification_by_token_hash(
        self, token_hash: str, type_: VerificationTypeEnum
    ) -> Verification | None:
        result = await self._session.exec(
            select(Verification).where(
                Verification.token_hash == token_hash,
                Verification.type == type_,
                Verification.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.first()

    async def delete_verification(self, verification: Verification) -> None:
        """Single-use: a verification/reset token is deleted the moment
        it's consumed, so it can never be replayed."""
        await self._session.delete(verification)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
