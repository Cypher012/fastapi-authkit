from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from fastauthx_orgs.models import RoleEnum


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationPublic(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MembershipPublic(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: RoleEnum
    created_at: datetime

    model_config = {"from_attributes": True}


class MembershipRoleUpdate(BaseModel):
    role: RoleEnum


class InvitationCreate(BaseModel):
    email: EmailStr
    role: RoleEnum = RoleEnum.MEMBER


class InvitationPublic(BaseModel):
    """Never includes the token — see README/milestone notes: "do not
    expose the raw stored token." This is used for the org-facing list
    of outstanding invitations, not the public token-preview endpoint."""

    id: UUID
    organization_id: UUID
    email: str
    role: RoleEnum
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitationPreview(BaseModel):
    """What GET /invitations/{token} returns — enough for a frontend to
    render "You've been invited to join {organization_name}" before the
    user decides whether to accept, without requiring auth first."""

    organization_name: str
    email: str
    role: RoleEnum
    expires_at: datetime
    accepted_at: datetime | None
