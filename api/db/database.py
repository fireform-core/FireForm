import os

from sqlmodel import Session, create_engine

DATABASE_URL = "sqlite:///./fireform.db"
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() in {"1", "true", "yes", "on"}

engine = create_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    connect_args={"check_same_thread": False},
)

def get_session():
    with Session(engine) as session:
        yield session