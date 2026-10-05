from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import logger

# Database URL from settings
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy sync engine
try:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,  # Verify connections before use
        echo=False,  # Set True to log all SQL
    )

    # Session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database engine configured successfully.")
except Exception as e:
    logger.error(f"Failed to configure database engine: {e}")
    raise e
