from sqlmodel import Session, select
from api.db.models import Template, FormSubmission, FillJob, BatchSubmission

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
    job = session.get(FillJob, job_id)
    if not job:
        return None
    for key, value in kwargs.items():
        setattr(job, key, value)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job

# Batch Submissions
def create_batch(session: Session, batch: BatchSubmission) -> BatchSubmission:
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch

def get_batch(session: Session, batch_id: str) -> BatchSubmission | None:
    return session.get(BatchSubmission, batch_id)