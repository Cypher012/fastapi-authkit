"""fastauthx-roles ships no migrations (see its README) — a real consumer
imports UserRole onto their own metadata and runs their own Alembic
migration. For this package's own tests, we just create_all its one
table directly against the shared dev Postgres instance; create_all
skips tables that already exist (users, etc.), so this is safe.
"""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import Users  # registers "users" so UserRole's FK resolves
from fastauthx_roles.models import UserRole

load_dotenv()

_DATABASE_URL = os.environ.get(
    "FASTAUTHX_TEST_DATABASE_URL",
    "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
        os.environ["POSTGRES_USER"],
        os.environ["POSTGRES_PASSWORD"],
        os.environ.get("POSTGRES_HOST", "localhost"),
        os.environ.get("POSTGRES_PORT", "5432"),
        os.environ["POSTGRES_DB"],
    ),
)

_engine = create_async_engine(_DATABASE_URL)
_session_maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _session_maker() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
async def _create_user_roles_table():
    """Creates `user_roles` for the test session and drops it again
    afterward. Without the teardown, this table would linger in the
    shared dev DB after every test run — since `app/`'s own Alembic
    setup doesn't know about it yet (fastauthx-roles isn't consumed by
    app/ yet), a lingering table shows up as unexpected drift the next
    time someone runs `alembic check`/`autogenerate` against this DB.

    Uses a private MetaData, not the shared SQLModel.metadata — Postgres
    ENUM types are tracked at the MetaData level, so drop_all on the
    shared metadata can try to drop enum types used by completely
    unrelated tables (e.g. fastauthx.models.Accounts' `providerenum`) once
    the full workspace test suite has registered them onto the same
    metadata. `Users` is copied in too — DDL sorting needs to resolve
    UserRole's `users.id` foreign key even though `tables=[...]` below
    means `users` itself is never created/dropped.
    """
    isolated_metadata = MetaData()
    Users.__table__.to_metadata(isolated_metadata)
    user_role_table = UserRole.__table__.to_metadata(isolated_metadata)

    async with _engine.begin() as conn:
        await conn.run_sync(
            lambda c: isolated_metadata.create_all(c, tables=[user_role_table])
        )
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(
            lambda c: isolated_metadata.drop_all(c, tables=[user_role_table])
        )


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


@pytest.fixture
def get_session_dependency():
    """The bare `get_session` callable, for tests that need to hand it to
    create_roles_kit() themselves — exposed as a fixture rather than
    imported directly, since importing a same-named module across the
    three "tests" directories in this workspace risks a module-name
    collision that pytest's own conftest loading is specially built to
    avoid (this plain function isn't)."""
    return get_session


@pytest.fixture
async def test_user(db_session: AsyncSession) -> Users:
    """A real row in fastauthx's `users` table — UserRole's foreign key
    needs a genuine user to point at."""
    user = Users(email=f"{uuid4().hex}@example.com", name="Test User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
