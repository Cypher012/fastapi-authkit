"""The AuthHooks.on_user_created implementation — this is the one file
in this package that has to match fastauthx core's exact hook contract
(Callable[[Users, AsyncSession], Awaitable[None]]), since it's built
specifically to plug into it.
"""

from fastauthx.models import Users
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx_orgs.repository import OrgsRepository
from fastauthx_orgs.service import OrgsService


async def create_organization_for_new_user(user: Users, session: AsyncSession) -> None:
    """New signups don't choose an organization name up front — they get
    a default (`"{name}'s Organization"`) and can rename it later via
    OrgsService.rename_organization."""
    service = OrgsService(OrgsRepository(session))
    await service.create_organization_with_owner(
        name=f"{user.name}'s Organization", user_id=user.id
    )
