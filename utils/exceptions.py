# utils/exceptions.py

class ServiceError(Exception):
    status_code = 400

    def __init__(
        self,
        code="SERVICE_ERROR",
        message="Service error",
        details=None,
        status_code=None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}

        if status_code is not None:
            self.status_code = status_code

        super().__init__(message)


class ValidationError(ServiceError):
    status_code = 422

    def __init__(self, message, details=None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details=details,
            status_code=422,
        )


class UnauthorizedError(ServiceError):
    status_code = 401

    def __init__(self, message="Authentication required.", details=None):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            details=details,
            status_code=401,
        )


class ForbiddenError(ServiceError):
    status_code = 403

    def __init__(
        self,
        message="Administrator privileges required.",
        details=None,
    ):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            details=details,
            status_code=403,
        )


class NotFoundError(ServiceError):
    status_code = 404

    def __init__(self, message, details=None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            details=details,
            status_code=404,
        )


class ConflictError(ServiceError):
    status_code = 409

    def __init__(self, message, details=None):
        super().__init__(
            code="CONFLICT",
            message=message,
            details=details,
            status_code=409,
        )