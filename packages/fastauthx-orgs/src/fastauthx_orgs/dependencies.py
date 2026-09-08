"""FastAPI dependency wiring, built once by create_orgs_router and
closed over get_session/get_current_user — same factory pattern as
fastauthx core and fastauthx-roles, for the same reason: no global state,
so multiple create_orgs_router calls in one process never collide.

Composing require_permission on top: like fastauthx-roles, this package
has no concept of "permission" — see README. A host builds one like:

    async def require_permission(permission: Permission):
        async def dependency(
            membership: Annotated[OrganizationMemberships, Depends(orgs.get_current_membership)],
        ) -> OrganizationMemberships:
            if permission not in ROLE_PERMISSIONS[membership.role]:
                raise HTTPException(status_code=403)
            return membership
        return dependency
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastauthx.models import Users
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx_orgs.exceptions import InsufficientRoleError, NotAMemberError
from fastauthx_orgs.models import ROLE_RANK, OrganizationMemberships, RoleEnum
from fastauthx_orgs.repository import OrgsRepository

GetSession = Callable[[], AsyncIterator[AsyncSession]]

# Unlike fastauthx-roles, this package already hard-depends on fastauthx
# core (hooks.py implements fastauthx's own AuthHooks contract), so there's
# no reason to decouple get_current_user's type behind a generic
# Protocol here — it's always fastauthx.models.Users in practice, and
# routes.py needs `.email`, not just `.id`.
GetCurrentUser = Callable[..., Awaitable[Users]]
GetCurrentMembership = Callable[..., Awaitable[OrganizationMemberships]]


@dataclass
class OrgsDependencies:
    get_current_membership: GetCurrentMembership
    require_role: Callable[[RoleEnum], GetCurrentMembership]


def build_dependencies(
    *, get_session: GetSession, get_current_user: GetCurrentUser
) -> OrgsDependencies:
    async def get_current_membership(
        organization_id: UUID,
        current_user: Annotated[Users, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> OrganizationMemberships:
        """`organization_id` is a path parameter — FastAPI matches this
        name against `{organization_id}` in whatever route depends on
        this, even through nested Depends(). Never trust it without this
        check: 404s (not 403s) if the caller isn't a member, so an
        outsider can't distinguish "wrong org ID" from "org exists but
        you're not in it"."""
        membership = await OrgsRepository(session).get_membership(
            organization_id=organization_id, user_id=current_user.id
        )
        if membership is None:
            raise NotAMemberError()
        return membership

    def require_role(min_role: RoleEnum) -> GetCurrentMembership:
        async def dependency(
            membership: Annotated[
                OrganizationMemberships, Depends(get_current_membership)
            ],
        ) -> OrganizationMemberships:
            if ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
                raise InsufficientRoleError()
            return membership

        return dependency

    return OrgsDependencies(
        get_current_membership=get_current_membership, require_role=require_role
    )
