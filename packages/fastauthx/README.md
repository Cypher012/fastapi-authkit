# fastauthx

![Python](https://img.shields.io/badge/python-3.13%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A drop in authentication core for FastAPI. Password auth, Google OAuth,
JWT access tokens, rotating single use refresh tokens, email
verification, and password reset, all wired up in a few lines, without
locking you into a specific database engine, email provider, or
multi tenancy model.

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Setting up a new project from scratch](#setting-up-a-new-project-from-scratch)
- [Endpoints](#endpoints)
- [Configuration reference](#configuration-reference)
- [Google OAuth setup](#google-oauth-setup)
- [Extending: AuthHooks](#extending-authhooks)
- [Bring your own email provider](#bring-your-own-email-provider)
- [Error responses](#error-responses)
- [Security notes](#security-notes)
- [Database and migrations](#database-and-migrations)
- [Testing](#testing)
- [FAQ](#faq)
- [License](#license)

## Why this exists

Most FastAPI auth libraries either do too little (just JWT helpers, you
build everything else) or too much (they assume your data model, your
email provider, your tenancy shape). `fastauthx` tries to sit in the
middle. It is a complete, secure, tested implementation of the auth
flows every app needs, but it stays out of the way of decisions that
are actually yours to make.

Concretely, that means:

- **You bring your own DB session.** `fastauthx` does not own an engine
  or connection pool. You pass it a `get_session` dependency, the same
  shape your app already uses for everything else.
- **You bring your own email provider.** Sending email goes through a
  tiny `EmailSender` protocol. A console logger (for local dev) and a
  Resend adapter ship in the box. Plugging in SES, Postmark, or
  anything else is a ten line class.
- **It ships no database migrations.** `fastauthx` gives you SQLModel
  table classes (`Users`, `Accounts`, `Sessions`, `Verification`). You
  import them onto your own app's metadata and run your own Alembic
  migration, so they live alongside your other tables in one history.
- **It knows nothing about organizations, teams, or roles.** That is a
  deliberate boundary. Multi tenancy is a big, opinionated design
  space, and forcing one shape onto every consumer would make this
  library far less generally useful. Instead there is a single,
  explicit extension point (`AuthHooks.on_user_created`) for anything
  you want to happen when a new user shows up. See
  [`fastauthx-orgs`](../fastauthx-orgs) for a package built on exactly
  this hook.

## Features

| Area | What you get |
|---|---|
| Password auth | Argon2id hashing, register, login |
| Access tokens | Short lived JWTs (`HS256`), no authorization state baked in |
| Refresh tokens | Long lived, opaque, single use, rotated on every refresh, stored only as a hash |
| Google OAuth | Full OIDC flow, identity keyed on Google's stable `sub`, conservative account linking |
| Email verification | Single use hashed token, expiring, resend endpoint |
| Password reset | Single use hashed token, expiring, revokes all existing sessions on success |
| Extensibility | One hook (`AuthHooks.on_user_created`) for anything that needs to happen when a user is created |
| Email | Swappable `EmailSender` protocol, ships console and Resend adapters |

## Requirements

- Python 3.13 or later
- PostgreSQL (the test suite and the shipped models assume Postgres specific types; other databases are not tested)
- An async SQLAlchemy/SQLModel session

## Installation

`fastauthx` is not published on PyPI yet, and there is an unrelated,
pre existing package also called `FastAuthX` on PyPI (PyPI treats
`FastAuthX` and `fastauthx` as the same name). Do not run a bare
`pip install fastauthx`, it will install the wrong package. Install
directly from this repository instead:

```bash
uv add "fastauthx @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx"
```

With `uv`, this is the whole story. `uv` reads this repository's
workspace configuration from the git checkout automatically, so
`fastauthx-orgs` and `fastauthx-roles` (see their own READMEs) resolve
their dependency on `fastauthx` correctly the same way, with no extra
setup.

With plain `pip`, install `fastauthx` and any of its siblings together,
in the same command or the same requirements file, so pip's resolver
sees the git reference before it looks anywhere else for the name:

```bash
pip install \
  "fastauthx @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx"
```

If you `pip install fastauthx-orgs` (or `fastauthx-roles`) by itself,
without `fastauthx` listed alongside it in the same invocation, pip
will fetch the unrelated PyPI package for `fastauthx` as a dependency.
This is a real, confirmed failure mode of plain pip with this
particular name collision, not a hypothetical one. `uv` does not have
this problem, and is the installation method this project actually
tests.

## Quickstart

```python
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx import AuthConfig, ConsoleEmailSender, create_auth_router

app = FastAPI()

# 1. Your own DB session. fastauthx does not own this.
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session():
    async with session_maker() as session:
        yield session

# 2. Your own email sender. Swap ConsoleEmailSender for ResendEmailSender
#    (or your own) whenever you are ready to send real email.
email_sender = ConsoleEmailSender()

# 3. One config object.
config = AuthConfig(
    secret_key="change-me-to-something-long-and-random",
    frontend_url="http://localhost:3000",
)

# 4. Mount it.
auth = create_auth_router(config, get_session=get_session, email_sender=email_sender)
app.include_router(auth.router)
auth.install_exception_handlers(app)

# 5. Protect your own routes with the dependency it gives you back.
from fastapi import Depends
from fastauthx.models import Users

@app.get("/me/projects")
async def my_projects(user: Users = Depends(auth.get_current_user)):
    return {"user_id": str(user.id)}
```

## Setting up a new project from scratch

Every command below was actually run, in order, in a fresh directory,
against a real Postgres database, to write this section. This is not
an approximation, it is the exact path from an empty folder to a
running server with a working `/auth/register` endpoint.

### 1. Create the project

```bash
mkdir my-app && cd my-app
uv init --app
```

### 2. Add dependencies

```bash
uv add fastapi uvicorn sqlmodel asyncpg "alembic[async]" python-dotenv
uv add "fastauthx @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx"
```

### 3. Start Postgres

If you do not already have one running, the quickest way is Docker:

```bash
docker run -d --name my-app-db \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=my_app \
  -p 5432:5432 postgres:17-alpine
```

### 4. Configure environment variables

```bash
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/my_app
SECRET_KEY=change-me-to-something-long-and-random
EOF
```

Generate a real secret instead of typing one by hand:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5. Write `main.py`

```python
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx import AuthConfig, ConsoleEmailSender, create_auth_router
from fastauthx.models import Users

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]

engine = create_async_engine(DATABASE_URL)
session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with session_maker() as session:
        yield session


config = AuthConfig(
    secret_key=SECRET_KEY,
    frontend_url="http://localhost:3000",
    secure_cookies=False,  # True in production, behind HTTPS
)

app = FastAPI(title="my app")

auth = create_auth_router(
    config,
    get_session=get_session,
    email_sender=ConsoleEmailSender(),
)
app.include_router(auth.router)
auth.install_exception_handlers(app)


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/me")
async def me(user: Users = Depends(auth.get_current_user)):
    return {"id": str(user.id), "email": user.email, "name": user.name}
```

### 6. Set up Alembic

```bash
uv run alembic init -t async alembic
```

Edit `alembic/env.py`. Replace the top of the generated file (everything
up to `target_metadata = None`) with:

```python
import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context
from fastauthx.models import *  # noqa: F403 registers fastauthx's tables

load_dotenv()

config = context.config
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata
```

Leave the rest of the generated file (`run_migrations_offline`,
`do_run_migrations`, `run_async_migrations`, `run_migrations_online`,
and the final `if` block) exactly as generated.

Also edit `alembic/script.py.mako` and add one import, so generated
migrations that reference SQLModel types actually compile:

```python
from alembic import op
import sqlalchemy as sa
import sqlmodel
${imports if imports else ""}
```

### 7. Generate and run the migration

```bash
uv run alembic revision --autogenerate -m "add fastauthx tables"
uv run alembic upgrade head
```

You should see `users`, `accounts`, `sessions`, and `verification`
listed as newly created tables in the command output.

### 8. Run the app

```bash
uv run uvicorn main:app --reload
```

### 9. Try it

```bash
curl -i -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"correct-horse-battery","name":"Ada Lovelace"}'
```

You should get back `201 Created`, a JSON body with an `access_token`
and a `user` object, and a `Set-Cookie: refresh_token=...` header. Open
`http://localhost:8000/docs` to see every endpoint in Swagger UI.

## Endpoints

| Method | Path | Auth required | Notes |
|---|---|---|---|
| POST | `/auth/register` | no | Creates user, sends verification email |
| POST | `/auth/login` | no | |
| POST | `/auth/refresh` | refresh cookie | Rotates the refresh token |
| POST | `/auth/logout` | refresh cookie | Revokes the refresh token |
| GET | `/auth/me` | access token | |
| POST | `/auth/verify-email` | no | Body: `{ "token": "..." }` |
| POST | `/auth/verify-email/resend` | access token | |
| POST | `/auth/forgot-password` | no | Always 202, never reveals if email exists |
| POST | `/auth/reset-password` | no | Also revokes all existing sessions |
| GET | `/auth/google/login` | no | Only registered if Google is configured |
| GET | `/auth/google/callback` | no | Only registered if Google is configured |

The access token is returned in the JSON body. The refresh token is
**only** ever set as an `HttpOnly` cookie (`Path=/auth`). It is never
present in any response body.

### Request and response examples

**`POST /auth/register`**

Request:

```json
{
  "email": "ada@example.com",
  "password": "correct-horse-battery-staple",
  "name": "Ada Lovelace"
}
```

Response, `201 Created`, plus a `Set-Cookie: refresh_token=...` header:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "b3b1e6b0-3e9a-4c9e-9c9a-1f2a3b4c5d6e",
    "email": "ada@example.com",
    "name": "Ada Lovelace",
    "avatar_url": null,
    "email_verified": false,
    "created_at": "2026-09-08T12:00:00Z"
  }
}
```

**`POST /auth/login`**

Request:

```json
{ "email": "ada@example.com", "password": "correct-horse-battery-staple" }
```

Response shape is identical to register's.

**`POST /auth/refresh`** and **`POST /auth/logout`** read the refresh
token from the cookie automatically. Neither takes a body.

```json
{ "access_token": "eyJhbGciOiJIUzI1NiIs...", "token_type": "bearer" }
```

**`GET /auth/me`** (with `Authorization: Bearer <access_token>`):

```json
{
  "id": "b3b1e6b0-3e9a-4c9e-9c9a-1f2a3b4c5d6e",
  "email": "ada@example.com",
  "name": "Ada Lovelace",
  "avatar_url": null,
  "email_verified": true,
  "created_at": "2026-09-08T12:00:00Z"
}
```

## Configuration reference

```python
AuthConfig(
    secret_key: str,                     # required, JWT signing and session middleware
    frontend_url: str,                   # required, used to build email links
    secure_cookies: bool = True,         # set False for local http:// development

    tokens: TokenConfig(
        algorithm: str = "HS256",
        access_expire_minutes: int = 15,
        refresh_expire_days: int = 30,
    ),

    verification: VerificationConfig(
        email_expire_hours: int = 24,
        password_reset_expire_minutes: int = 30,
    ),

    # Keyed by provider name. Currently only "google" is implemented.
    # Omitting a provider means its routes are never registered at all.
    oauth: dict[str, GoogleOAuthConfig] = {},
)
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `secret_key` | `str` | required | Used to sign JWTs and Starlette's session cookie. Keep it out of source control. |
| `frontend_url` | `str` | required | Base URL used to build verification and password reset links. |
| `secure_cookies` | `bool` | `True` | Set to `False` only for local development over plain HTTP. |
| `tokens.algorithm` | `str` | `"HS256"` | JWT signing algorithm. |
| `tokens.access_expire_minutes` | `int` | `15` | Access token lifetime. |
| `tokens.refresh_expire_days` | `int` | `30` | Refresh token lifetime, before rotation resets it. |
| `verification.email_expire_hours` | `int` | `24` | Email verification link lifetime. |
| `verification.password_reset_expire_minutes` | `int` | `30` | Password reset link lifetime. Short on purpose. |
| `oauth` | `dict[str, GoogleOAuthConfig]` | `{}` | Keyed by provider name. Empty means no OAuth routes are registered at all. |

## Google OAuth setup

```python
from fastauthx import AuthConfig, GoogleOAuthConfig

config = AuthConfig(
    secret_key=...,
    frontend_url=...,
    oauth={
        "google": GoogleOAuthConfig(
            client_id="...",
            client_secret="...",
            redirect_uri="http://localhost:8000/auth/google/callback",
        ),
    },
)
```

You will also need Starlette's `SessionMiddleware` (Authlib uses it to
stash CSRF state between the login redirect and the callback):

```python
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(SessionMiddleware, secret_key=config.secret_key)
```

Steps to get real credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Create an OAuth 2.0 Client ID of type "Web application".
3. Add an authorized redirect URI that matches `redirect_uri` above exactly.
4. Copy the client ID and secret into your `AuthConfig`.

**Account linking policy.** Signing in with Google links to an existing
password account with the same email only if Google reports that email
as verified. Otherwise the login is rejected with `OAuthAccountError`.
This prevents an attacker from using an unverified Google account to
take over an existing local account. A first time Google sign in with
no matching account creates a new user and marks their email verified
automatically, since Google has already done that verification for you.

## Extending: AuthHooks

`on_user_created` fires once, right after a new user is persisted
(flushed but not yet committed), for both password registration and a
user's first Google sign in. It runs inside the same transaction, so
raising from it rolls back user creation too.

```python
from fastauthx import AuthHooks, create_auth_router

async def on_user_created(user, session) -> None:
    # e.g. create an organization and add `user` as its owner,
    # using the same `session` so it is part of the same transaction.
    ...

auth = create_auth_router(
    config,
    get_session=get_session,
    email_sender=email_sender,
    hooks=AuthHooks(on_user_created=on_user_created),
)
```

This is the seam multi tenancy and RBAC extensions are meant to hang
off of. `fastauthx` itself never needs to know they exist. See
[`fastauthx-orgs`](../fastauthx-orgs) for a full implementation of this
pattern.

## Bring your own email provider

```python
from fastauthx import EmailSender

class MyEmailSender:
    async def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> None:
        ...  # call your provider's API
```

Anything satisfying that shape works. It is a `Protocol`, not a base
class you need to inherit from. A `ResendEmailSender` ships as an
optional extra:

```bash
uv add "fastauthx[resend] @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx"
```

```python
from fastauthx.email.resend import ResendEmailSender

email_sender = ResendEmailSender(api_key="re_...", from_address="noreply@yourapp.com")
```

## Error responses

`auth.install_exception_handlers(app)` registers one handler that turns
every domain exception into a JSON response of the shape
`{ "detail": "human readable message" }`, with the status codes below.

| Exception | Status | When |
|---|---|---|
| `EmailAlreadyRegisteredError` | 409 | Registering with an email that already has an account |
| `InvalidCredentialsError` | 401 | Wrong email or password on login |
| `InvalidRefreshTokenError` | 401 | Refresh or logout with a missing, expired, or already used refresh token |
| `InvalidAccessTokenError` | 401 | Missing, malformed, or expired access token on a protected route |
| `InvalidVerificationTokenError` | 400 | Unknown, expired, or already used email verification or password reset token |
| `OAuthAccountError` | 400 | Google sign in failed, or would link to an account it should not |

## Security notes

- Passwords are hashed with Argon2id, never stored or logged in plain text.
- Refresh tokens are opaque random strings, not JWTs, so they can be
  revoked server side. Only a SHA-256 hash is stored.
- Every refresh rotates the token: the old one is revoked the moment a
  new one is issued, so a stolen but unused refresh token stops working
  the next time the legitimate client refreshes.
- `/auth/forgot-password` always returns the same response whether or
  not the email is registered, to prevent user enumeration.
- Resetting a password revokes every existing session for that user.
- The refresh token is never present in any JSON response body. It is
  only ever set as an `HttpOnly`, `Path=/auth` cookie.

## Database and migrations

`fastauthx` ships plain SQLModel table classes and no migrations. Import
them so they register on your app's metadata, then run your own
migration. See
[Setting up a new project from scratch](#setting-up-a-new-project-from-scratch)
for the full, verified `alembic/env.py` setup.

```python
from fastauthx.models import Users, Accounts, Sessions, Verification  # noqa: F401
```

```bash
alembic revision --autogenerate -m "add fastauthx tables"
alembic upgrade head
```

## Testing

The test suite talks to a real Postgres instance (no mocks) and builds
its own minimal FastAPI app via `create_auth_router` directly. It does
not need a host app.

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest
```

## FAQ

**Does this work with SQLite or MySQL?**
Not tested. The models use Postgres specific column types
(`TIMESTAMPTZ`, native `UUID`, Postgres `ENUM`), so other databases
would need changes.

**Can I add extra fields to the `Users` table?**
Not directly today. `fastauthx` owns that table's schema. If you need
more user fields, the common pattern is a separate table with a foreign
key to `Users.id`, populated via the `AuthHooks.on_user_created` hook.

**Why is the refresh token a cookie instead of returned like the access token?**
So that JavaScript can never read it. Keeping it out of `localStorage`
or any JSON response body is what makes token theft via XSS much harder.

**Can I use more than one OAuth provider?**
Only Google is implemented today. The `oauth` config field is a dict
keyed by provider name specifically so a second provider can be added
as a new key later without a breaking change.

## License

MIT
