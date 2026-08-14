# benchmark/pipelines/pipeline.py
import time
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Template  # noqa: F401 — registers tables
from app.api.schemas.templates import TemplateCreate
from app.services.template import TemplateService
from app.services.form import FormService
from benchmark.pipelines.base import BasePipeline, PipelineExtractionOutput


# Shared in-memory SQLite engine for the benchmark run
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(_engine)


class Pipeline(BasePipeline):
    def run(self, narrative: str, template_schema: dict, pdf_path: str) -> PipelineExtractionOutput:
        with Session(_engine) as session:
            # 1. Seed a Template row from the JSON schema
            template = TemplateService().create_template(session, TemplateCreate(
                name=pdf_path,
                pdf_path=pdf_path,
                fields=template_schema,
            ))

            # 2. Run the LLM extraction
            t0 = time.perf_counter()
            submission = FormService().fill_and_persist(
                session=session,
                template=session.get(Template, template.id),
                transcript=narrative,
                input_id=None,   # no Input row needed for benchmark
            )
            latency = time.perf_counter() - t0

            # 3. Pull extracted fields out of the filled submission
            extracted = submission.output_pdf_path  # parse JSON fields here

            return PipelineExtractionOutput(
                extracted_fields=extracted,
                field_confidence={},
                latency_seconds=latency,
            )
