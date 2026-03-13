from sqlmodel import Session, select
from api.db.models import Template, FormSubmission

# Templates
def create_template(session: Session, template: Template) -> Template:
    session.add(template)
    session.commit()
    session.refresh(template)
    return template

def get_template(session: Session, template_id: int) -> Template | None:
    return session.get(Template, template_id)

# Forms
def create_form(session: Session, form: FormSubmission) -> FormSubmission:
    session.add(form)
    session.commit()
    session.refresh(form)
    return form

def get_all_templates(session: Session, limit: int = 100, offset: int = 0) -> list[Template]:
    return session.exec(select(Template).offset(offset).limit(limit)).all()

def get_form(session: Session, submission_id: int) -> FormSubmission | None:
    return session.get(FormSubmission, submission_id)