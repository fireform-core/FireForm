from benchmark.pipelines.base import BasePipeline, PipelineExtractionOutput


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
        return PipelineExtractionOutput(
            extracted_fields={},
            field_confidence={},
            latency_seconds=0.0
        )
