"""add_knowledge_bases_and_retrieval_indexes

Revision ID: e9f5a2b3c4d5
Revises: d8e4f1a2b3c4
Create Date: 2026-10-05 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9f5a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d8e4f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
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
        sa.UniqueConstraint("workspace_id", "name", name="uq_knowledge_bases_workspace_name"),
    )
    op.create_index("ix_knowledge_bases_id", "knowledge_bases", ["id"])
    op.create_index("ix_knowledge_bases_workspace_id", "knowledge_bases", ["workspace_id"])
    op.create_index("ix_knowledge_bases_created_by_id", "knowledge_bases", ["created_by_id"])

    op.add_column("documents", sa.Column("knowledge_base_id", sa.Integer(), nullable=True))
    op.create_index("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"])
    op.create_foreign_key(
        "fk_documents_knowledge_base_id",
        "documents",
        "knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        ondelete="CASCADE",
    )

    conn = op.get_bind()
    workspaces = conn.execute(sa.text("SELECT id, created_by_id FROM workspaces ORDER BY id")).fetchall()
    for workspace_id, created_by_id in workspaces:
        result = conn.execute(
            sa.text(
                """
                INSERT INTO knowledge_bases
                    (workspace_id, name, description, created_by_id, created_at, updated_at)
                VALUES
                    (:workspace_id, 'General', 'Default knowledge base for this workspace',
                     :created_by_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """
            ),
            {"workspace_id": workspace_id, "created_by_id": created_by_id},
        )
        kb_id = result.scalar_one()
        conn.execute(
            sa.text(
                """
                UPDATE documents
                SET knowledge_base_id = :kb_id
                WHERE workspace_id = :workspace_id AND knowledge_base_id IS NULL
                """
            ),
            {"kb_id": kb_id, "workspace_id": workspace_id},
        )

    # Orphan documents without workspace: attach to first available KB if any remain
    orphans = conn.execute(
        sa.text(
            """
            SELECT d.id, d.owner_id
            FROM documents d
            WHERE d.knowledge_base_id IS NULL
            """
        )
    ).fetchall()
    for doc_id, owner_id in orphans:
        kb_id = None
        if owner_id is not None:
            kb_id = conn.execute(
                sa.text(
                    """
                    SELECT kb.id
                    FROM knowledge_bases kb
                    JOIN users u ON u.default_workspace_id = kb.workspace_id
                    WHERE u.id = :owner_id
                    ORDER BY kb.id
                    LIMIT 1
                    """
                ),
                {"owner_id": owner_id},
            ).scalar_one_or_none()
        if kb_id is None:
            kb_id = conn.execute(
                sa.text("SELECT id FROM knowledge_bases ORDER BY id LIMIT 1")
            ).scalar_one_or_none()
        if kb_id is not None:
            conn.execute(
                sa.text(
                    """
                    UPDATE documents
                    SET knowledge_base_id = :kb_id,
                        workspace_id = COALESCE(
                            workspace_id,
                            (SELECT workspace_id FROM knowledge_bases WHERE id = :kb_id)
                        )
                    WHERE id = :doc_id
                    """
                ),
                {"kb_id": kb_id, "doc_id": doc_id},
            )

    remaining_null = conn.execute(
        sa.text("SELECT COUNT(*) FROM documents WHERE knowledge_base_id IS NULL")
    ).scalar()
    if remaining_null == 0:
        op.alter_column("documents", "knowledge_base_id", existing_type=sa.Integer(), nullable=False)

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id "
        "ON document_chunks (document_id)"
    )

    # Full-text search support for hybrid retrieval (PostgreSQL only)
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv "
        "ON document_chunks USING GIN (content_tsv)"
    )

    # Approximate nearest neighbor index for vector search
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_document_id")

    op.alter_column("documents", "knowledge_base_id", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint("fk_documents_knowledge_base_id", "documents", type_="foreignkey")
    op.drop_index("ix_documents_knowledge_base_id", table_name="documents")
    op.drop_column("documents", "knowledge_base_id")

    op.drop_index("ix_knowledge_bases_created_by_id", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_workspace_id", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
