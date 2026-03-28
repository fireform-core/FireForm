class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class ValidationError(AppError):
    """Raised when input validation fails."""

    def __init__(self, message: str, errors: list[str] = None):
        super().__init__(message, status_code=422)
        self.errors = errors or []