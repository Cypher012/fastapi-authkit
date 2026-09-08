# fastauthx

A drop in authentication core for FastAPI. Password auth, Google OAuth,
JWT access tokens, rotating single use refresh tokens, email
verification, and password reset, all wired up in a few lines, without
locking you into a specific database engine, email provider, or
multi tenancy model.

```bash
pip install fastauthx
```

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
  you want to happen when a new user shows up: creating an
  organization, sending a welcome sequence, assigning a default role,
  whatever your app needs. See
  [`fastauthx-orgs`](../fastauthx-orgs) for a package built on exactly
  this hook.

## Features

- Argon2id password hashing
- Short lived JWT access tokens plus long lived, single use, rotating
  refresh tokens (stored hashed, never exposed as JWTs)
- Google OAuth (OIDC), with the identity key being Google's stable
  `sub`, never email, and a documented, deliberately conservative
  account linking policy
- Email verification and password reset, both via single use hashed
  tokens with expiry
- A single `AuthHooks` extension point for reacting to new users
  without this library needing to know why
- Zero required external services to run the test suite beyond
  Postgres (email defaults to a console logger, Google OAuth is opt in)

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

Then, once, register the tables on your own metadata and run your own
migration:

```python
from fastauthx.models import Users, Accounts, Sessions, Verification  # noqa: F401
# now run: alembic revision --autogenerate -m "add fastauthx tables"
```

That is it. `/auth/register`, `/auth/login`, `/auth/refresh`,
`/auth/logout`, `/auth/me`, `/auth/verify-email`,
`/auth/verify-email/resend`, `/auth/forgot-password`, and
`/auth/reset-password` are live.

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

### Google OAuth

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

Create the OAuth client at
[Google Cloud Console](https://console.cloud.google.com/apis/credentials)
(Web application type) and set the authorized redirect URI to match
`redirect_uri` above exactly.

**Account linking.** Signing in with Google links to an existing
password account with the same email only if Google reports that email
as verified. Otherwise the login is rejected with `OAuthAccountError`.
This prevents an attacker from using an unverified Google account to
take over an existing local account. A first time Google sign in with
no matching account creates a new user and marks their email verified
automatically.

## Extending: `AuthHooks`

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
pip install "fastauthx[resend]"
```

```python
from fastauthx.email.resend import ResendEmailSender

email_sender = ResendEmailSender(api_key="re_...", from_address="noreply@yourapp.com")
```

## Testing

The test suite talks to a real Postgres instance (no mocks) and builds
its own minimal FastAPI app via `create_auth_router` directly. It does
not need a host app.

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest
```

## License

MIT
