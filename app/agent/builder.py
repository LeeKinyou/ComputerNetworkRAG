"""create_agent 构建器（03 §3.2）：模型 + 工具适配 + system prompt + checkpointer。

rag_service 不在此注入——course_rag_query 在 create_registry(rag_service) 时
已构造注入（05 §2.4），builder 只面向 registry。
"""

from pathlib import Path

import aiosqlite
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

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
1. 回答前先判断问题类型并在思考中说明，需要数据时必须调用工具，不得心算编造子网结果；
2. 复合问题分步骤调用，每次只调用一个工具，拿到观察结果后再决定下一步；
3. 最终答案用中文，先给结论再给关键过程，引用检索结果时注明来自哪份课件；
4. 与计算机网络无关的问题不调用工具，简要说明你的服务范围。"""

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


def build_agent(registry: ToolRegistry, model=None):
    """构建 ReAct 图：LangChain 1.x 节点名为 model/tools。"""
    if model is None:
        settings = get_settings()
        model = ChatOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            timeout=settings.LLM_TIMEOUT,
            extra_body={"enable_thinking": False},
        )
    return create_agent(
        model=model,
        tools=registry.to_langchain_tools(),
        system_prompt=SYSTEM_PROMPT,
        checkpointer=_saver,
    )
