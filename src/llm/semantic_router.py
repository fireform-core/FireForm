import asyncio
import json
import logging
from typing import Dict, Any

from src.schemas import (
    IncidentReport,
    SpatialData,
    MedicalData,
    OperationalData,
    IncidentType
)

logger = logging.getLogger("fireform_audit")

class MockAsyncLLMClient:
    """Simulates an asynchronous Ollama client for local local SLM inference."""
    async def extract_schema(self, transcript: str, schema_cls: Any) -> Any:
        # Simulate network or local inference latency
        await asyncio.sleep(0.5)

        # Mocking the JSON response based on the schema requested
        if schema_cls == SpatialData:
            mock_data = {
                "address": "123 Main St, Springfield",
                "coordinates": [39.7817, -89.6501]
            }
        elif schema_cls == MedicalData:
            mock_data = {
                "injuries": True,
                "severity": "Minor burns, handled on site"
            }
        elif schema_cls == OperationalData:
            mock_data = {
                "units_responding": ["Engine 51", "Ambulance 61"],
                "incident_type": "FIRE"
            }
        else:
            raise ValueError(f"Unknown schema class: {schema_cls}")

        # Validate and return the Pydantic model directly
        return schema_cls.model_validate(mock_data)

class SemanticRouter:
    """
    Pareto-Optimal Semantic Router.
    Decomposes the master extraction requirement into domain-specific Pydantic sub-schemas
    to prevent SLM Attention Dilution and achieves O(1) concurrent latency.
    """
    def __init__(self, llm_client=None):
        self.llm_client = llm_client or MockAsyncLLMClient()

    async def pareto_extraction(self, transcript: str) -> IncidentReport:
        """
        Uses asyncio.gather to concurrently extract SpatialData, MedicalData, and OperationalData.
        """
        logger.info(f"Starting O(1) concurrent pareto extraction for transcript length: {len(transcript)}")
        
        # Fire concurrent requests for each focused domain chunk
        spatial_task = self.llm_client.extract_schema(transcript, SpatialData)
        medical_task = self.llm_client.extract_schema(transcript, MedicalData)
        operational_task = self.llm_client.extract_schema(transcript, OperationalData)
        
        # Wait for all the chunks to finish simultaneously
        spatial_res, medical_res, operational_res = await asyncio.gather(
            spatial_task, medical_task, operational_task
        )
        
        logger.info("Successfully extracted all schema chunks concurrently.")
        
        # Re-aggregate into the standardized master report
        report_data = {
            "narrative": transcript,
            "spatial": spatial_res,
            "medical": medical_res,
            "operational": operational_res,
            "confidence_scores": []
        }
        
        return IncidentReport(**report_data)

async def test_router():
    """Simple internal test to verify routing."""
    router = SemanticRouter()
    report = await router.pareto_extraction("Fire at 123 Main St, Springfield. Engine 51 and Ambulance 61 responded. One minor burn.")
    print(report.model_dump_json(indent=2))

if __name__ == "__main__":
    asyncio.run(test_router())
