"""require_role, exercised over real HTTP against a minimal FastAPI app.
Deliberately uses a fake `get_current_user` (not fastauthx's) to prove
create_roles_kit composes with *any* callable that resolves to something
with an `.id` — the whole point of not hard-depending on fastauthx."""

from collections.abc import AsyncIterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import Users
from fastauthx_roles import assign_role, create_roles_kit
from fastauthx_roles.dependencies import GetSession


def _build_app(user: Users, get_session: GetSession) -> FastAPI:
    async def fake_get_current_user() -> Users:
        return user

    kit = create_roles_kit(get_session=get_session, get_current_user=fake_get_current_user)

    app = FastAPI()

    @app.get("/admin-only", dependencies=[Depends(kit.require_role("admin"))])
    async def admin_only() -> dict:
        return {"ok": True}

    @app.get(
        "/admin-or-support",
        dependencies=[Depends(kit.require_role("admin", "support"))],
    )
    async def admin_or_support() -> dict:
        return {"ok": True}

    return app


@pytest.fixture
async def client(
    test_user: Users, get_session_dependency: GetSession
) -> AsyncIterator[AsyncClient]:
    app = _build_app(test_user, get_session_dependency)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_require_role_allows_a_user_with_the_role(
    client: AsyncClient, db_session: AsyncSession, test_user: Users
) -> None:
    await assign_role(db_session, test_user.id, "admin")

    response = await client.get("/admin-only")

    assert response.status_code == 200


async def test_require_role_rejects_a_user_without_the_role(
    client: AsyncClient, test_user: Users
) -> None:
    response = await client.get("/admin-only")

    assert response.status_code == 403


async def test_require_role_is_or_based_across_multiple_roles(
    client: AsyncClient, db_session: AsyncSession, test_user: Users
) -> None:
    """Holding just one of the listed roles ("support") is enough — no
    hierarchy, no requirement to hold every role passed to require_role."""
    await assign_role(db_session, test_user.id, "support")

    response = await client.get("/admin-or-support")

    assert response.status_code == 200
