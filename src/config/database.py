"""Database configuration and connection management."""

import os
from typing import Optional
from src.config import service_logger
from src.models.database import db_manager


def get_database_url() -> str:
    """Get database URL from environment variables."""
    # Try different environment variable names for flexibility
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DB_URL")

    if not db_url:
        # Default to SQLite for development if no PostgreSQL URL provided
        service_logger.warning("No DATABASE_URL found, using SQLite for development")
        db_path = os.path.join(os.getcwd(), "data", "reports.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db_url = f"sqlite:///{db_path}"

    return db_url


def init_database() -> None:
    """Initialize database connection and create tables."""
    try:
        database_url = get_database_url()
        service_logger.info("Initializing database connection", url=database_url.split('@')[-1] if '@' in database_url else database_url)

        db_manager.connect(database_url)
        db_manager.create_tables()

        service_logger.info("Database initialized successfully")
    except Exception as e:
        service_logger.error("Failed to initialize database", error=str(e))
        raise


def get_db_session():
    """Get a database session for use in services."""
    return db_manager.get_session()


def close_database() -> None:
    """Close database connections."""
    if db_manager:
        db_manager.close()
        service_logger.info("Database connections closed")
