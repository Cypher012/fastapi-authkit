"""Plain functions, not a class with a service layer on top — role
assignment is a single-row operation with no multi-step transaction to
orchestrate, so the extra layering `fastauthx` core uses for register/login
would be pure ceremony here."""

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx_roles.models import UserRole


async def assign_role(session: AsyncSession, user_id: UUID, role: str) -> None:
    """Idempotent: assigning a role the user already has is a no-op, not
    an error — callers shouldn't need to check first."""
    result = await session.exec(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role == role)
    )
    if result.first() is not None:
        return
    session.add(UserRole(user_id=user_id, role=role))
    await session.commit()


async def revoke_role(session: AsyncSession, user_id: UUID, role: str) -> None:
    """Also idempotent: revoking a role the user doesn't have is a no-op."""
    result = await session.exec(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role == role)
    )
    row = result.first()
    if row is not None:
        await session.delete(row)
        await session.commit()


async def get_user_roles(session: AsyncSession, user_id: UUID) -> list[str]:
    result = await session.exec(
        select(UserRole).where(UserRole.user_id == user_id)
    )
    return [row.role for row in result.all()]
