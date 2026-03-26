from sqlmodel import create_engine, Session
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import StaticPool
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./fireform.db")

# Detect database dialect to apply appropriate configuration
db_url = make_url(DATABASE_URL)
is_sqlite = db_url.drivername.startswith('sqlite')

# Configure engine with dialect-specific settings
engine_kwargs = {
    "echo": False,  # Disable SQL logging in production for security
}

if is_sqlite:
    # SQLite-specific configuration
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 30,  # 30 second timeout
    }
    # Use StaticPool for SQLite to avoid connection issues
    engine_kwargs["poolclass"] = StaticPool
else:
    # PostgreSQL/MySQL configuration with connection pooling
    engine_kwargs["pool_size"] = 5  # Connection pool size
    engine_kwargs["max_overflow"] = 10  # Maximum overflow connections
    engine_kwargs["pool_timeout"] = 30  # Pool timeout
    engine_kwargs["pool_recycle"] = 3600  # Recycle connections every hour
    engine_kwargs["pool_pre_ping"] = True  # Verify connections before use

engine = create_engine(DATABASE_URL, **engine_kwargs)

def get_session():
    """
    Get database session with proper resource management.
    Uses context manager to ensure sessions are properly closed.
    """
    with Session(engine) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()