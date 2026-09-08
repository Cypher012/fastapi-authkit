"""Tables this package owns: organizations and their memberships.
FK's into `users.id` — assumes that table exists (e.g. from `fastauthx`
core), same convention as `fastauthx-roles`. No migrations shipped; a host
imports these classes onto its own SQLModel.metadata and runs its own
Alembic migration.
"""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel, UniqueConstraint


class RoleEnum(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


# A ranked hierarchy, not just an unordered set: each tier is a superset
# of the one below (OWNER can do everything ADMIN can, etc.), so
# `require_role(min_role=...)` compares rank rather than checking
# membership in an explicit list of allowed roles at every call site.
ROLE_RANK: dict[RoleEnum, int] = {
    RoleEnum.MEMBER: 1,
    RoleEnum.ADMIN: 2,
    RoleEnum.OWNER: 3,
}


class Organizations(SQLModel, table=True):
    __tablename__: str = "organizations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(nullable=False)
    slug: str = Field(nullable=False, unique=True, index=True)
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


class OrganizationMemberships(SQLModel, table=True):
    __tablename__: str = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_org_memberships_org_id_user_id"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(
        foreign_key="organizations.id", nullable=False, index=True
    )
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    role: RoleEnum = Field(default=RoleEnum.MEMBER, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_type=DateTime(timezone=True),
    )


class Invitations(SQLModel, table=True):
    __tablename__: str = "invitations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "email", name="uq_invitations_org_id_email"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(
        foreign_key="organizations.id", nullable=False, index=True
    )
    email: str = Field(nullable=False)
    role: RoleEnum = Field(default=RoleEnum.MEMBER, nullable=False)
    token_hash: str = Field(nullable=False, unique=True, index=True)
    expires_at: datetime = Field(nullable=False, sa_type=DateTime(timezone=True))
    accepted_at: datetime | None = Field(
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
