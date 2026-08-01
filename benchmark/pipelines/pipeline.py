import time
from benchmark.pipelines.base import BasePipeline, PipelineExtractionOutput

from app.api.routes import create_template, wait_for_job_completion, fill_form
from app.core.config import OLLAMA_MODEL

class Pipeline(BasePipeline):
    def run(self, narrative: str, template_schema: dict) -> PipelineExtractionOutput:
        '''
        # Create a unique template ID
        template_id = f"benchmark_template_{int(time.time())}"
        
        # Create the template (this is synchronous)
        template_response = create_template(
            name=template_id,
            description="Benchmark template",
            pdf_path="/tmp/empty.pdf",
            fields=template_schema
        )
        
        if not template_response:
            raise RuntimeError("Failed to create template")
            
        # Submit the form fill (this is asynchronous)
        form_response = fill_form(
            template_id=template_response.id,
            input_text=narrative,
            model=OLLAMA_MODEL,
            api_key="benchmark-key"
        )
        
        if not form_response:
            raise RuntimeError("Failed to submit form fill")
            
        # Wait for the job to complete (synchronous waiting)
        job_id = form_response.job_id
        result = wait_for_job_completion(job_id)
        
        if not result:
            raise RuntimeError("Job did not complete")
            
        # Extract the output
        extracted_fields = result.extracted_fields
        field_confidence = result.field_confidence
        latency_seconds = result.latency_seconds
        
        return PipelineExtractionOutput(
            extracted_fields=extracted_fields,
            field_confidence=field_confidence,
            latency_seconds=latency_seconds
        )
        '''
        pass
