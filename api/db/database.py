import os
from sqlmodel import create_engine, Session

DATABASE_URL = "sqlite:///./fireform.db"

# SQL echo is opt-in via environment variable — defaults to off in production
# to prevent every SQL query from being printed to stdout.
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"

engine = create_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    connect_args={"check_same_thread": False},
)


def get_session():
    with Session(engine) as session:
        yield session