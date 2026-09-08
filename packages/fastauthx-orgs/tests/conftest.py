"""fastauthx-orgs' own test suite builds its own minimal FastAPI app via
create_orgs_router() directly, using a fake get_current_user (any
callable resolving to something with an .id — no dependency on a real
fastauthx login flow needed to exercise this package's logic).

Unlike fastauthx-roles' tests, this suite does NOT create/drop its tables
itself: `organizations`/`organization_memberships` are already part of
this monorepo's real, Alembic-migrated schema (they existed under
app.models before being relocated here — no schema change happened, just
a code move), same assumption fastauthx core's own test suite makes about
`users`/`accounts`/etc. Tearing them down here would be dropping real
app tables, not cleaning up ephemeral test state — see the incident this
comment is here to prevent.
"""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import unquote
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import Users  # registers "users" so FKs resolve
from fastauthx_orgs import create_orgs_router
from fastauthx_orgs.models import RoleEnum
from fastauthx_orgs.repository import OrgsRepository

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


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


@pytest.fixture
async def make_user(db_session: AsyncSession):
    """Factory fixture: each call inserts a fresh real `users` row (the
    FK target for memberships) and returns it."""

    async def _make_user(name: str = "Test User") -> Users:
        user = Users(email=f"{uuid4().hex}@example.com", name=name)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _make_user


@pytest.fixture
async def test_user(make_user) -> Users:
    return await make_user()


@pytest.fixture
def current_user_holder():
    """A mutable box so tests can swap which user `fake_get_current_user`
    resolves to mid-test (e.g. to act as two different org members)."""
    return {}


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(
        self, *, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        self.sent.append(SentEmail(to=to, subject=subject, html=html))

    def extract_token(self, to: str) -> str:
        """Pulls the invitation token out of the last email sent to
        `to`, mirroring what a user would get from clicking the link in
        their inbox. Invitation links are `/invitations/{token}` (no
        query string), so this just takes the last path segment."""
        email = next(e for e in reversed(self.sent) if e.to == to)
        href = email.html.split('href="', 1)[1].split('"', 1)[0]
        return unquote(href.rstrip("/").rsplit("/", 1)[-1])


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def test_app(
    current_user_holder: dict, test_user: Users, fake_email_sender: FakeEmailSender
) -> FastAPI:
    current_user_holder["user"] = test_user

    async def fake_get_current_user() -> Users:
        return current_user_holder["user"]

    kit = create_orgs_router(
        get_session=get_session,
        get_current_user=fake_get_current_user,
        email_sender=fake_email_sender,
        frontend_url="http://localhost:3000",
    )
    app = FastAPI()
    app.include_router(kit.router)
    kit.install_exception_handlers(app)
    return app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def add_member(db_session: AsyncSession):
    """Seeds a membership directly (bypassing HTTP) — there's no invite
    endpoint yet (Milestone 5), so this is how tests get a second member
    into an organization to exercise multi-member scenarios."""

    async def _add_member(
        organization_id, user_id, role: RoleEnum = RoleEnum.MEMBER
    ) -> None:
        repository = OrgsRepository(db_session)
        await repository.create_membership(
            organization_id=organization_id, user_id=user_id, role=role
        )
        await repository.commit()

    return _add_member
