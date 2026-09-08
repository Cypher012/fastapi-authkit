"""Repository-level: assign/revoke/get roles directly against Postgres.
No FastAPI involved here — see test_require_role.py for the dependency."""

from fastauthx.models import Users
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx_roles import assign_role, get_user_roles, revoke_role


async def test_assign_role_then_get_user_roles(
    db_session: AsyncSession, test_user: Users
) -> None:
    await assign_role(db_session, test_user.id, "admin")

    roles = await get_user_roles(db_session, test_user.id)

    assert roles == ["admin"]


async def test_a_user_can_hold_multiple_roles(
    db_session: AsyncSession, test_user: Users
) -> None:
    await assign_role(db_session, test_user.id, "admin")
    await assign_role(db_session, test_user.id, "billing_manager")

    roles = await get_user_roles(db_session, test_user.id)

    assert set(roles) == {"admin", "billing_manager"}


async def test_assign_role_is_idempotent(
    db_session: AsyncSession, test_user: Users
) -> None:
    await assign_role(db_session, test_user.id, "admin")
    await assign_role(db_session, test_user.id, "admin")

    roles = await get_user_roles(db_session, test_user.id)

    assert roles == ["admin"]


async def test_revoke_role_removes_it(
    db_session: AsyncSession, test_user: Users
) -> None:
    await assign_role(db_session, test_user.id, "admin")

    await revoke_role(db_session, test_user.id, "admin")

    assert await get_user_roles(db_session, test_user.id) == []


async def test_revoke_role_is_idempotent_when_not_assigned(
    db_session: AsyncSession, test_user: Users
) -> None:
    await revoke_role(db_session, test_user.id, "admin")

    assert await get_user_roles(db_session, test_user.id) == []


async def test_get_user_roles_is_empty_for_a_fresh_user(
    db_session: AsyncSession, test_user: Users
) -> None:
    assert await get_user_roles(db_session, test_user.id) == []
