"""fastauthx-orgs' public surface."""

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
from fastauthx_orgs.hooks import create_organization_for_new_user
from fastauthx_orgs.models import (
    ROLE_RANK,
    Invitations,
    OrganizationMemberships,
    Organizations,
    RoleEnum,
)
from fastauthx_orgs.routes import OrgsKit, create_orgs_router

__all__ = [
    "ROLE_RANK",
    "AlreadyAMemberError",
    "InsufficientRoleError",
    "Invitations",
    "InvitationAlreadyAcceptedError",
    "InvitationEmailMismatchError",
    "InvitationExpiredError",
    "InvitationNotFoundError",
    "LastOwnerError",
    "NotAMemberError",
    "OrgsError",
    "OrgsKit",
    "OrganizationMemberships",
    "OrganizationNotFoundError",
    "Organizations",
    "RoleEnum",
    "create_orgs_router",
    "create_organization_for_new_user",
]
