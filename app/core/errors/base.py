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
