import os
from sqlmodel import create_engine, Session

# Define path to the database in the user's home directory
HOME_DIR = os.path.expanduser("~")
APP_DIR = os.path.join(HOME_DIR, ".fireform")
os.makedirs(APP_DIR, exist_ok=True)
DB_PATH = os.path.join(APP_DIR, "fireform.db")

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"check_same_thread": False},
)

def get_session():
    with Session(engine) as session:
        yield session