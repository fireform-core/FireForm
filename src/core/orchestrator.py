import asyncio
import logging

logger = logging.getLogger(__name__)

class VRAMOrchestrator:
    """
    Orchestrates access to VRAM-intensive models (Whisper, Ollama) 
    to prevent OOM on hardware-constrained devices.
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VRAMOrchestrator, cls).__new__(cls)
        return cls._instance

    @property
    def lock(self):
        return self._lock

orchestrator = VRAMOrchestrator()
