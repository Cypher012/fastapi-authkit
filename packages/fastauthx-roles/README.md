# fastauthx-roles

![Python](https://img.shields.io/badge/python-3.13%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Global, non tenant role gating for FastAPI apps. For multi tenant,
per organization roles, see [`fastauthx-orgs`](../fastauthx-orgs)
instead. This package is for apps that just want "is this user an
admin" without any concept of organizations.

## Table of contents

- [What it ships](#what-it-ships)
- [What it deliberately does not ship](#what-it-deliberately-does-not-ship)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Setting up a new project from scratch](#setting-up-a-new-project-from-scratch)
- [API reference](#api-reference)
- [Building your own permission mapping](#building-your-own-permission-mapping)
- [Security notes](#security-notes)
- [Database and migrations](#database-and-migrations)
- [Testing](#testing)
- [FAQ](#faq)
- [License](#license)

## What it ships

| Piece | What it does |
|---|---|
| `UserRole` | One table: `user_roles(user_id, role)`. A user can hold more than one role. |
| `assign_role(session, user_id, role)` | Idempotent. Assigning a role a user already has is a no-op. |
| `revoke_role(session, user_id, role)` | Idempotent. Revoking a role a user does not have is a no-op. |
| `get_user_roles(session, user_id)` | Returns the list of role strings a user holds. |
| `create_roles_kit(get_session, get_current_user)` | Returns `require_role(*roles)`, a dependency with OR semantics. |

`role` is a plain string, not a fixed enum, because a global role
vocabulary varies too much per app to hardcode. One app wants `ADMIN` /
`USER`, another wants `SUPERADMIN` / `SUPPORT` / `USER`, another just
wants a `staff` flag.

`require_role("admin", "support")` passes if the caller holds at least
one of the listed roles. There is no hierarchy, since there is no
universal ordering across arbitrary, app defined role strings.

## What it deliberately does not ship

- **No hierarchy.** If you want `admin` to imply `support`, build that
  mapping in your own app on top of `get_current_user_roles`. Same
  reasoning as why `fastauthx-orgs` does not ship a `Permission` enum.
- **No router.** Assigning a role is normally an infrequent, operator
  triggered action (a seed script, an internal admin tool), not a self
  serve public flow the way an organization invitation is. This
  package gives you the building blocks and leaves it to you whether
  to ever expose them through an endpoint.
- **No dependency on `fastauthx` itself.** `create_roles_kit` accepts
  any `get_current_user` shaped callable that resolves to something
  with an `.id`, not specifically `fastauthx.models.Users`. It works
  with any FastAPI auth setup. The one place this package does assume
  something is the foreign key on `user_roles.user_id`, which points at
  a table literally named `users` (for example, the one `fastauthx`
  provides).

## Requirements

- Python 3.13 or later
- PostgreSQL
- Any FastAPI dependency that resolves the current user, from
  `fastauthx` or otherwise, as long as the returned object has an `.id`

## Installation

This package does not depend on `fastauthx` at runtime, so it does not
hit the PyPI name collision described in `fastauthx`'s README. It is
still not published on PyPI itself, so install it from this repository:

```bash
uv add "fastauthx-roles @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx-roles"
# or: pip install "fastauthx-roles @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx-roles"
```

If you are also using `fastauthx` in the same project (the common
case), see its README for why you should list it alongside anything
that depends on it when using plain `pip`.

## Quickstart

```python
from fastauthx_roles import assign_role, create_roles_kit

roles = create_roles_kit(get_session=get_session, get_current_user=get_current_user)

# Somewhere in an admin script or internal tool:
await assign_role(session, user.id, "admin")

# Protect a route:
from typing import Annotated
from fastapi import Depends

@app.delete("/users/{user_id}")
async def ban_user(
    user_id: str,
    _: Annotated[None, Depends(roles.require_role("admin", "support"))],
):
    ...
```

## Setting up a new project from scratch

This continues directly from `fastauthx`'s own
[Setting up a new project from scratch](../fastauthx#setting-up-a-new-project-from-scratch),
which you should follow first. `fastauthx` is used here for
`get_current_user`, but any FastAPI auth setup works in its place, this
package does not require it specifically. Every command below was
actually run against a real Postgres database to write this section.

### 1. Add the dependency

From the same project you set up for `fastauthx`:

```bash
uv add "fastauthx-roles @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx-roles"
```

### 2. Update `main.py`

Replace `main.py` with:

```python
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx import AuthConfig, ConsoleEmailSender, create_auth_router
from fastauthx_roles import create_roles_kit

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]

engine = create_async_engine(DATABASE_URL)
session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with session_maker() as session:
        yield session


config = AuthConfig(secret_key=SECRET_KEY, frontend_url="http://localhost:3000", secure_cookies=False)

app = FastAPI(title="my app")

auth = create_auth_router(config, get_session=get_session, email_sender=ConsoleEmailSender())
app.include_router(auth.router)
auth.install_exception_handlers(app)

roles = create_roles_kit(get_session=get_session, get_current_user=auth.get_current_user)


@app.get("/admin/dashboard")
async def admin_dashboard(_=Depends(roles.require_role("admin"))):
    return {"status": "welcome, admin"}
```

### 3. Add its table to your migration

Edit `alembic/env.py`, adding one import right after the `fastauthx`
one:

```python
from fastauthx.models import *  # noqa: F403 registers fastauthx's tables
from fastauthx_roles.models import *  # noqa: F403 registers fastauthx-roles' table
```

### 4. Generate and run the migration

```bash
uv run alembic revision --autogenerate -m "add fastauthx-roles table"
uv run alembic upgrade head
```

You should see `user_roles` listed as a newly created table.

### 5. Write a script to grant the role

This package deliberately has no endpoint for this (see
[What it deliberately does not ship](#what-it-deliberately-does-not-ship)).
Write a small script instead:

```python
# assign_admin.py
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import Users
from fastauthx_roles import assign_role


async def main(email: str) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        result = await session.exec(select(Users).where(Users.email == email))
        user = result.first()
        if user is None:
            print(f"No user with email {email}")
            return
        await assign_role(session, user.id, "admin")
        print(f"{email} is now an admin")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
```

### 6. Run the app and try it

```bash
uv run uvicorn main:app --reload
```

Register a user, confirm the dashboard is forbidden, grant the role,
then confirm it works:

```bash
RESPONSE=$(curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"correct-horse-battery","name":"Ada Lovelace"}')

TOKEN=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -s -w "\nstatus=%{http_code}\n" http://localhost:8000/admin/dashboard -H "Authorization: Bearer $TOKEN"
# {"detail":"You do not have the required role."}
# status=403

uv run python assign_admin.py ada@example.com
# ada@example.com is now an admin

curl -s -w "\nstatus=%{http_code}\n" http://localhost:8000/admin/dashboard -H "Authorization: Bearer $TOKEN"
# {"status":"welcome, admin"}
# status=200
```

## API reference

### `assign_role(session, user_id, role) -> None`

Adds a role to a user. Idempotent: assigning a role the user already
has does nothing and does not raise.

### `revoke_role(session, user_id, role) -> None`

Removes a role from a user. Idempotent: revoking a role the user does
not have does nothing and does not raise.

### `get_user_roles(session, user_id) -> list[str]`

Returns every role string currently assigned to the user, in no
particular order.

### `create_roles_kit(*, get_session, get_current_user) -> RolesKit`

Returns a `RolesKit` with two attributes:

- `get_current_user_roles`, a FastAPI dependency returning
  `list[str]` for whoever `get_current_user` resolves to.
- `require_role(*roles: str)`, a dependency factory. The dependency it
  returns raises `HTTPException(403)` unless the caller holds at least
  one of the given role strings.

## Building your own permission mapping

```python
from enum import Enum
from typing import Annotated
from fastapi import Depends, HTTPException

class Permission(str, Enum):
    INVOICE_VOID = "invoice:void"
    USER_BAN = "user:ban"

ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": {Permission.INVOICE_VOID, Permission.USER_BAN},
    "support": {Permission.USER_BAN},
}

def require_permission(permission: Permission):
    async def dependency(
        user_roles: Annotated[list[str], Depends(roles.get_current_user_roles)],
    ) -> None:
        if not any(permission in ROLE_PERMISSIONS.get(r, set()) for r in user_roles):
            raise HTTPException(status_code=403)
    return dependency
```

## Security notes

- Role assignment is not exposed as a public endpoint by this package.
  If you add one yourself, gate it behind your own admin authentication,
  since granting a role is a privilege escalation sensitive action.
- `require_role` fails closed: if `get_current_user` raises (for
  example, an invalid or missing token), that exception propagates and
  the request never reaches the route.

## Database and migrations

```python
from fastauthx_roles.models import UserRole  # noqa: F401
```

```bash
alembic revision --autogenerate -m "add fastauthx-roles table"
alembic upgrade head
```

## Testing

A real Postgres instance, no mocks. The test suite creates its one
table itself and drops it again afterward, since this package (unlike
`fastauthx-orgs`) is not expected to already be part of your app's
migrated schema.

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest
```

## FAQ

**Can a user have more than one role?**
Yes. `user_roles` has a unique constraint on `(user_id, role)`, not on
`user_id` alone, so a user can hold as many roles as you assign.

**Do I need `fastauthx` to use this package?**
No. `create_roles_kit` only needs a `get_current_user` dependency that
resolves to something with an `.id`. Any auth library, or your own
hand rolled one, works.

**How do I let users manage roles through an API instead of a script?**
Write the endpoint yourself, calling `assign_role` / `revoke_role`, and
gate it with your own `require_role("admin")` check. This is a
deliberate omission, not a missing feature: role assignment endpoints
carry enough app specific authorization nuance (who can grant what to
whom) that a one size fits all version would likely be wrong for your
case.

## License

MIT
