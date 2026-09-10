"""create_agent 构建器（03 §3.2）：模型 + 工具适配 + system prompt + checkpointer。

rag_service 不在此注入——course_rag_query 在 create_registry(rag_service) 时
已构造注入（05 §2.4），builder 只面向 registry。审批策略定稿为
HumanInTheLoopMiddleware（03 §3.4 优先第二种）：按工具名粒度中断，只有
APPROVAL_TOOLS 内的工具暂停等审批，本地纯计算与课程检索不受影响。
"""

from pathlib import Path

import aiosqlite
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.middleware import CompoundTaskMiddleware
from app.agent.registry import ToolRegistry
from app.config import get_settings

DEFAULT_DB_PATH = "data/langgraph.db"

SYSTEM_PROMPT = """你是"计算机网络"课程的智能助教，运行在课程演示系统中。
你可以使用工具：
- course_rag_query：检索课程课件与教材，回答概念/原理/协议类问题；
- subnet_calculator：IPv4 子网计算（网络地址、掩码、广播、可用主机）；
- lpm_lookup：路由表最长前缀匹配查表，可展示比对过程；
- dns_lookup：域名 DNS 解析。
行为准则：
1. 回答前先在思考中把问题拆成子问题清单，说明每个子问题需要哪个工具的数据；
2. 需要数据的问题必须调用工具，不得心算编造子网结果；
3. 每轮只调用一个工具，拿到观察结果后逐项核对子问题清单：只要有子问题还没有对应的工具观察结果，就必须继续调用下一个工具；
4. 所有子问题都有工具观察结果支撑后才允许给最终答案；复合问题只调用一次工具通常不足以完整回答；
5. 引用课件内容必须来自 course_rag_query 的检索结果并注明课件名，不得凭记忆虚构课件内容；
6. 最终答案用中文，先给结论再给关键过程，引用检索结果时注明来自哪份课件；
7. 与计算机网络无关的问题不调用工具，简要说明你的服务范围。"""

_saver: AsyncSqliteSaver | None = None
_conn: aiosqlite.Connection | None = None


async def open_checkpointer(db_path: str = DEFAULT_DB_PATH) -> AsyncSqliteSaver:
    global _saver, _conn
    if _saver is not None:
        return _saver
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _conn = await aiosqlite.connect(db_path)
    _saver = AsyncSqliteSaver(_conn)
    await _saver.setup()
    return _saver


async def close_checkpointer() -> None:
    global _saver, _conn
    if _conn is not None:
        await _conn.close()
    _saver = None
    _conn = None


def _approval_tools() -> dict[str, dict]:
    """APPROVAL_TOOLS 逗号分隔配置 → HumanInTheLoopMiddleware 的 interrupt_on。"""
    settings = get_settings()
    if not settings.HITL_ENABLED:
        return {}
    return {
        name.strip(): {"allowed_decisions": ["approve", "edit", "reject"]}
        for name in settings.APPROVAL_TOOLS.split(",")
        if name.strip()
    }


def build_agent(registry: ToolRegistry, model=None):
    """构建 ReAct 图：LangChain 1.x 节点名为 model/tools。"""
    settings = get_settings()
    if model is None:
        model = ChatOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            timeout=settings.LLM_TIMEOUT,
            extra_body={"enable_thinking": False},
        )
    interrupt_on = _approval_tools()
    middleware: list = [CompoundTaskMiddleware()]
    if interrupt_on:
        middleware.append(
            HumanInTheLoopMiddleware(
                interrupt_on=interrupt_on,
                description_prefix="该工具会产生真实网络请求，执行前需要人工审批",
            )
        )
    return create_agent(
        model=model,
        tools=registry.to_langchain_tools(),
        system_prompt=SYSTEM_PROMPT,
        checkpointer=_saver,
        middleware=middleware,
    )
