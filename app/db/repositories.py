from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.models import Extraction, Form, FormSubmission, Incident, Input, Job, Report, Template


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


def update_template(session: Session, template: Template) -> Template:
    session.add(template)
    session.commit()
    session.refresh(template)
    return template

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


# Reports
def create_report(session: Session, report: Report) -> Report:
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_report(session: Session, report_id: UUID) -> Report | None:
    return session.get(Report, report_id)


def update_report(session: Session, report: Report) -> Report:
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


# Incidents & Forms for Reporting
def get_incidents_in_date_range(session: Session, start_date: date, end_date: date) -> list[Incident]:
    statement = (
        select(Incident)
        .where(
            Incident.deleted_at.is_(None),
            or_(
                Incident.incident_date.between(start_date, end_date),
                and_(
                    Incident.incident_date.is_(None),
                    Incident.created_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
                    Incident.created_at <= datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc),
                ),
            ),
        )
        .order_by(Incident.incident_date.asc(), Incident.created_at.asc())
    )
    return list(session.exec(statement).all())


def get_forms_for_incident(session: Session, incident_id: UUID) -> list[Form]:
    statement = select(Form).where(Form.incident_id == incident_id)
    return list(session.exec(statement).all())


def get_forms_for_incidents(session: Session, incident_ids: list[UUID]) -> list[Form]:
    if not incident_ids:
        return []
    statement = select(Form).where(Form.incident_id.in_(incident_ids))
    return list(session.exec(statement).all())


def get_extractions_by_ids(session: Session, extract_ids: list[UUID]) -> list[Extraction]:
    if not extract_ids:
        return []
    statement = select(Extraction).where(Extraction.extract_id.in_(extract_ids))
    return list(session.exec(statement).all())

