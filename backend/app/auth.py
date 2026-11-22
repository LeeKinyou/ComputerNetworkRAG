"""轻量登录：`.env` 配置账号 + HMAC 签名 cookie，不引入新依赖。

设计取舍：
- 演示环境只有少量固定身份，账号表放 `.env` 比建 users 表省一次迁移；
- 角色只有两种：`teacher`（可看全班、可切单个学生）与 `student`（只能看自己）；
- 密码只做常量时间比较，不做哈希存储：口令来自环境变量，不进仓库也不落库。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response

from app.config import settings

COOKIE_NAME = "cnrag_session"
TOKEN_TTL_SECONDS = 8 * 60 * 60
DEFAULT_USER_KEY = "demo_user"
ROLES = {"teacher", "student"}


@dataclass(frozen=True)
class Account:
    username: str
    role: str
    user_key: str

    def as_dict(self) -> dict[str, str]:
        return {"username": self.username, "role": self.role, "user_key": self.user_key}


def parse_accounts(raw: str) -> dict[str, tuple[str, str]]:
    """`username:role:password`，多条用 `;` 或换行分隔。返回 username -> (role, password)。"""
    accounts: dict[str, tuple[str, str]] = {}
    for chunk in raw.replace("\n", ";").split(";"):
        item = chunk.strip()
        if not item:
            continue
        parts = item.split(":", 2)
        if len(parts) != 3:
            continue
        username, role, password = (part.strip() for part in parts)
        if not username or not password or role not in ROLES:
            continue
        accounts[username] = (role, password)
    return accounts


def accounts() -> dict[str, tuple[str, str]]:
    return parse_accounts(settings.auth_accounts)


def authenticate(username: str, password: str) -> Account | None:
    entry = accounts().get(username.strip())
    if not entry:
        return None
    role, expected = entry
    if not hmac.compare_digest(password, expected):
        return None
    return Account(username=username.strip(), role=role, user_key=username.strip())


def _sign(payload: str) -> str:
    digest = hmac.new(settings.app_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_token(account: Account) -> str:
    payload = {
        "sub": account.username,
        "role": account.role,
        "key": account.user_key,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    body = body.rstrip("=")
    return f"{body}.{_sign(body)}"


def read_token(token: str | None) -> Account | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    username = str(payload.get("sub") or "")
    role = str(payload.get("role") or "")
    if not username or role not in ROLES:
        return None
    return Account(username=username, role=role, user_key=str(payload.get("key") or username))


def current_account(request: Request) -> Account | None:
    """从 cookie 或 Bearer 头解析身份；中间件会把结果放到 request.state。"""
    cached = getattr(request.state, "account", None)
    if isinstance(cached, Account):
        return cached
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    account = read_token(token)
    request.state.account = account
    return account


def set_session_cookie(response: Response, account: Account) -> None:
    response.set_cookie(
        COOKIE_NAME,
        issue_token(account),
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def scoped_user_key(request: Request, user_key: str | None = None) -> str:
    """把请求里的 user_key 收口到当前身份：学生只能操作自己，教师可按需指定。

    作为 FastAPI 依赖使用：`user_key: str = Depends(scoped_user_key)`，
    依赖里的 `user_key` 会自动读取同名 query 参数。
    """
    account = current_account(request)
    if account is None:
        # AUTH_ENABLED=false 的本地演示：保持原有单用户行为
        return user_key or DEFAULT_USER_KEY
    if account.role == "teacher":
        return user_key or account.user_key
    if user_key and user_key != account.user_key:
        raise fail(403, "FORBIDDEN", "只能访问自己的数据")
    return account.user_key


def ensure_owner(account: Account | None, user_key: str | None) -> str:
    """校验 body 里的 user_key（创建会话 / 发起运行 / 提交作答）。"""
    if account is None:
        return user_key or DEFAULT_USER_KEY
    if account.role == "teacher":
        return user_key or account.user_key
    if user_key and user_key != account.user_key:
        raise fail(403, "FORBIDDEN", "只能以自己的身份提交")
    return account.user_key


def require_teacher(account: Account | None) -> None:
    if account is not None and account.role != "teacher":
        raise fail(403, "FORBIDDEN", "该页面仅教师可访问")
