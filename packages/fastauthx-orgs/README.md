# fastauthx-orgs

![Python](https://img.shields.io/badge/python-3.13%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Multi tenant organizations, membership, rank based role checks, and
invitations, built on top of [`fastauthx`](../fastauthx). For a single
global role per user with no tenancy at all, see
[`fastauthx-roles`](../fastauthx-roles) instead.

## Table of contents

- [What it ships](#what-it-ships)
- [What it deliberately does not ship](#what-it-deliberately-does-not-ship)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Setting up a new project from scratch](#setting-up-a-new-project-from-scratch)
- [Endpoints](#endpoints)
- [Request and response examples](#request-and-response-examples)
- [Invitations in detail](#invitations-in-detail)
- [Roles and permissions](#roles-and-permissions)
- [Error responses](#error-responses)
- [Security notes](#security-notes)
- [Database and migrations](#database-and-migrations)
- [Testing](#testing)
- [FAQ](#faq)
- [License](#license)

## What it ships

| Piece | What it does |
|---|---|
| `RoleEnum` | `OWNER` / `ADMIN` / `MEMBER`, a ranked hierarchy, not an unordered set |
| `get_current_membership(organization_id)` | Resolves the caller's membership from a path parameter, 404 if none exists |
| `require_role(min_role)` | Built on the above, 403 if the caller's rank is below `min_role` |
| `create_organization_for_new_user` | An `AuthHooks.on_user_created` callback that gives every new user an organization and `OWNER` membership |
| `create_orgs_router(...)` | Organization CRUD, membership management, and the full invitation flow |

`OWNER` outranks `ADMIN` outranks `MEMBER`, matching the fact that each
tier is a superset of the one below. `get_current_membership` is what
makes "never trust an organization ID from the client without checking
membership" actually true on every route, not just the ones someone
remembered to guard by hand.

## What it deliberately does not ship

A `Permission` enum or a role to permission mapping. What permissions
mean in your app (`project:delete`, `invoice:void`, and so on) is
inherently specific to your app's actual resources. A generic package
cannot enumerate them meaningfully. See
[Roles and permissions](#roles-and-permissions) for the pattern this
package expects you to use instead.

## Requirements

- Python 3.13 or later
- PostgreSQL
- [`fastauthx`](../fastauthx) already set up in your app, since this
  package needs its `get_current_user` dependency and its `Users` table

## Installation

Same caveat as `fastauthx`: this is not on PyPI, and `fastauthx-orgs`
depends on `fastauthx`, which collides with an unrelated package of the
same name on PyPI. Use `uv`, which resolves this correctly on its own
by reading this repository's workspace configuration:

```bash
uv add "fastauthx-orgs @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx-orgs"
```

If you use plain `pip`, you must list `fastauthx` explicitly alongside
it in the same command, or pip will silently fetch the wrong,
unrelated `fastauthx` from PyPI as a dependency of this package:

```bash
pip install \
  "fastauthx @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx" \
  "fastauthx-orgs @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx-orgs"
```

## Quickstart

This assumes you already have `fastauthx` set up (see its README).
`fastauthx-orgs` needs the same `get_session`, plus the
`get_current_user` dependency `create_auth_router` gave you back.

```python
from fastauthx import AuthHooks
from fastauthx_orgs import create_organization_for_new_user, create_orgs_router

# Wire the hook into fastauthx so every new user gets an organization.
auth = create_auth_router(
    config,
    get_session=get_session,
    email_sender=email_sender,
    hooks=AuthHooks(on_user_created=create_organization_for_new_user),
)
app.include_router(auth.router)
auth.install_exception_handlers(app)

# Mount the orgs router alongside it, reusing the same session and
# the get_current_user dependency fastauthx just gave you.
orgs = create_orgs_router(
    get_session=get_session,
    get_current_user=auth.get_current_user,
    email_sender=email_sender,
    frontend_url="http://localhost:3000",
)
app.include_router(orgs.router)
orgs.install_exception_handlers(app)
```

## Setting up a new project from scratch

This continues directly from `fastauthx`'s own
[Setting up a new project from scratch](../fastauthx#setting-up-a-new-project-from-scratch),
which you should follow first. Every command below was actually run
against a real Postgres database to write this section.

### 1. Add the dependency

From the same project you set up for `fastauthx`:

```bash
uv add "fastauthx-orgs @ git+https://github.com/Cypher012/fastapi-authkit.git#subdirectory=packages/fastauthx-orgs"
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

from fastauthx import AuthConfig, AuthHooks, ConsoleEmailSender, create_auth_router
from fastauthx_orgs import create_organization_for_new_user, create_orgs_router
from fastauthx_orgs.models import OrganizationMemberships, RoleEnum

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]

engine = create_async_engine(DATABASE_URL)
session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with session_maker() as session:
        yield session


config = AuthConfig(secret_key=SECRET_KEY, frontend_url="http://localhost:3000", secure_cookies=False)
email_sender = ConsoleEmailSender()

app = FastAPI(title="my app")

auth = create_auth_router(
    config,
    get_session=get_session,
    email_sender=email_sender,
    hooks=AuthHooks(on_user_created=create_organization_for_new_user),
)
app.include_router(auth.router)
auth.install_exception_handlers(app)

orgs = create_orgs_router(
    get_session=get_session,
    get_current_user=auth.get_current_user,
    email_sender=email_sender,
    frontend_url="http://localhost:3000",
)
app.include_router(orgs.router)
orgs.install_exception_handlers(app)


@app.delete("/orgs/{organization_id}/projects/{project_id}")
async def delete_project(
    organization_id: str,
    project_id: str,
    membership: OrganizationMemberships = Depends(orgs.require_role(RoleEnum.ADMIN)),
):
    return {"deleted": project_id, "by_role": membership.role}
```

### 3. Add its tables to your migration

Edit `alembic/env.py`, adding one import right after the `fastauthx`
one:

```python
from fastauthx.models import *  # noqa: F403 registers fastauthx's tables
from fastauthx_orgs.models import *  # noqa: F403 registers fastauthx-orgs' tables
```

### 4. Generate and run the migration

```bash
uv run alembic revision --autogenerate -m "add fastauthx-orgs tables"
uv run alembic upgrade head
```

You should see `organizations`, `organization_memberships`, and
`invitations` listed as newly created tables.

### 5. Run the app and try it

```bash
uv run uvicorn main:app --reload
```

Register a user (this fires the hook and creates their organization
automatically), then list their organizations:

```bash
RESPONSE=$(curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"correct-horse-battery","name":"Ada Lovelace"}')

TOKEN=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/orgs -H "Authorization: Bearer $TOKEN"
```

You should get back a list containing one organization, named
`"Ada Lovelace's Organization"`, with the new user as its `OWNER`.

## Endpoints

| Method | Path | Required role | Notes |
|---|---|---|---|
| POST | `/orgs` | authenticated | Creates an organization, caller becomes `OWNER` |
| GET | `/orgs` | authenticated | Lists organizations the caller belongs to |
| GET | `/orgs/{organization_id}` | any member | |
| PATCH | `/orgs/{organization_id}` | `ADMIN` or higher | Rename |
| DELETE | `/orgs/{organization_id}` | `OWNER` | Also deletes its memberships and invitations |
| GET | `/orgs/{organization_id}/members` | any member | |
| PATCH | `/orgs/{organization_id}/members/{user_id}` | `OWNER` | Change a member's role |
| DELETE | `/orgs/{organization_id}/members/{user_id}` | `ADMIN` or higher | Remove a member |
| DELETE | `/orgs/{organization_id}/members/me` | any member | Leave the organization |
| POST | `/orgs/{organization_id}/invitations` | `ADMIN` or higher | Sends an invitation email |
| GET | `/orgs/{organization_id}/invitations` | `ADMIN` or higher | List outstanding invitations |
| DELETE | `/orgs/{organization_id}/invitations/{invitation_id}` | `ADMIN` or higher | Revoke |
| GET | `/invitations/{token}` | no | Public preview, for a "you have been invited" page |
| POST | `/invitations/{token}/accept` | authenticated | Must be logged in as the invited email |

An organization always has at least one `OWNER`. Attempting to demote
or remove the last `OWNER`, or for the last `OWNER` to leave, returns
409.

## Request and response examples

**`POST /orgs`**

Request:

```json
{ "name": "Acme Inc" }
```

Response, `201 Created`:

```json
{
  "id": "8f14e45f-ceea-467e-add1-e4e9df1c3d8e",
  "name": "Acme Inc",
  "slug": "acme-inc",
  "created_at": "2026-09-08T12:00:00Z"
}
```

**`POST /orgs/{organization_id}/invitations`**

Request:

```json
{ "email": "new.hire@example.com", "role": "MEMBER" }
```

Response, `201 Created` (note there is no token field, see
[Invitations in detail](#invitations-in-detail)):

```json
{
  "id": "3c9a1b2d-1234-4a5b-8c9d-0e1f2a3b4c5d",
  "organization_id": "8f14e45f-ceea-467e-add1-e4e9df1c3d8e",
  "email": "new.hire@example.com",
  "role": "MEMBER",
  "expires_at": "2026-09-15T12:00:00Z",
  "accepted_at": null,
  "created_at": "2026-09-08T12:00:00Z"
}
```

**`GET /invitations/{token}`** (public, no auth):

```json
{
  "organization_name": "Acme Inc",
  "email": "new.hire@example.com",
  "role": "MEMBER",
  "expires_at": "2026-09-15T12:00:00Z",
  "accepted_at": null
}
```

**`POST /invitations/{token}/accept`** returns the new membership:

```json
{
  "id": "9d8c7b6a-5432-4a1b-8c9d-0e1f2a3b4c5d",
  "organization_id": "8f14e45f-ceea-467e-add1-e4e9df1c3d8e",
  "user_id": "b3b1e6b0-3e9a-4c9e-9c9a-1f2a3b4c5d6e",
  "role": "MEMBER",
  "created_at": "2026-09-08T12:05:00Z"
}
```

## Invitations in detail

- Tokens are generated with the same opaque, single use mechanism
  `fastauthx` uses for refresh and verification tokens. Only a hash is
  stored.
- Invitations expire after `invitation_expire_days` (default 7).
- Accepting an invitation checks that the authenticated user's email
  matches the invitation's email, not just that the token is valid. A
  valid token that leaked to the wrong inbox cannot be used by someone
  else.
- Re-inviting the same email to the same organization replaces the
  previous invitation rather than failing.
- No endpoint ever returns the raw token. It only ever appears once, in
  the email.

## Roles and permissions

`require_role(min_role)` answers "is this caller at least an ADMIN in
this organization." It cannot answer "can this caller delete this
specific project," because that is a decision about your app's domain,
not this package's. Build that layer yourself:

```python
from enum import Enum
from typing import Annotated
from fastapi import Depends, HTTPException
from fastauthx_orgs.models import OrganizationMemberships, RoleEnum

class Permission(str, Enum):
    PROJECT_DELETE = "project:delete"
    MEMBER_INVITE = "member:invite"
    # whatever your actual product's resources are

ROLE_PERMISSIONS: dict[RoleEnum, set[Permission]] = {
    RoleEnum.OWNER: set(Permission),
    RoleEnum.ADMIN: {Permission.PROJECT_DELETE, Permission.MEMBER_INVITE},
    RoleEnum.MEMBER: set(),
}

def require_permission(permission: Permission):
    async def dependency(
        membership: Annotated[OrganizationMemberships, Depends(orgs.get_current_membership)],
    ) -> OrganizationMemberships:
        if permission not in ROLE_PERMISSIONS[membership.role]:
            raise HTTPException(status_code=403)
        return membership
    return dependency
```

## Error responses

`orgs.install_exception_handlers(app)` registers one handler that turns
every domain exception into a JSON response of the shape
`{ "detail": "human readable message" }`, with the status codes below.

| Exception | Status | When |
|---|---|---|
| `OrganizationNotFoundError` | 404 | The organization ID does not exist |
| `NotAMemberError` | 404 | The caller is not a member of the organization (same status as not found, on purpose, see below) |
| `InsufficientRoleError` | 403 | The caller's role is below what the route requires |
| `LastOwnerError` | 409 | An action would leave the organization without an `OWNER` |
| `AlreadyAMemberError` | 409 | Inviting or accepting for someone already a member |
| `InvitationNotFoundError` | 404 | Unknown invitation token or ID |
| `InvitationAlreadyAcceptedError` | 409 | The invitation was already used |
| `InvitationEmailMismatchError` | 403 | The authenticated user's email does not match the invitation |
| `InvitationExpiredError` | 410 | The invitation existed and was valid, but its expiry has passed |

`NotAMemberError` and `OrganizationNotFoundError` deliberately share a
status code and message shape. An outsider probing organization IDs
should not be able to tell "this ID does not exist" apart from "this ID
exists but you are not in it."

## Security notes

- `get_current_membership` is checked on every organization scoped
  route. There is no route that trusts a client supplied organization
  ID without verifying membership first.
- Changing a member's role requires `OWNER`, since granting `ADMIN` or
  `OWNER` to someone is a privilege escalation sensitive action.
- An organization can never end up without an `OWNER`. Demoting,
  removing, or self removing the last `OWNER` is rejected with 409.
- Invitation acceptance is bound to the authenticated user's email, not
  just the token, closing the gap where a forwarded invitation link
  could be used by the wrong person.

## Database and migrations

```python
from fastauthx_orgs.models import Organizations, OrganizationMemberships, Invitations  # noqa: F401
```

```bash
alembic revision --autogenerate -m "add fastauthx-orgs tables"
alembic upgrade head
```

## Testing

Same shape as `fastauthx`: a real Postgres instance, no mocks, and a
minimal FastAPI app built directly with `create_orgs_router`.

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest
```

## FAQ

**Can a user belong to more than one organization?**
Yes. Membership is a separate table keyed by `(organization_id,
user_id)`, and a user can have a different role in each organization
they belong to.

**What happens to invitations when an organization is deleted?**
They are deleted along with its memberships, in the same transaction as
the organization itself.

**Why is `require_role` rank based instead of a list of allowed roles?**
Because the roles genuinely are a hierarchy in this package: `OWNER`
can do everything `ADMIN` can, and `ADMIN` can do everything `MEMBER`
can. A rank comparison says that directly instead of every call site
re-listing every allowed role.

**Can I rename `OWNER`, `ADMIN`, `MEMBER`?**
Not without forking the package today. If your app needs different
names for the same three tier hierarchy, mapping them in your own
presentation layer is simpler than changing the underlying enum.

## License

MIT
