from fastapi.responses import JSONResponse


def error_response(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse:
    """按 04 号文档统一错误体返回 JSON。"""
    return JSONResponse(
        status_code=status,
        content={"error_code": code, "message": message, "detail": detail},
    )
