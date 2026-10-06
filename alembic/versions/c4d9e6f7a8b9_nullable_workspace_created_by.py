"""nullable_workspace_created_by_on_user_delete

Revision ID: c4d9e6f7a8b9
Revises: b3c8d5e6f7a8
Create Date: 2026-10-06 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d9e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c8d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow deleting users without deleting workspaces they created.
    op.alter_column(
        "workspaces",
        "created_by_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.drop_constraint("workspaces_created_by_id_fkey", "workspaces", type_="foreignkey")
    op.create_foreign_key(
        "workspaces_created_by_id_fkey",
        "workspaces",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("workspaces_created_by_id_fkey", "workspaces", type_="foreignkey")
    op.execute("UPDATE workspaces SET created_by_id = (SELECT id FROM users ORDER BY id LIMIT 1) WHERE created_by_id IS NULL")
    op.alter_column(
        "workspaces",
        "created_by_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "workspaces_created_by_id_fkey",
        "workspaces",
        "users",
        ["created_by_id"],
        ["id"],
    )
