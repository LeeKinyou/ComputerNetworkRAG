"""把 LightRAG 官方控制台（WebUI + 文档/图谱/查询 API）挂进本项目进程。

图谱页的自研可视化在交互与信息密度上不如 LightRAG 自带的 WebUI（cosmos.gl 3D 图谱、
文档流水线、实体/关系编辑），因此复用同一个 LightRAG 单例再挂一套控制台，
不再起第二个进程、也不复制存储。

安全边界：控制台带 delete_document / clear_cache / 实体编辑等写接口。
未配置 AUTH_ACCOUNTS 与 LIGHTRAG_API_KEY 时这些接口完全开放，所以
LIGHTRAG_CONSOLE 默认关闭；公网机器上开启前必须先配其中一项凭据。
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

logger = logging.getLogger(__name__)

UI_PATH = "/webui"
API_PATH = "/lightrag-api"
RUNTIME_CONFIG_PLACEHOLDER = b"<!-- __LIGHTRAG_RUNTIME_CONFIG__ -->"

_args = None

# 挂在宿主 app.state 上的键。不能放模块全局：uvicorn 以 "main:app" 导入字符串
# 启动时 main 模块会被导入两次，第二个实例（真正对外服务的那个）会因为
# 全局标记已置位而跳过挂载，结果是全部路由 404。
STATE_KEY = "lightrag_console"


class ConsoleState:
    __slots__ = ("app", "wired")

    def __init__(self, app: FastAPI):
        self.app = app
        self.wired = False


def enabled() -> bool:
    return bool(get_settings().LIGHTRAG_CONSOLE)


def _state(host) -> ConsoleState | None:
    return getattr(host.state, STATE_KEY, None)


def public_info(host) -> dict:
    """给 /api/health 用：前端图谱页只在控制台真正可用时才显示入口。"""
    state = _state(host)
    return {
        "enabled": state is not None,
        "wired": bool(state and state.wired),
        "url": f"{UI_PATH}/" if state is not None else None,
    }


def _init_lightrag_config():
    """初始化 LightRAG 自己的 argparse 全局配置。

    lightrag.api 模块一被 import 就会通过 _GlobalArgsProxy 触发 parse_args()，
    而它用的是 sys.argv —— 以 `uvicorn main:app --host ...` 启动时会把 uvicorn
    的参数当成 LightRAG 的参数并 parser.error() 退出。所以必须在 import 之前、
    用清空过的 argv 抢先初始化，配置项一律走环境变量。
    """
    global _args
    from lightrag.api.config import initialize_config

    argv = sys.argv
    sys.argv = [argv[0] if argv else "main.py"]
    try:
        _args = initialize_config(force=True)
    finally:
        sys.argv = argv
    return _args


class ConsoleStaticFiles(StaticFiles):
    """注入 window.__LIGHTRAG_CONFIG__。

    打包后的 SPA 用该配置里的 apiPrefix 拼 axios baseURL；不注入时它按
    「API 与页面同源同根」假设工作，而我们的 API 挂在 /lightrag-api 下。
    """

    def __init__(self, *args, runtime_config: bytes, **kwargs):
        self._runtime_config = runtime_config
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if not isinstance(response, FileResponse) or response.status_code != 200:
            return response
        if response.media_type != "text/html":
            return response
        try:
            content = Path(response.path).read_bytes()
        except OSError:
            logger.warning("无法读取 %s 注入运行时配置", response.path)
            return response
        if RUNTIME_CONFIG_PLACEHOLDER in content:
            content = content.replace(RUNTIME_CONFIG_PLACEHOLDER, self._runtime_config)
            response = Response(content=content, media_type="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


def _register_console_routes(app: FastAPI) -> None:
    """/auth-status、/login、/auth/verify、/health、/ui/customization。

    这几个是 WebUI 启动的前置接口，且不依赖 LightRAG 实例。前四个在
    lightrag_server.create_app() 里是内联定义的、没法复用，因此按原实现重写一份
    （去掉登录爆破限速），token 仍由 LightRAG 的 auth_handler 签发，
    保证 routers 里的 combined_auth 能验通过。
    """
    from lightrag import __version__ as core_version
    from lightrag.api.auth import auth_handler
    from lightrag.api.routers.ui_customization_routes import (
        create_ui_customization_routes,
    )
    from lightrag.api.utils_api import auth_configured

    webui_title = os.getenv("WEBUI_TITLE")
    webui_description = os.getenv("WEBUI_DESCRIPTION")
    # snapshot=None = 「未配置 UI_TEMPLATES_DIR」的正常部署，返回 200 customized:false
    app.include_router(
        create_ui_customization_routes(
            None, webui_title, webui_description
        )
    )
    brand = {
        "core_version": core_version,
        "api_version": core_version,
        "webui_title": webui_title,
        "webui_description": webui_description,
        "ai_content_notice_enabled": bool(
            getattr(_args, "enable_ai_content_notice", False)
        ),
    }

    def guest_payload() -> dict:
        token = auth_handler.create_token(
            username="guest", role="guest", metadata={"auth_mode": "disabled"}
        )
        return {
            "auth_configured": False,
            "access_token": token,
            "token_type": "bearer",
            "auth_mode": "disabled",
            "message": "Authentication is disabled. Using guest access.",
            **brand,
        }

    @app.get("/auth-status")
    async def auth_status():
        if auth_configured:
            return {"auth_configured": True, "auth_mode": "enabled", **brand}
        return guest_payload()

    @app.post("/login")
    async def login(form_data: OAuth2PasswordRequestForm = Depends()):
        if not auth_handler.accounts:
            return guest_payload()
        ok = await asyncio.to_thread(
            auth_handler.verify_password, form_data.username, form_data.password
        )
        if not ok:
            raise HTTPException(status_code=401, detail="Incorrect credentials")
        token = auth_handler.create_token(
            username=form_data.username, role="user", metadata={"auth_mode": "enabled"}
        )
        return {
            "access_token": token,
            "token_type": "bearer",
            "auth_mode": "enabled",
            **brand,
        }

    @app.get("/auth/verify")
    async def auth_verify():
        return {"status": "ok"}

    @app.get("/health")
    async def health():
        from lightrag.kg.shared_storage import get_default_workspace, get_namespace_data

        payload = {
            "status": "healthy",
            "auth_mode": "enabled" if auth_configured else "disabled",
            "webui_available": True,
            "api_docs_available": False,
            "pipeline_busy": False,
            "pipeline_active": False,
            **brand,
        }
        # 存储未初始化（LightRAG 启动失败）时读命名空间会报 ERROR，只给存活信号
        if not getattr(app.state, "lightrag_ready", False):
            return payload
        try:
            status_data = await get_namespace_data(
                "pipeline_status", workspace=get_default_workspace()
            )
            busy = bool(status_data.get("busy", False))
            payload["pipeline_busy"] = busy
            payload["pipeline_active"] = busy or bool(
                status_data.get("scanning", False)
            )
        except Exception as exc:  # 探针不能把 liveness 变成 500
            logger.debug("读取 pipeline 状态失败：%s", exc)
        return payload


def mount_console(app: FastAPI) -> bool:
    """注册路由挂载点。LightRAG 本身在这里只建空 app，路由等 wire_console()。"""
    if not enabled() or _state(app) is not None:
        return False

    _init_lightrag_config()
    from lightrag import api as lightrag_api

    webui_dir = Path(lightrag_api.__file__).parent / "webui"
    if not (webui_dir / "index.html").exists():
        logger.warning("LightRAG WebUI 资源缺失（%s），控制台未挂载", webui_dir)
        return False

    api_key = _api_key()
    if not (auth_has_accounts() or api_key):
        logger.warning(
            "LightRAG 控制台已开放挂载：未配置 AUTH_ACCOUNTS / LIGHTRAG_API_KEY，"
            "任何人都能删除文档与改写图谱。公网部署请至少配置其中一项。"
        )

    console_app = FastAPI(
        title="LightRAG Console", docs_url=None, redoc_url=None, openapi_url=None
    )
    # document_routes 的后台任务（scan/delete/enqueue）都注册到这个集合上
    console_app.state.background_tasks = set()
    console_app.state.lightrag_ready = False
    _register_console_routes(console_app)
    setattr(app.state, STATE_KEY, ConsoleState(console_app))

    payload = json.dumps(
        {
            "apiPrefix": API_PATH,
            "webuiPrefix": f"{UI_PATH}/",
            "webuiTitle": os.getenv("WEBUI_TITLE") or None,
        }
    ).replace("</", "<\\/")
    runtime_config = (
        f"<script>window.__LIGHTRAG_CONFIG__ = {payload};"
        "if(window.__LIGHTRAG_CONFIG__.webuiTitle)"
        "{document.title=window.__LIGHTRAG_CONFIG__.webuiTitle;}</script>"
    ).encode("utf-8")

    app.mount(API_PATH, console_app, name="lightrag-api")
    app.mount(
        UI_PATH,
        ConsoleStaticFiles(
            directory=str(webui_dir), html=True, runtime_config=runtime_config
        ),
        name="lightrag-webui",
    )
    logger.info("LightRAG 控制台：页面 %s，接口 %s", UI_PATH, API_PATH)
    return True


def auth_has_accounts() -> bool:
    from lightrag.api.auth import auth_handler

    return bool(auth_handler.accounts)


def _api_key() -> str | None:
    """控制台 X-API-Key 鉴权取值，与 lightrag_server 一致；挂载告警与接线必须同源。"""
    return os.getenv("LIGHTRAG_API_KEY") or getattr(_args, "key", None)


def wire_console(host: FastAPI, rag) -> bool:
    """LightRAG 单例就绪后，把官方文档/图谱/查询路由接到控制台的子 app 上。"""
    state = _state(host)
    if state is None or state.wired:
        return False

    from lightrag.api.routers.document_routes import (
        DocumentManager,
        create_document_routes,
    )
    from lightrag.api.routers.graph_routes import create_graph_routes
    from lightrag.api.routers.query_routes import create_query_routes

    settings = get_settings()
    api_key = _api_key()
    # 上传落盘目录跟着 working_dir 走，避免 LightRAG 默认的 ./inputs 跑到仓库根
    input_dir = Path(settings.LIGHTRAG_WORKING_DIR).parent / "lightrag-input"
    doc_manager = DocumentManager(str(input_dir), workspace=_args.workspace or "")

    state.app.include_router(create_document_routes(rag, doc_manager, api_key))
    state.app.include_router(create_query_routes(rag, api_key, _args.top_k))
    state.app.include_router(create_graph_routes(rag, api_key))
    state.wired = True
    state.app.state.lightrag_ready = True
    return True


async def shutdown_console(host: FastAPI) -> None:
    """取消并 join 后台任务，让每个子任务的 finally 释放流水线预约（须在存储关闭前）。"""
    state = _state(host)
    if state is None:
        return
    try:
        from lightrag.kg.shared_storage import drain_reserved_background_tasks

        await drain_reserved_background_tasks(state.app.state.background_tasks)
    except Exception:
        logger.warning("LightRAG 控制台后台任务收尾失败", exc_info=True)
