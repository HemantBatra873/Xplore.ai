import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Test env flags (disable rate limiter, etc.)
os.environ["TESTING"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.db.base import Base
from app.main import app

DEFAULT_SQLITE_URL = "sqlite:///:memory:"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

USING_POSTGRES = DATABASE_URL.startswith("postgresql")

if USING_POSTGRES:
    engine = create_engine(DATABASE_URL)
else:
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 2. Override FastAPI dependencies
# Inject the test DB session when routes depend on get_db
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# 3. Pytest Fixtures
@pytest.fixture(scope="session")
def setup_database():
    """
    Create tables from SQLAlchemy models before tests; drop after.

    Prefer a dedicated test database when using Postgres. Do not point
    DATABASE_URL at an Alembic-managed development database — drop_all()
    removes application tables (and would leave a stale alembic_version).
    """
    if USING_POSTGRES:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if USING_POSTGRES:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
            conn.commit()


@pytest.fixture(scope="module")
def client(setup_database):
    """
    HTTP test client fixture.
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session(setup_database):
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
