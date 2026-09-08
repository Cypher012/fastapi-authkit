"""fastauthx-roles' public surface."""

from fastauthx_roles.dependencies import RolesKit, create_roles_kit
from fastauthx_roles.models import UserRole
from fastauthx_roles.repository import assign_role, get_user_roles, revoke_role

__all__ = [
    "RolesKit",
    "UserRole",
    "assign_role",
    "create_roles_kit",
    "get_user_roles",
    "revoke_role",
]
