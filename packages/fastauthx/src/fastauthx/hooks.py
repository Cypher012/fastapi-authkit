"""The extension point that lets a host app react to auth events without
fastauthx needing to know what it's reacting with — e.g. an orgs/RBAC layer
creating an organization and an OWNER membership the moment a user is
created, via a foreign key into `Users.id` it owns itself.

Hooks run *inside* AuthService's existing transaction, before commit —
raising from a hook aborts the whole operation (e.g. a failed org-slug
allocation rolls back the user creation too), and hooks never see a
half-committed user.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import Users

OnUserCreated = Callable[[Users, AsyncSession], Awaitable[None]]


@dataclass
class AuthHooks:
    on_user_created: OnUserCreated | None = None
    """Called once, right after a brand-new user is persisted (`flush`ed
    but not yet committed) — for both password registration and a
    user's first Google sign-in. Not called for repeat logins, and not
    called when a Google login links to an *existing* user."""
