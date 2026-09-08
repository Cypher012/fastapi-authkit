# fastauthx-orgs

Multi tenant organizations, membership, rank based role checks, and
invitations, built on top of [`fastauthx`](../fastauthx). For a single
global role per user with no tenancy at all, see
[`fastauthx-roles`](../fastauthx-roles) instead.

```bash
pip install fastauthx-orgs
```

## What it ships

- `RoleEnum` (`OWNER` / `ADMIN` / `MEMBER`) as a ranked hierarchy, not
  an unordered set. `OWNER` outranks `ADMIN` outranks `MEMBER`,
  matching the fact that each tier is a superset of the one below.
- `get_current_membership(organization_id)`, a dependency that resolves
  the caller's membership in the organization named by a path
  parameter, and returns 404 if none exists. This is what makes "never
  trust an organization ID from the client without checking
  membership" actually true on every route, not just the ones someone
  remembered to guard.
- `require_role(min_role)`, built on `get_current_membership`, which
  returns 403 if the caller's rank is below `min_role`.
- `create_organization_for_new_user`, an `AuthHooks.on_user_created`
  callback (from `fastauthx` core) that gives every new user their own
  organization and `OWNER` membership.
- Full organization CRUD, membership management, and an invitation
  flow: invite by email, preview an invitation by token, accept it, or
  revoke it. Invitation email reuses `fastauthx`'s `EmailSender` port,
  the same one you already configured for verification and password
  reset email.
- `create_orgs_router(...)`, the single entry point that wires all of
  the above into your FastAPI app.

## What it deliberately does not ship

A `Permission` enum or a role to permission mapping. What permissions
mean in your app (`project:delete`, `invoice:void`, and so on) is
inherently specific to your app's actual resources. A generic package
cannot enumerate them meaningfully. Build `require_permission` in your
own app on top of `get_current_membership`. See the example near the
bottom of this README.

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

Then register the tables and migrate, same as `fastauthx`:

```python
from fastauthx_orgs.models import Organizations, OrganizationMemberships, Invitations  # noqa: F401
# now run: alembic revision --autogenerate -m "add fastauthx-orgs tables"
```

Protect your own routes with `require_role` or `get_current_membership`:

```python
from typing import Annotated
from fastapi import Depends
from fastauthx_orgs.models import RoleEnum, OrganizationMemberships

@app.delete("/orgs/{organization_id}/projects/{project_id}")
async def delete_project(
    organization_id: str,
    project_id: str,
    membership: Annotated[OrganizationMemberships, Depends(orgs.require_role(RoleEnum.ADMIN))],
):
    ...
```

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

## Building `require_permission` on top

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

## Testing

Same shape as `fastauthx`: a real Postgres instance, no mocks, and a
minimal FastAPI app built directly with `create_orgs_router`.

```bash
export POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=...
uv run pytest
```

## License

MIT
