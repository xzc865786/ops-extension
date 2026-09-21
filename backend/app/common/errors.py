from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str | None = None):
        super().__init__(status_code=status_code, detail={"detail": detail, "code": code} if code else detail)
        self.code = code


def bad_request(detail: str, code: str | None = None) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, detail, code)


def unauthorized(detail: str = "未登录", code: str = "UNAUTHORIZED") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, detail, code)


def forbidden(detail: str = "无权限", code: str = "FORBIDDEN") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, detail, code)


def not_found(detail: str = "资源不存在", code: str = "NOT_FOUND") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, detail, code)


def conflict(detail: str, code: str = "CONFLICT") -> AppError:
    return AppError(status.HTTP_409_CONFLICT, detail, code)
