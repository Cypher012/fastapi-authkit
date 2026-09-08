"""fastauthx's own test suite talks to a real Postgres instance — the same
one this monorepo's docker-compose provides for local dev — but builds
its own tiny FastAPI app via create_auth_router() directly, with no
hooks and no host app involved. That's deliberate: it proves the library
works standalone, the way an external consumer's test suite would use it.
"""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx import AuthConfig, create_auth_router
from fastauthx.email_service import AuthEmailService
from fastauthx.repository import AuthRepository
from fastauthx.security import JWTService, PasswordService
from fastauthx.service import AuthService

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


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str


class FakeEmailSender:
    """Test double for the EmailSender port: records what would have been
    sent instead of calling a real provider."""

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send(
        self, *, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        self.sent.append(SentEmail(to=to, subject=subject, html=html))

    def extract_token(self, to: str) -> str:
        email = next(e for e in reversed(self.sent) if e.to == to)
        href = email.html.split('href="', 1)[1].split('"', 1)[0]
        query = parse_qs(urlparse(href).query)
        return query["token"][0]


def make_test_config() -> AuthConfig:
    return AuthConfig(
        secret_key="test-secret-key-that-is-long-enough-for-hs256",
        frontend_url="http://localhost:3000",
        secure_cookies=False,
    )


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def test_app(fake_email_sender: FakeEmailSender) -> FastAPI:
    kit = create_auth_router(
        make_test_config(), get_session=get_session, email_sender=fake_email_sender
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
def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


@pytest.fixture
def auth_service(
    db_session: AsyncSession, fake_email_sender: FakeEmailSender
) -> AuthService:
    """A real AuthService for unit-testing business logic (e.g. the
    Google OAuth account-linking rules) directly, without going through
    HTTP or mocking Authlib's Google handshake."""
    config = make_test_config()
    return AuthService(
        repository=AuthRepository(db_session),
        password_service=PasswordService(),
        jwt_service=JWTService(
            secret_key=config.secret_key,
            algorithm=config.tokens.algorithm,
            expires_minutes=config.tokens.access_expire_minutes,
        ),
        email_service=AuthEmailService(
            email_sender=fake_email_sender,
            frontend_url=config.frontend_url,
            verification_config=config.verification,
        ),
        token_config=config.tokens,
        verification_config=config.verification,
    )
