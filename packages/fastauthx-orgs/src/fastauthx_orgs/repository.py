"""Data-access layer for organizations/membership. Only queries and
persistence live here — role-rank checks and hook orchestration live in
dependencies.py/hooks.py, so this stays a thin, easily-mocked boundary
to Postgres, same split as fastauthx core's AuthRepository."""

from datetime import datetime, timezone
from uuid import UUID

from fastauthx.models import Users
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx_orgs.models import Invitations, Organizations, OrganizationMemberships, RoleEnum


class OrgsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def create_organization(self, *, name: str, slug: str) -> Organizations:
        organization = Organizations(name=name, slug=slug)
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def get_organization_by_id(
        self, organization_id: UUID
    ) -> Organizations | None:
        return await self._session.get(Organizations, organization_id)

    async def get_organization_by_slug(self, slug: str) -> Organizations | None:
        result = await self._session.exec(
            select(Organizations).where(Organizations.slug == slug)
        )
        return result.first()

    async def update_organization_name(
        self, organization: Organizations, name: str
    ) -> None:
        organization.name = name
        self._session.add(organization)
        await self._session.flush()

    async def delete_organization(self, organization: Organizations) -> None:
        await self._session.delete(organization)
        await self._session.flush()

    async def create_membership(
        self, *, organization_id: UUID, user_id: UUID, role: RoleEnum
    ) -> OrganizationMemberships:
        membership = OrganizationMemberships(
            organization_id=organization_id, user_id=user_id, role=role
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def get_membership(
        self, *, organization_id: UUID, user_id: UUID
    ) -> OrganizationMemberships | None:
        result = await self._session.exec(
            select(OrganizationMemberships).where(
                OrganizationMemberships.organization_id == organization_id,
                OrganizationMemberships.user_id == user_id,
            )
        )
        return result.first()

    async def list_memberships_for_organization(
        self, organization_id: UUID
    ) -> list[OrganizationMemberships]:
        result = await self._session.exec(
            select(OrganizationMemberships).where(
                OrganizationMemberships.organization_id == organization_id
            )
        )
        return list(result.all())

    async def delete_all_memberships_for_organization(
        self, organization_id: UUID
    ) -> None:
        """There's no ON DELETE CASCADE on organization_memberships — an
        org must have its memberships cleared before it can be deleted,
        otherwise Postgres raises a foreign-key violation."""
        memberships = await self.list_memberships_for_organization(organization_id)
        for membership in memberships:
            await self._session.delete(membership)
        await self._session.flush()

    async def list_organizations_for_user(
        self, user_id: UUID
    ) -> list[Organizations]:
        result = await self._session.exec(
            select(Organizations)
            .join(
                OrganizationMemberships,
                OrganizationMemberships.organization_id == Organizations.id,
            )
            .where(OrganizationMemberships.user_id == user_id)
        )
        return list(result.all())

    async def count_members_with_role(
        self, *, organization_id: UUID, role: RoleEnum
    ) -> int:
        """Used to stop the last OWNER of an organization from being
        demoted or removed, which would leave it ownerless."""
        result = await self._session.exec(
            select(OrganizationMemberships).where(
                OrganizationMemberships.organization_id == organization_id,
                OrganizationMemberships.role == role,
            )
        )
        return len(result.all())

    async def update_membership_role(
        self, membership: OrganizationMemberships, role: RoleEnum
    ) -> None:
        membership.role = role
        self._session.add(membership)
        await self._session.flush()

    async def delete_membership(self, membership: OrganizationMemberships) -> None:
        await self._session.delete(membership)
        await self._session.flush()

    async def get_user_by_email(self, email: str) -> Users | None:
        """The one place this repository reaches across into fastauthx's
        `users` table — needed to check "is this invited email already a
        member" before sending an invitation."""
        result = await self._session.exec(select(Users).where(Users.email == email))
        return result.first()

    async def create_invitation(
        self,
        *,
        organization_id: UUID,
        email: str,
        role: RoleEnum,
        token_hash: str,
        expires_at: datetime,
    ) -> Invitations:
        invitation = Invitations(
            organization_id=organization_id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(invitation)
        await self._session.flush()
        return invitation

    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitations | None:
        return await self._session.get(Invitations, invitation_id)

    async def get_invitation_by_token_hash(
        self, token_hash: str
    ) -> Invitations | None:
        result = await self._session.exec(
            select(Invitations).where(Invitations.token_hash == token_hash)
        )
        return result.first()

    async def get_pending_invitation(
        self, *, organization_id: UUID, email: str
    ) -> Invitations | None:
        result = await self._session.exec(
            select(Invitations).where(
                Invitations.organization_id == organization_id,
                Invitations.email == email,
                Invitations.accepted_at.is_(None),
            )
        )
        return result.first()

    async def list_invitations_for_organization(
        self, organization_id: UUID
    ) -> list[Invitations]:
        result = await self._session.exec(
            select(Invitations).where(Invitations.organization_id == organization_id)
        )
        return list(result.all())

    async def delete_all_invitations_for_organization(
        self, organization_id: UUID
    ) -> None:
        invitations = await self.list_invitations_for_organization(organization_id)
        for invitation in invitations:
            await self._session.delete(invitation)
        await self._session.flush()

    async def delete_invitation(self, invitation: Invitations) -> None:
        await self._session.delete(invitation)
        await self._session.flush()

    async def mark_invitation_accepted(self, invitation: Invitations) -> None:
        invitation.accepted_at = datetime.now(timezone.utc)
        self._session.add(invitation)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
