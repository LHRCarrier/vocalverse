"""统一响应 envelope（docs/06 第 7 章）：{code, message, data}。

成功 code=0；业务错误码表见 docs/api/error-codes.md。
"""

from typing import Any

from pydantic import BaseModel


class Envelope[T](BaseModel):
    code: int = 0
    message: str = "ok"
    data: T | None = None


def ok(data: Any = None, message: str = "ok") -> Envelope:
    return Envelope(code=0, message=message, data=data)


class BizError(Exception):
    """业务异常：HTTP 状态码与业务 code 并存。"""

    def __init__(self, http_status: int, code: int, message: str):
        self.http_status = http_status
        self.code = code
        self.message = message
        super().__init__(message)
