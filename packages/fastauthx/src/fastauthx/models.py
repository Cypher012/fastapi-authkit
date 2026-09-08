"""The tables fastauthx owns: users, their auth accounts (password or
OAuth), refresh-token sessions, and single-use verification tokens.

Deliberately excludes anything about organizations/roles/tenancy — a
host app imports these classes so they land on its own SQLModel.metadata
(and its own Alembic migration), then builds whatever it wants on top by
foreign-keying into `Users.id`. fastauthx ships no migrations of its own.
"""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Field, SQLModel, UniqueConstraint


class ProviderEnum(str, Enum):
    GOOGLE = "GOOGLE"
    PASSWORD = "PASSWORD"


class VerificationTypeEnum(str, Enum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


class Users(SQLModel, table=True):
    __tablename__: str = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(nullable=False, unique=True, index=True)
    name: str = Field(nullable=False)
    avatar_url: str | None = Field(default=None)
    email_verified: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )


class Accounts(SQLModel, table=True):
    __tablename__: str = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_accounts_provider_provider_account_id",
        ),
        CheckConstraint(
            "(provider = 'PASSWORD' AND password_hash IS NOT NULL AND provider_account_id IS NULL) "
            "OR (provider = 'GOOGLE' AND provider_account_id IS NOT NULL AND password_hash IS NULL)",
            name="ck_accounts_provider_fields",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    provider: ProviderEnum = Field(nullable=False)
    provider_account_id: str | None = Field(default=None)
    access_token: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    access_token_expires_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    refresh_token_expires_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    password_hash: str | None = Field(default=None)
    id_token: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )


class Sessions(SQLModel, table=True):
    __tablename__: str = "sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    token_hash: str = Field(nullable=False, unique=True, index=True)
    expires_at: datetime = Field(nullable=False, sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )


class Verification(SQLModel, table=True):
    __tablename__: str = "verification"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    type: VerificationTypeEnum = Field(nullable=False)
    token_hash: str = Field(nullable=False, unique=True, index=True)
    expires_at: datetime = Field(nullable=False, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
