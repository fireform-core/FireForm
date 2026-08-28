from app.services.approach_d import ApproachD
from benchmark.pipelines.base import BasePipeline, PipelineExtractionOutput
import time

class Pipeline(BasePipeline):
    def run(self, narrative: str, target_json: str, pdf_path: str, output_pdf_path: str) -> PipelineExtractionOutput:
        start_time = time.time()
        extracted_json = ApproachD.fill_form(narrative, target_json, pdf_path, output_pdf_path)
        latency = time.time() - start_time

        return PipelineExtractionOutput(
            extracted_fields=extracted_json,
            field_confidence={},
            latency_seconds=latency
        )
