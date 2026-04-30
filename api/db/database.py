import os

from sqlmodel import create_engine, Session

DATABASE_URL = "sqlite:///./fireform.db"

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    connect_args={"check_same_thread": False},
)

def get_session():
    with Session(engine) as session:
        yield session