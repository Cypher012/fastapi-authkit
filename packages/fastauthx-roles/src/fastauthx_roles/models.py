"""The only table this package owns. FK's into `users.id` — it assumes
that table exists (e.g. from `fastauthx` core) but doesn't import
`fastauthx.models.Users` itself; the foreign key is just a table-name
string, resolved by SQLAlchemy's mapper configuration, not a Python
import. As with `fastauthx`/`fastauthx-orgs`, no migrations are shipped —
a host imports this class onto its own SQLModel.metadata and runs its
own Alembic migration.
"""

from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, UniqueConstraint


class UserRole(SQLModel, table=True):
    __tablename__: str = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    role: str = Field(nullable=False, index=True)
