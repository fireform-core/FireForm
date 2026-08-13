from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PipelineExtractionOutput:
    """Output structure for extraction pipelines."""
    extracted_fields: dict[str, any]
    field_confidence: dict[str, float]
    latency_seconds: float


class BasePipeline(ABC):
    """Base class for all extraction pipelines."""

    @abstractmethod
    def run(self, narrative: str, template_schema: dict) -> PipelineExtractionOutput: 
        pass