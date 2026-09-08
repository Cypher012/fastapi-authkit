"""create_roles_kit is the only entry point. Deliberately takes
`get_current_user` as a plain parameter typed against a minimal `HasId`
Protocol rather than importing `fastauthx.models.Users` — this package
composes with *any* FastAPI auth dependency that resolves to something
with an `.id`, not specifically fastauthx's.

Composing require_permission on top: this package intentionally has no
concept of "permission" — that mapping is app-specific (see README).
A host builds it like:

    async def require_permission(permission: Permission):
        async def dependency(
            roles: Annotated[list[str], Depends(roles_kit.get_current_user_roles)],
        ) -> None:
            if not any(permission in ROLE_PERMISSIONS.get(r, set()) for r in roles):
                raise HTTPException(status_code=403)
        return dependency
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx_roles.repository import get_user_roles

GetSession = Callable[[], AsyncIterator[AsyncSession]]


class HasId(Protocol):
    id: UUID


GetCurrentUser = Callable[..., Awaitable[HasId]]
RequireRole = Callable[..., Callable[..., Awaitable[None]]]


@dataclass
class RolesKit:
    get_current_user_roles: Callable[..., Awaitable[list[str]]]
    require_role: RequireRole


def create_roles_kit(
    *, get_session: GetSession, get_current_user: GetCurrentUser
) -> RolesKit:
    async def get_current_user_roles(
        current_user: Annotated[HasId, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> list[str]:
        return await get_user_roles(session, current_user.id)

    def require_role(*roles: str) -> Callable[..., Awaitable[None]]:
        """OR semantics: passes if the user holds at least one of
        `roles`. There's no hierarchy to check "at least this rank"
        against — see README for why."""

        async def dependency(
            user_roles: Annotated[list[str], Depends(get_current_user_roles)],
        ) -> None:
            if not any(role in user_roles for role in roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have the required role.",
                )

        return dependency

    return RolesKit(
        get_current_user_roles=get_current_user_roles, require_role=require_role
    )
