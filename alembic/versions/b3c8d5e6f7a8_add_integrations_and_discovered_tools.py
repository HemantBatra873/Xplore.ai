"""add_integrations_and_discovered_tools

Revision ID: b3c8d5e6f7a8
Revises: a2b7c4d5e6f7
Create Date: 2026-10-06 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c8d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b7c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_integrations_workspace_name"),
    )
    op.create_index("ix_integrations_id", "integrations", ["id"])
    op.create_index("ix_integrations_workspace_id", "integrations", ["workspace_id"])
    op.create_index("ix_integrations_created_by_id", "integrations", ["created_by_id"])
    op.create_index("ix_integrations_type", "integrations", ["type"])
    op.create_index("ix_integrations_is_enabled", "integrations", ["is_enabled"])

    op.create_table(
        "integration_tools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "integration_id",
            sa.Integer(),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remote_name", sa.String(length=200), nullable=False),
        sa.Column("registry_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_schema_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "discovered_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "integration_id", "remote_name", name="uq_integration_tools_integration_remote"
        ),
    )
    op.create_index("ix_integration_tools_id", "integration_tools", ["id"])
    op.create_index("ix_integration_tools_integration_id", "integration_tools", ["integration_id"])
    op.create_index("ix_integration_tools_registry_name", "integration_tools", ["registry_name"])


def downgrade() -> None:
    op.drop_table("integration_tools")
    op.drop_index("ix_integrations_is_enabled", table_name="integrations")
    op.drop_index("ix_integrations_type", table_name="integrations")
    op.drop_index("ix_integrations_created_by_id", table_name="integrations")
    op.drop_index("ix_integrations_workspace_id", table_name="integrations")
    op.drop_index("ix_integrations_id", table_name="integrations")
    op.drop_table("integrations")
