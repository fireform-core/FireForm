from benchmark.pipelines.base import BasePipeline, PipelineExtractionOutput
from app.services.input import InputService
from app.api.routes.input import submit_text_input
from app.api.schemas.input import TextInputRequest, TextInputResponse
from app.api.routes.extraction import create_extraction, get_extraction_result
from app.api.schemas.extraction import ExtractionJobResponse
import time

class Pipeline(BasePipeline):
    def run(self, narrative: str, template_schema: dict, pdf_path: str) -> PipelineExtractionOutput:
        '''
        You guys should here implement the whole pipeline implementation depending on approach B or C.

        Expected behavior:
        - Create and fill templates, then wait for jobs to complete.
        - Return extracted fields, confidence scores, and latency.

        Example of a single step:
        >>> template_id = create_template(...)
        >>> form_response = fill_form(...)
        >>> result = wait_for_job_completion(form_response.job_id)
        >>> extracted = result.extracted_fields
        >>> confidence = result.field_confidence
        >>> latency = result.latency_seconds
        '''

        # 1. Input Layer
        text_input_response = submit_text_input(TextInputRequest(narrative=narrative))
        input_id = text_input_response.input_id

        # 2. Extraction Layer
        job_response = create_extraction(input_id)

        extract_id = job_response.extract_id
        
        # 3. Polling loop (wait 5 seconds between checks until condition is met)
        extraction_starting_time = time.time()
        while get_extraction_result(extract_id).status == "processing":
            time.sleep(5)
        extraction_ending_time = time.time()
        extraction_latency = extraction_ending_time - extraction_starting_time


        incident_contract = get_extraction_result(extract_id).partial_result
        



        return PipelineExtractionOutput(
            extracted_fields={},
            field_confidence={},
            latency_seconds=0.0
        )
