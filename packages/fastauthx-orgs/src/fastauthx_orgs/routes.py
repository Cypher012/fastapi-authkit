"""create_orgs_router(...) is the only public entry point. Routes here
are thin: parse request -> call OrgsService/OrgsRepository -> shape
response. Role gating happens via Depends(deps.require_role(...)) /
Depends(deps.get_current_membership), never by hand in a route body.

The returned router combines two sub-routers: one prefixed "/orgs" (org
CRUD, membership, and org-scoped invitation creation/revocation — these
naturally start with {organization_id}), and one prefixed "/invitations"
(the token-based public preview/accept routes, which aren't org-scoped
in their URL since the token alone identifies everything).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastauthx.email.base import EmailSender
from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.models import Users
from fastauthx_orgs.dependencies import (
    GetCurrentMembership,
    GetCurrentUser,
    GetSession,
    build_dependencies,
)
from fastauthx_orgs.email_service import OrgsEmailService
from fastauthx_orgs.exceptions import (
    AlreadyAMemberError,
    InsufficientRoleError,
    InvitationAlreadyAcceptedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    LastOwnerError,
    NotAMemberError,
    OrganizationNotFoundError,
    OrgsError,
)
from fastauthx_orgs.models import OrganizationMemberships, Organizations, RoleEnum
from fastauthx_orgs.repository import OrgsRepository
from fastauthx_orgs.schemas import (
    InvitationCreate,
    InvitationPreview,
    InvitationPublic,
    MembershipPublic,
    MembershipRoleUpdate,
    OrganizationCreate,
    OrganizationPublic,
    OrganizationUpdate,
)
from fastauthx_orgs.service import OrgsService

_STATUS_BY_ORGS_ERROR: dict[type[OrgsError], int] = {
    OrganizationNotFoundError: status.HTTP_404_NOT_FOUND,
    NotAMemberError: status.HTTP_404_NOT_FOUND,
    InsufficientRoleError: status.HTTP_403_FORBIDDEN,
    LastOwnerError: status.HTTP_409_CONFLICT,
    AlreadyAMemberError: status.HTTP_409_CONFLICT,
    InvitationNotFoundError: status.HTTP_404_NOT_FOUND,
    InvitationAlreadyAcceptedError: status.HTTP_409_CONFLICT,
    InvitationEmailMismatchError: status.HTTP_403_FORBIDDEN,
    # 410, not 400: the invitation existed and was valid — it just isn't
    # any more. That's a meaningfully different fact than a malformed
    # request, and 410 Gone says so directly.
    InvitationExpiredError: status.HTTP_410_GONE,
}


@dataclass
class OrgsKit:
    router: APIRouter
    get_current_membership: GetCurrentMembership
    require_role: Callable[[RoleEnum], GetCurrentMembership]
    install_exception_handlers: Callable[[FastAPI], None]


def create_orgs_router(
    *,
    get_session: GetSession,
    get_current_user: GetCurrentUser,
    email_sender: EmailSender,
    frontend_url: str,
    invitation_expire_days: int = 7,
) -> OrgsKit:
    deps = build_dependencies(get_session=get_session, get_current_user=get_current_user)
    email_service = OrgsEmailService(email_sender=email_sender, frontend_url=frontend_url)

    def _build_service(session: AsyncSession) -> OrgsService:
        return OrgsService(
            OrgsRepository(session),
            email_service=email_service,
            invitation_expire_days=invitation_expire_days,
        )

    orgs_router = APIRouter(prefix="/orgs", tags=["orgs"])
    invitations_router = APIRouter(prefix="/invitations", tags=["invitations"])

    async def _get_organization_or_404(
        session: AsyncSession, organization_id: UUID
    ) -> Organizations:
        organization = await OrgsRepository(session).get_organization_by_id(
            organization_id
        )
        if organization is None:
            raise OrganizationNotFoundError()
        return organization

    @orgs_router.post(
        "", response_model=OrganizationPublic, status_code=status.HTTP_201_CREATED
    )
    async def create_organization(
        data: OrganizationCreate,
        current_user: Annotated[Users, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> OrganizationPublic:
        organization = await _build_service(session).create_organization_with_owner(
            name=data.name, user_id=current_user.id
        )
        return OrganizationPublic.model_validate(organization)

    @orgs_router.get("", response_model=list[OrganizationPublic])
    async def list_my_organizations(
        current_user: Annotated[Users, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> list[OrganizationPublic]:
        organizations = await OrgsRepository(session).list_organizations_for_user(
            current_user.id
        )
        return [OrganizationPublic.model_validate(org) for org in organizations]

    @orgs_router.get("/{organization_id}", response_model=OrganizationPublic)
    async def get_organization(
        organization_id: UUID,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.get_current_membership)
        ],
    ) -> OrganizationPublic:
        organization = await _get_organization_or_404(session, organization_id)
        return OrganizationPublic.model_validate(organization)

    @orgs_router.patch("/{organization_id}", response_model=OrganizationPublic)
    async def rename_organization(
        organization_id: UUID,
        data: OrganizationUpdate,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.ADMIN))
        ],
    ) -> OrganizationPublic:
        organization = await _get_organization_or_404(session, organization_id)
        await _build_service(session).rename_organization(organization, data.name)
        return OrganizationPublic.model_validate(organization)

    @orgs_router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_organization(
        organization_id: UUID,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.OWNER))
        ],
    ) -> None:
        organization = await _get_organization_or_404(session, organization_id)
        await _build_service(session).delete_organization(organization)

    @orgs_router.get(
        "/{organization_id}/members", response_model=list[MembershipPublic]
    )
    async def list_members(
        organization_id: UUID,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.get_current_membership)
        ],
    ) -> list[MembershipPublic]:
        memberships = await OrgsRepository(session).list_memberships_for_organization(
            organization_id
        )
        return [MembershipPublic.model_validate(m) for m in memberships]

    @orgs_router.patch(
        "/{organization_id}/members/{user_id}", response_model=MembershipPublic
    )
    async def change_member_role(
        organization_id: UUID,
        user_id: UUID,
        data: MembershipRoleUpdate,
        session: Annotated[AsyncSession, Depends(get_session)],
        _requester: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.OWNER))
        ],
    ) -> MembershipPublic:
        """OWNER-only: changing someone's role (including granting OWNER)
        is a privilege-escalation-sensitive action."""
        repository = OrgsRepository(session)
        target = await repository.get_membership(
            organization_id=organization_id, user_id=user_id
        )
        if target is None:
            raise NotAMemberError()
        await _build_service(session).change_member_role(target, data.role)
        return MembershipPublic.model_validate(target)

    # Registered before "/members/{user_id}" below: Starlette matches
    # path patterns in registration order, and a bare {user_id} would
    # otherwise swallow "/members/me" and fail UUID parsing before this
    # literal route is ever reached.
    @orgs_router.delete(
        "/{organization_id}/members/me", status_code=status.HTTP_204_NO_CONTENT
    )
    async def leave_organization(
        session: Annotated[AsyncSession, Depends(get_session)],
        membership: Annotated[
            OrganizationMemberships, Depends(deps.get_current_membership)
        ],
    ) -> None:
        """Any member can leave — gated by get_current_membership alone
        (any role), not require_role. Still blocked if the caller is the
        organization's last OWNER (see OrgsService._guard_last_owner) —
        transfer ownership first."""
        await _build_service(session).remove_member(membership)

    @orgs_router.delete(
        "/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    async def remove_member(
        organization_id: UUID,
        user_id: UUID,
        session: Annotated[AsyncSession, Depends(get_session)],
        _requester: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.ADMIN))
        ],
    ) -> None:
        repository = OrgsRepository(session)
        target = await repository.get_membership(
            organization_id=organization_id, user_id=user_id
        )
        if target is None:
            raise NotAMemberError()
        await _build_service(session).remove_member(target)

    @orgs_router.post(
        "/{organization_id}/invitations",
        response_model=InvitationPublic,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_invitation(
        organization_id: UUID,
        data: InvitationCreate,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.ADMIN))
        ],
    ) -> InvitationPublic:
        organization = await _get_organization_or_404(session, organization_id)
        invitation = await _build_service(session).invite_member(
            organization=organization, email=data.email, role=data.role
        )
        return InvitationPublic.model_validate(invitation)

    @orgs_router.get(
        "/{organization_id}/invitations", response_model=list[InvitationPublic]
    )
    async def list_invitations(
        organization_id: UUID,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.ADMIN))
        ],
    ) -> list[InvitationPublic]:
        invitations = await OrgsRepository(session).list_invitations_for_organization(
            organization_id
        )
        return [InvitationPublic.model_validate(i) for i in invitations]

    @orgs_router.delete(
        "/{organization_id}/invitations/{invitation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def revoke_invitation(
        organization_id: UUID,
        invitation_id: UUID,
        session: Annotated[AsyncSession, Depends(get_session)],
        _membership: Annotated[
            OrganizationMemberships, Depends(deps.require_role(RoleEnum.ADMIN))
        ],
    ) -> None:
        repository = OrgsRepository(session)
        invitation = await repository.get_invitation_by_id(invitation_id)
        if invitation is None or invitation.organization_id != organization_id:
            raise InvitationNotFoundError()
        await _build_service(session).revoke_invitation(invitation)

    @invitations_router.get("/{token}", response_model=InvitationPreview)
    async def preview_invitation(
        token: str,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> InvitationPreview:
        """Public — no auth required, so a frontend can show "You've been
        invited to join {org}" before asking the user to log in/sign up."""
        service = _build_service(session)
        invitation = await service.get_invitation_by_token(token)
        organization = await OrgsRepository(session).get_organization_by_id(
            invitation.organization_id
        )
        if organization is None:
            raise InvitationNotFoundError()
        return InvitationPreview(
            organization_name=organization.name,
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
        )

    @invitations_router.post("/{token}/accept", response_model=MembershipPublic)
    async def accept_invitation(
        token: str,
        current_user: Annotated[Users, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> MembershipPublic:
        """Requires authentication: the milestone's "verify the accepting
        user is the intended recipient" rule needs a real identity to
        check the invitation's email against (OrgsService raises
        InvitationEmailMismatchError if they don't match)."""
        membership = await _build_service(session).accept_invitation(
            token, user_id=current_user.id, user_email=current_user.email
        )
        return MembershipPublic.model_validate(membership)

    def install_exception_handlers(app: FastAPI) -> None:
        @app.exception_handler(OrgsError)
        async def orgs_error_handler(request: Request, exc: OrgsError) -> JSONResponse:
            status_code = _STATUS_BY_ORGS_ERROR.get(
                type(exc), status.HTTP_400_BAD_REQUEST
            )
            return JSONResponse(
                status_code=status_code, content={"detail": str(exc)}
            )

    router = APIRouter()
    router.include_router(orgs_router)
    router.include_router(invitations_router)

    return OrgsKit(
        router=router,
        get_current_membership=deps.get_current_membership,
        require_role=deps.require_role,
        install_exception_handlers=install_exception_handlers,
    )
