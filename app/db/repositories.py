from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from app.models import FormSubmission, Input, Job, Template


# Templates
def create_template(session: Session, template: Template) -> Template:
    session.add(template)
    session.commit()
    session.refresh(template)
    return template

def get_template(session: Session, template_id: int) -> Template | None:
    return session.get(Template, template_id)


def list_templates(session: Session) -> list[Template]:
    statement = select(Template).order_by(Template.created_at.desc(), Template.id.desc())
    return list(session.exec(statement))

# Forms
def create_form(session: Session, form: FormSubmission) -> FormSubmission:
    session.add(form)
    session.commit()
    session.refresh(form)
    return form


def get_submissions(session: Session) -> list[tuple[FormSubmission, str | None]]:
    statement = (
        select(FormSubmission, Template.name)
        .join(Template, FormSubmission.template_id == Template.id, isouter=True)
        .order_by(FormSubmission.created_at.desc(), FormSubmission.id.desc())
    )
    return list(session.exec(statement).all())


def get_submissions_with_template(session: Session) -> list[tuple[FormSubmission, str | None]]:
    statement = select(FormSubmission, Template.name).join(
        Template, FormSubmission.template_id == Template.id, isouter=True
    )
    return list(session.exec(statement).all())


def get_submissions_before(session: Session, cutoff: datetime) -> list[FormSubmission]:
    statement = select(FormSubmission).where(FormSubmission.created_at < cutoff)
    return list(session.exec(statement))


# Jobs
def create_job(session: Session, job: Job) -> Job:
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def get_job_by_uuid(session: Session, job_uuid: str) -> Job | None:
    statement = select(Job).where(Job.job_id == job_uuid)
    return session.exec(statement).first()


def get_job_by_celery_id(session: Session, celery_task_id: str) -> Job | None:
    statement = select(Job).where(Job.celery_task_id == celery_task_id)
    return session.exec(statement).first()


def update_job(session: Session, job: Job) -> Job:
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def delete_template(session: Session, template: Template) -> None:
    session.delete(template)
    session.commit()


def get_submissions_by_template(session: Session, template_id: int) -> list[FormSubmission]:
    statement = select(FormSubmission).where(FormSubmission.template_id == template_id)
    return list(session.exec(statement))


def get_jobs_by_template(session: Session, template_id: int) -> list[Job]:
    statement = select(Job).where(Job.template_id == template_id)
    return list(session.exec(statement))


def get_form_submission(session: Session, submission_id: int) -> FormSubmission | None:
    return session.get(FormSubmission, submission_id)


def delete_form_submission(session: Session, submission: FormSubmission) -> None:
    session.delete(submission)
    session.commit()


# Inputs
def create_input(session: Session, input_obj: Input) -> Input:
    session.add(input_obj)
    session.commit()
    session.refresh(input_obj)
    return input_obj


def get_input(session: Session, input_id: UUID) -> Input | None:
    return session.get(Input, input_id)


def update_input(session: Session, input_obj: Input) -> Input:
    session.add(input_obj)
    session.commit()
    session.refresh(input_obj)
    return input_obj

