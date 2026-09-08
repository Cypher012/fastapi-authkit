"""Business rules for organizations/membership/invitations. Same shape
as fastauthx core's AuthService: depends on a repository (and, for
invitations, an email service) handed to it, raises domain exceptions
instead of HTTPException, commits once per logical operation.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastauthx.security import generate_opaque_token, hash_opaque_token

from fastauthx_orgs.email_service import OrgsEmailService
from fastauthx_orgs.exceptions import (
    AlreadyAMemberError,
    InvitationAlreadyAcceptedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    LastOwnerError,
)
from fastauthx_orgs.models import (
    Invitations,
    OrganizationMemberships,
    Organizations,
    RoleEnum,
)
from fastauthx_orgs.repository import OrgsRepository
from fastauthx_orgs.utils import slugify


class OrgsService:
    def __init__(
        self,
        repository: OrgsRepository,
        email_service: OrgsEmailService | None = None,
        invitation_expire_days: int = 7,
    ) -> None:
        self._repository = repository
        self._email_service = email_service
        self._invitation_expire_days = invitation_expire_days

    async def create_organization_with_owner(
        self, *, name: str, user_id: UUID
    ) -> Organizations:
        slug = await self._unique_slug(name)
        organization = await self._repository.create_organization(name=name, slug=slug)
        await self._repository.create_membership(
            organization_id=organization.id, user_id=user_id, role=RoleEnum.OWNER
        )
        await self._repository.commit()
        return organization

    async def rename_organization(self, organization: Organizations, name: str) -> None:
        await self._repository.update_organization_name(organization, name)
        await self._repository.commit()

    async def delete_organization(self, organization: Organizations) -> None:
        """Memberships and invitations have no ON DELETE CASCADE, so
        they're cleared explicitly, in the same transaction, before the
        organization itself is deleted."""
        await self._repository.delete_all_memberships_for_organization(
            organization.id
        )
        await self._repository.delete_all_invitations_for_organization(
            organization.id
        )
        await self._repository.delete_organization(organization)
        await self._repository.commit()

    async def change_member_role(
        self, membership: OrganizationMemberships, new_role: RoleEnum
    ) -> None:
        await self._guard_last_owner(membership, becoming_role=new_role)
        await self._repository.update_membership_role(membership, new_role)
        await self._repository.commit()

    async def remove_member(self, membership: OrganizationMemberships) -> None:
        await self._guard_last_owner(membership, becoming_role=None)
        await self._repository.delete_membership(membership)
        await self._repository.commit()

    async def invite_member(
        self, *, organization: Organizations, email: str, role: RoleEnum
    ) -> Invitations:
        """Re-inviting an email that already has a pending invitation
        replaces it (fresh token, fresh expiry) rather than erroring —
        the old link simply stops working."""
        existing_user = await self._repository.get_user_by_email(email)
        if existing_user is not None:
            existing_membership = await self._repository.get_membership(
                organization_id=organization.id, user_id=existing_user.id
            )
            if existing_membership is not None:
                raise AlreadyAMemberError()

        existing_invitation = await self._repository.get_pending_invitation(
            organization_id=organization.id, email=email
        )
        if existing_invitation is not None:
            await self._repository.delete_invitation(existing_invitation)

        raw_token = generate_opaque_token()
        token_hash = hash_opaque_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=self._invitation_expire_days
        )
        invitation = await self._repository.create_invitation(
            organization_id=organization.id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self._repository.commit()

        if self._email_service is None:
            raise RuntimeError(
                "invite_member() requires OrgsService to be constructed with "
                "an email_service — it was built without one."
            )
        await self._email_service.send_invitation_email(
            to_email=email, organization_name=organization.name, raw_token=raw_token
        )
        return invitation

    async def get_invitation_by_token(self, raw_token: str) -> Invitations:
        token_hash = hash_opaque_token(raw_token)
        invitation = await self._repository.get_invitation_by_token_hash(token_hash)
        if invitation is None:
            raise InvitationNotFoundError()
        return invitation

    async def accept_invitation(
        self, raw_token: str, *, user_id: UUID, user_email: str
    ) -> OrganizationMemberships:
        invitation = await self.get_invitation_by_token(raw_token)

        if invitation.accepted_at is not None:
            raise InvitationAlreadyAcceptedError()
        if invitation.expires_at < datetime.now(timezone.utc):
            raise InvitationExpiredError()
        # Milestone's rule: verify the accepting user is the intended
        # recipient — a valid token alone isn't enough if it leaked to
        # someone else's inbox forward.
        if invitation.email.lower() != user_email.lower():
            raise InvitationEmailMismatchError()

        existing_membership = await self._repository.get_membership(
            organization_id=invitation.organization_id, user_id=user_id
        )
        if existing_membership is not None:
            raise AlreadyAMemberError()

        membership = await self._repository.create_membership(
            organization_id=invitation.organization_id,
            user_id=user_id,
            role=invitation.role,
        )
        await self._repository.mark_invitation_accepted(invitation)
        await self._repository.commit()
        return membership

    async def revoke_invitation(self, invitation: Invitations) -> None:
        await self._repository.delete_invitation(invitation)
        await self._repository.commit()

    async def _guard_last_owner(
        self, membership: OrganizationMemberships, *, becoming_role: RoleEnum | None
    ) -> None:
        """Blocks demoting/removing an organization's only OWNER — either
        would leave it ownerless. `becoming_role=None` means "being
        removed entirely" rather than changed to a specific role."""
        if membership.role != RoleEnum.OWNER or becoming_role == RoleEnum.OWNER:
            return
        owner_count = await self._repository.count_members_with_role(
            organization_id=membership.organization_id, role=RoleEnum.OWNER
        )
        if owner_count <= 1:
            raise LastOwnerError()

    async def _unique_slug(self, name: str) -> str:
        base_slug = slugify(name)
        slug = base_slug
        while await self._repository.get_organization_by_slug(slug) is not None:
            slug = f"{base_slug}-{secrets.token_hex(3)}"
        return slug
