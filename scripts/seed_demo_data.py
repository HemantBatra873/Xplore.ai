#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import logger
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.document import DOCUMENT_STATUS_READY, Document, DocumentChunk
from app.models.task import Task
from app.models.user import User

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo123456"


def seed():
    logger.info("=== Seeding demo data ===")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        existing = db.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": DEMO_EMAIL},
        ).fetchone()

        if existing:
            logger.info(f"Demo user already exists (id={existing[0]}), skipping seed.")
            return

        demo_user = User(
            username="demo",
            email=DEMO_EMAIL,
            full_name="Demo User",
            hashed_password=get_password_hash(DEMO_PASSWORD),
            is_active=True,
        )
        db.add(demo_user)
        db.flush()
        logger.info(f"Created demo user (id={demo_user.id}, password={DEMO_PASSWORD})")

        from app.services.workspace_service import WorkspaceService

        workspace = WorkspaceService.create_personal_workspace(db, demo_user, commit=False)
        logger.info(f"Created personal workspace (id={workspace.id})")

        doc = Document(
            owner_id=demo_user.id,
            workspace_id=workspace.id,
            filename="welcome.txt",
            file_type="txt",
            content=(
                "Welcome to the Xplore.ai knowledge base.\n\n"
                "Xplore.ai uses retrieval-augmented generation for grounded answers.\n"
                "Uploaded documents are chunked, embedded, and stored in pgvector.\n"
                "Queries retrieve relevant passages before sending context to the LLM.\n\n"
                "The foundation also supports tool calling, conversation memory, SSE streaming, and encrypted provider keys.\n"
                "Try asking: 'What can I do with this knowledge base?'"
            ),
            status=DOCUMENT_STATUS_READY,
            chunks_count=1,
        )
        db.add(doc)
        db.flush()
        logger.info(f"Created demo document (id={doc.id})")

        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            content=doc.content,
            embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        )
        db.add(chunk)

        tasks_data = [
            {
                "title": "Learn how retrieval works",
                "description": "Read the project documentation to understand retrieval-augmented generation",
                "status": "completed",
            },
            {
                "title": "Configure an LLM API key",
                "description": "Add a provider key in your personal settings",
                "status": "pending",
            },
            {
                "title": "Try a tool call",
                "description": "Ask the assistant about the weather or create a task",
                "status": "pending",
            },
        ]
        for t in tasks_data:
            db.add(Task(owner_id=demo_user.id, workspace_id=workspace.id, **t))

        logger.info(f"Created {len(tasks_data)} demo tasks")

        db.commit()
        logger.info("=== Seed complete! ===")
        logger.info(f"Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")

    except Exception as e:
        db.rollback()
        logger.error(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
