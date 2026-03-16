class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class LLMUnavailableError(AppError):
    """
    Raised when the LLM backend (Ollama) is unreachable or misconfigured.
    """

    def __init__(self, detail: str):
        super().__init__(message=detail, status_code=503)