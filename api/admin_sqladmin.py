import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from markupsafe import escape
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlmodel import Session, select

from api.db.database import engine
from api.db.models import FormSubmission, Template
from src.controller import Controller


class FireFormAuth(AuthenticationBackend):
    def __init__(self, secret_key: str):
        super().__init__(secret_key=secret_key)
        self.admin_username = os.getenv("FIREFORM_ADMIN_USER", "admin")
        self.admin_password = os.getenv("FIREFORM_ADMIN_PASSWORD", "admin")

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        if username == self.admin_username and password == self.admin_password:
            request.session.update({"token": "fireform-admin-authenticated"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("token"))


class TemplateAdmin(ModelView, model=Template):
    name = "Template"
    name_plural = "Templates"
    icon = "fa-solid fa-file-lines"

    column_list = [Template.id, Template.name, Template.pdf_path, Template.created_at]
    column_searchable_list = [Template.name, Template.pdf_path]
    column_sortable_list = [Template.id, Template.created_at]


class SubmissionAdmin(ModelView, model=FormSubmission):
    name = "Submission"
    name_plural = "Submissions"
    icon = "fa-solid fa-file-pdf"

    column_list = [
        FormSubmission.id,
        FormSubmission.template_id,
        FormSubmission.output_pdf_path,
        FormSubmission.created_at,
    ]
    column_searchable_list = [FormSubmission.output_pdf_path]
    column_sortable_list = [FormSubmission.id, FormSubmission.created_at]


class SimulationView(BaseView):
    name = "Simulation"
    icon = "fa-solid fa-flask"

    @expose("/simulation", methods=["GET", "POST"])
    async def simulation(self, request: Request):
        message = ""
        message_class = ""
        input_text = ""
        selected_template_id = ""
        process_log = ""

        with Session(engine) as session:
            templates = session.exec(select(Template).order_by(Template.created_at.desc())).all()

        if request.method == "POST":
            form = await request.form()
            template_id_raw = (form.get("template_id") or "").strip()
            input_text = (form.get("input_text") or "").strip()
            selected_template_id = template_id_raw

            if not template_id_raw or not input_text:
                message = "Template and input text are required."
                message_class = "err"
            else:
                try:
                    template_id = int(template_id_raw)
                    with Session(engine) as session:
                        selected = session.get(Template, template_id)
                        if not selected:
                            message = "Template not found."
                            message_class = "err"
                        else:
                            controller = Controller()
                            log_buffer = StringIO()
                            with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
                                output_path = controller.fill_form(
                                    user_input=input_text,
                                    fields=selected.fields,
                                    pdf_form_path=selected.pdf_path,
                                )
                            process_log = log_buffer.getvalue().strip()

                            if not output_path:
                                message = "Simulation failed to generate PDF output."
                                message_class = "err"
                            else:
                                submission = FormSubmission(
                                    template_id=selected.id,
                                    input_text=input_text,
                                    output_pdf_path=output_path,
                                )
                                session.add(submission)
                                session.commit()
                                session.refresh(submission)
                                message = (
                                    f"Simulation completed. Submission #{submission.id} created. "
                                    f"Open it in PDF Reader."
                                )
                                message_class = "ok"
                except ValueError:
                    message = "Invalid template ID."
                    message_class = "err"
                except Exception as exc:
                    if not process_log:
                        process_log = str(exc)
                    message = f"Simulation error: {escape(str(exc))}"
                    message_class = "err"

        context: dict[str, Any] = {
            "title": "Simulation",
            "subtitle": "Generate filled PDFs from one narrative input.",
            "templates": templates,
            "message": message,
            "message_class": message_class,
            "input_text": input_text,
            "selected_template_id": selected_template_id,
            "process_log": process_log,
        }
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/custom/simulation.html",
            context,
        )


class PdfReaderView(BaseView):
    name = "PDF Reader"
    icon = "fa-solid fa-book-open"

    @expose("/pdf-browser", methods=["GET"])
    async def browser(self, request: Request):
        with Session(engine) as session:
            submissions = session.exec(
                select(FormSubmission).order_by(FormSubmission.created_at.desc())
            ).all()

        context: dict[str, Any] = {
            "title": "PDF Reader",
            "subtitle": "Browse and open generated form outputs.",
            "submissions": submissions,
        }
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/custom/pdf_browser.html",
            context,
        )

    @expose("/pdf-viewer/{submission_id}", methods=["GET"])
    async def viewer(self, request: Request):
        submission_id_raw = request.path_params.get("submission_id")
        try:
            submission_id = int(submission_id_raw)
        except (TypeError, ValueError):
            return RedirectResponse(url="/admin/pdf-browser", status_code=303)

        with Session(engine) as session:
            submission = session.get(FormSubmission, submission_id)

        if not submission:
            return RedirectResponse(url="/admin/pdf-browser", status_code=303)

        context: dict[str, Any] = {
            "title": "PDF Viewer",
            "subtitle": "Embedded preview of generated form output.",
            "submission": submission,
            "pdf_url": f"/admin/pdf-file/{submission_id}",
        }
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/custom/pdf_viewer.html",
            context,
        )

    @expose("/pdf-file/{submission_id}", methods=["GET"])
    async def pdf_file(self, request: Request):
        submission_id_raw = request.path_params.get("submission_id")
        try:
            submission_id = int(submission_id_raw)
        except (TypeError, ValueError):
            return HTMLResponse("Invalid submission id", status_code=400)

        with Session(engine) as session:
            submission = session.get(FormSubmission, submission_id)

        if not submission:
            return HTMLResponse("Submission not found", status_code=404)

        base_dir = Path(__file__).resolve().parents[1]
        output_path = Path(submission.output_pdf_path)
        if not output_path.is_absolute():
            output_path = (base_dir / output_path).resolve()
        else:
            output_path = output_path.resolve()

        if not str(output_path).startswith(str(base_dir.resolve())):
            return HTMLResponse("Invalid file path", status_code=400)
        if not output_path.exists() or not output_path.is_file():
            return HTMLResponse("PDF file not found", status_code=404)

        return FileResponse(str(output_path), media_type="application/pdf")


def setup_admin(app):
    auth_backend = FireFormAuth(secret_key="fireform-sqladmin-auth-key")
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=auth_backend,
        title="FireForm",
        templates_dir="api/templates",
    )
    admin.add_view(TemplateAdmin)
    admin.add_view(SubmissionAdmin)
    admin.add_view(SimulationView)
    admin.add_view(PdfReaderView)
