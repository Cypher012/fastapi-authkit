# fastauthx-roles

Global, non tenant role gating for FastAPI apps. For multi tenant,
per organization roles, see [`fastauthx-orgs`](../fastauthx-orgs)
instead. This package is for apps that just want "is this user an
admin" without any concept of organizations.

```bash
uv add fastauthx-roles
# or: pip install fastauthx-roles
```

## What it ships

- One table, `user_roles(user_id, role)`. `role` is a plain string, not
  a fixed enum, because a global role vocabulary varies too much per
  app to hardcode. One app wants `ADMIN` / `USER`, another wants
  `SUPERADMIN` / `SUPPORT` / `USER`, another just wants a `staff` flag.
  A user can hold more than one role.
- `assign_role(session, user_id, role)` and
  `revoke_role(session, user_id, role)`, both idempotent.
- `get_user_roles(session, user_id)`.
- `create_roles_kit(get_session, get_current_user)`, which returns
  `require_role(*roles)`, a dependency with OR semantics: it passes if
  the caller holds at least one of the listed roles. There is no
  hierarchy, since there is no universal ordering across arbitrary
  app defined role strings.

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

Then register the table and migrate:

```python
from fastauthx_roles.models import UserRole  # noqa: F401
# now run: alembic revision --autogenerate -m "add fastauthx-roles table"
```

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

## Testing

A real Postgres instance, no mocks. The test suite creates its one
table itself and drops it again afterward, since this package (unlike
`fastauthx-orgs`) is not expected to already be part of your app's
migrated schema.

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest
```

## License

MIT
