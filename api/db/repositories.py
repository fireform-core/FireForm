from sqlmodel import Session, select
from api.db.models import Template, FormSubmission, FillJob

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

# Fill Jobs
def create_job(session: Session, job: FillJob) -> FillJob:
    session.add(job)
    session.commit()
    session.refresh(job)
    return job

def get_job(session: Session, job_id: str) -> FillJob | None:
    return session.get(FillJob, job_id)

def update_job(session: Session, job_id: str, **kwargs) -> FillJob | None:
    """
    Partially update a FillJob record. Accepts any subset of FillJob fields as
    keyword arguments. Returns the updated record, or None if not found.
    """
    job = session.get(FillJob, job_id)
    if not job:
        return None
    for key, value in kwargs.items():
        setattr(job, key, value)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job