def _default_error_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        404: "NOT_FOUND",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "ERROR")


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str | None = None,
        detail: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or _default_error_code(status_code)
        self.detail = detail


class ValidationAppError(AppError):
    """A 422 raised by a service with field-level issues attached.

    Request-shape problems are caught by FastAPI and rendered from
    RequestValidationError. This is for the ones only the service can see, such
    as a correction whose merged document no longer matches the contract, and
    it renders the same validation_errors list so clients read one shape.
    """

    def __init__(
        self,
        message: str,
        validation_errors: list[dict] | None = None,
        error_code: str = "VALIDATION_ERROR",
        detail: dict | None = None,
    ):
        super().__init__(message, status_code=422, error_code=error_code, detail=detail)
        self.validation_errors = validation_errors or []
