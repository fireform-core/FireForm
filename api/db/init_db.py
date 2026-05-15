import json
import datetime
from sqlmodel import SQLModel, Session, select
from api.db.database import engine
from api.db import models
from api.db.models import Template

def seed_db():
    with Session(engine) as session:
        # Check if we already have templates
        statement = select(Template)
        try:
            results = session.exec(statement).first()
        except Exception:
            # Table might not exist yet if called at a weird time
            results = None
        
        if not results:
            print("Seeding database with default template...")
            fields = {
                "Employee's name": "string",
                "Employee's job title": "string",
                "Employee's department supervisor": "string",
                "Employee's phone number": "string",
                "Employee's email": "string",
                "Signature": "string",
                "Date": "string"
            }
            
            # Using ID 2 as agreed to avoid any ID 1 corruption
            default_template = Template(
                id=2,
                name="Manual Test Template",
                fields=fields,
                pdf_path="src/inputs/file_template_manual.pdf",
                created_at=datetime.datetime.now()
            )
            session.add(default_template)
            session.commit()
            print("Database seeded successfully.")

def init_db():
    SQLModel.metadata.create_all(engine)
    seed_db()

if __name__ == "__main__":
    init_db()