class AppError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationFailed(AppError):
    status_code = 400


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class UpstreamFailure(AppError):
    status_code = 502
