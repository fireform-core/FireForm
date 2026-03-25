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


def get_templates_by_ids(session: Session, template_ids: list[int]) -> list[Template]:
    if not template_ids:
        return []
    statement = select(Template).where(Template.id.in_(template_ids))
    return list(session.exec(statement).all())

# Forms
def create_form(session: Session, form: FormSubmission) -> FormSubmission:
    session.add(form)
    session.commit()
    session.refresh(form)
    return form