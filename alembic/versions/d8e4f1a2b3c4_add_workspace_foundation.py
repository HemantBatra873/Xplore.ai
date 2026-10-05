"""add_workspace_foundation

Revision ID: d8e4f1a2b3c4
Revises: b35f62ae79bf
Create Date: 2026-10-05 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e4f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "b35f62ae79bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_workspaces_id", "workspaces", ["id"])
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)
    op.create_index("ix_workspaces_created_by_id", "workspaces", ["created_by_id"])

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership_workspace_user"),
    )
    op.create_index("ix_workspace_memberships_id", "workspace_memberships", ["id"])
    op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])
    op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])

    op.add_column("users", sa.Column("default_workspace_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_default_workspace_id",
        "users",
        "workspaces",
        ["default_workspace_id"],
        ["id"],
    )

    op.add_column("tasks", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.create_index("ix_tasks_workspace_id", "tasks", ["workspace_id"])
    op.create_foreign_key("fk_tasks_workspace_id", "tasks", "workspaces", ["workspace_id"], ["id"])

    op.add_column("documents", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_foreign_key(
        "fk_documents_workspace_id", "documents", "workspaces", ["workspace_id"], ["id"]
    )

    op.add_column("llm_call_logs", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.create_index("ix_llm_call_logs_workspace_id", "llm_call_logs", ["workspace_id"])
    op.create_foreign_key(
        "fk_llm_call_logs_workspace_id",
        "llm_call_logs",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )

    conn = op.get_bind()

    users = conn.execute(sa.text("SELECT id, username FROM users ORDER BY id")).fetchall()
    for user_id, username in users:
        slug = f"user-{user_id}-{(username or 'user').lower()}"
        slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in slug)
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug.strip("-") or f"user-{user_id}"

        result = conn.execute(
            sa.text(
                """
                INSERT INTO workspaces (name, slug, created_by_id, is_active, created_at, updated_at)
                VALUES (:name, :slug, :created_by_id, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """
            ),
            {
                "name": f"{username}'s Workspace",
                "slug": slug,
                "created_by_id": user_id,
            },
        )
        workspace_id = result.scalar_one()

        conn.execute(
            sa.text(
                """
                INSERT INTO workspace_memberships
                    (workspace_id, user_id, role, created_at, updated_at)
                VALUES
                    (:workspace_id, :user_id, 'owner', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        conn.execute(
            sa.text("UPDATE users SET default_workspace_id = :workspace_id WHERE id = :user_id"),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "UPDATE tasks SET workspace_id = :workspace_id WHERE owner_id = :user_id AND workspace_id IS NULL"
            ),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "UPDATE documents SET workspace_id = :workspace_id WHERE owner_id = :user_id AND workspace_id IS NULL"
            ),
            {"workspace_id": workspace_id, "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "UPDATE llm_call_logs SET workspace_id = :workspace_id WHERE user_id = :user_id AND workspace_id IS NULL"
            ),
            {"workspace_id": workspace_id, "user_id": user_id},
        )

    # Tasks always belong to a workspace after backfill for owned rows.
    # If any orphan tasks remain, attach them to the creator's default workspace when possible.
    orphan_tasks = conn.execute(
        sa.text("SELECT id, owner_id FROM tasks WHERE workspace_id IS NULL")
    ).fetchall()
    for task_id, owner_id in orphan_tasks:
        default_ws = conn.execute(
            sa.text("SELECT default_workspace_id FROM users WHERE id = :owner_id"),
            {"owner_id": owner_id},
        ).scalar_one_or_none()
        if default_ws:
            conn.execute(
                sa.text("UPDATE tasks SET workspace_id = :workspace_id WHERE id = :task_id"),
                {"workspace_id": default_ws, "task_id": task_id},
            )

    op.alter_column("tasks", "workspace_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_llm_call_logs_workspace_id", "llm_call_logs", type_="foreignkey")
    op.drop_index("ix_llm_call_logs_workspace_id", table_name="llm_call_logs")
    op.drop_column("llm_call_logs", "workspace_id")

    op.drop_constraint("fk_documents_workspace_id", "documents", type_="foreignkey")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_column("documents", "workspace_id")

    op.drop_constraint("fk_tasks_workspace_id", "tasks", type_="foreignkey")
    op.drop_index("ix_tasks_workspace_id", table_name="tasks")
    op.drop_column("tasks", "workspace_id")

    op.drop_constraint("fk_users_default_workspace_id", "users", type_="foreignkey")
    op.drop_column("users", "default_workspace_id")

    op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_id", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")

    op.drop_index("ix_workspaces_created_by_id", table_name="workspaces")
    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_index("ix_workspaces_id", table_name="workspaces")
    op.drop_table("workspaces")
