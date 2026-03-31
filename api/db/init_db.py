from sqlmodel import SQLModel
from database import engine
import models

def init_db():
    SQLModel.metadata.create_all(engine)

if __name__ == "__main__":
    init_db()