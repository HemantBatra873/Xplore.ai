"""add_agents_and_conversation_agent_link

Revision ID: a2b7c4d5e6f7
Revises: f1a6b3c4d5e6
Create Date: 2026-10-05 15:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b7c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a6b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "system_prompt",
            sa.Text(),
            nullable=False,
            server_default="You are a helpful assistant for Xplore.ai.",
        ),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("enabled_tools", sa.String(length=1000), nullable=True),
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
        sa.UniqueConstraint("workspace_id", "name", name="uq_agents_workspace_name"),
    )
    op.create_index("ix_agents_id", "agents", ["id"])
    op.create_index("ix_agents_workspace_id", "agents", ["workspace_id"])
    op.create_index("ix_agents_created_by_id", "agents", ["created_by_id"])
    op.create_index("ix_agents_is_enabled", "agents", ["is_enabled"])

    op.create_table(
        "agent_knowledge_bases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_base_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "agent_id", "knowledge_base_id", name="uq_agent_knowledge_bases_agent_kb"
        ),
    )
    op.create_index("ix_agent_knowledge_bases_id", "agent_knowledge_bases", ["id"])
    op.create_index("ix_agent_knowledge_bases_agent_id", "agent_knowledge_bases", ["agent_id"])
    op.create_index(
        "ix_agent_knowledge_bases_knowledge_base_id",
        "agent_knowledge_bases",
        ["knowledge_base_id"],
    )

    op.add_column(
        "conversations",
        sa.Column("agent_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_conversations_agent_id", "conversations", ["agent_id"])
    op.create_foreign_key(
        "fk_conversations_agent_id",
        "conversations",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("messages", sa.Column("tool_calls_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "tool_calls_json")
    op.drop_constraint("fk_conversations_agent_id", "conversations", type_="foreignkey")
    op.drop_index("ix_conversations_agent_id", table_name="conversations")
    op.drop_column("conversations", "agent_id")
    op.drop_table("agent_knowledge_bases")
    op.drop_index("ix_agents_is_enabled", table_name="agents")
    op.drop_index("ix_agents_created_by_id", table_name="agents")
    op.drop_index("ix_agents_workspace_id", table_name="agents")
    op.drop_index("ix_agents_id", table_name="agents")
    op.drop_table("agents")
