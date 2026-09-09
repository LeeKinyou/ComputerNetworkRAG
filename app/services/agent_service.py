"""AgentService：run 生命周期与 trace 落库（03 §3.2、04 §6.2/§6.4）。

事件到库的对应关系：thought/action/observation 各写一行 agent_steps；
meta/step_start/token 不落步骤表，final 落 agent_runs（status/final_answer）
并追加 assistant 消息。run 的状态只有 success/failed 两种：客户端中途断开、
模型异常都会走 failed，保证没有悬挂在 running 的 run。
"""

import anyio
import asyncio
import logging
from typing import AsyncIterator

from app.agent.runner import run_agent
from app.schemas import Event, StepRecord
from app.services.rag_service import _error_message
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

_TITLE_LEN = 30


def _title(question: str) -> str:
    return question if len(question) <= _TITLE_LEN else question[:_TITLE_LEN] + "…"


class AgentService:
    def __init__(self, repo: Repository, agent=None):
        self._repo = repo
        self._agent = agent

    @property
    def agent(self):
        return self._agent

    async def stream_chat(
        self, question: str, session_id: str | None = None
    ) -> AsyncIterator[Event]:
        if self._agent is None:
            raise RuntimeError("Agent 尚未初始化")
        if not session_id:
            session_id = await self._repo.create_session("agent", _title(question))
        run_id = await self._repo.create_run(session_id, question)
        await self._repo.add_message(session_id, "user", question, run_id)

        answer_parts: list[str] = []
        last_step_no = 0

        try:
            async for ev in run_agent(self._agent, question, run_id, session_id):
                if ev.name == "thought":
                    last_step_no = max(last_step_no, ev.data.get("step_no") or 0)
                    await self._repo.append_step(
                        run_id,
                        StepRecord(
                            run_id=run_id,
                            step_no=ev.data["step_no"],
                            kind="thought",
                            content=ev.data.get("content") or "",
                        ),
                    )
                elif ev.name == "action":
                    last_step_no = max(last_step_no, ev.data.get("step_no") or 0)
                    await self._repo.append_step(
                        run_id,
                        StepRecord(
                            run_id=run_id,
                            step_no=ev.data["step_no"],
                            kind="action",
                            tool_name=ev.data.get("tool") or "",
                            tool_args=ev.data.get("args") or {},
                        ),
                    )
                elif ev.name == "observation":
                    last_step_no = max(last_step_no, ev.data.get("step_no") or 0)
                    await self._repo.append_step(
                        run_id,
                        StepRecord(
                            run_id=run_id,
                            step_no=ev.data["step_no"],
                            kind="observation",
                            status=ev.data.get("status") or "failed",
                            elapsed_ms=int(ev.data.get("elapsed_ms") or 0),
                            content=ev.data.get("result") or "",
                            structured=ev.data.get("structured") or {},
                        ),
                    )
                elif ev.name == "token":
                    answer_parts.append(ev.data.get("delta") or "")
                elif ev.name == "final":
                    last_step_no = int(ev.data.get("steps_count") or 0)
                    answer = ev.data.get("answer") or ""
                    await self._repo.finish_run(run_id, "success", answer, last_step_no)
                    await self._repo.add_message(session_id, "assistant", answer, run_id)
                yield ev
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开。sse-starlette 用 anyio 取消流任务，而被取消的 scope 会对
            # 其中任务的每个 await 反复重投递取消——清理若裸 await 必被打断（实测
            # run 永远停在 running）。anyio 的标准做法：清理放进 shield 作用域，
            # 完成落库后再把取消继续向上抛。
            logger.info("Agent 流中断，标记 run 失败 run=%s", run_id)
            with anyio.CancelScope(shield=True):
                await self._repo.finish_run(
                    run_id, "failed", "".join(answer_parts) or None, last_step_no
                )
            raise
        except Exception as exc:  # noqa: BLE001 — 任何异常都转 error 事件
            message = _error_message(exc)
            logger.warning("Agent 运行失败 run=%s：%s", run_id, exc)
            # error 步骤沿用当前 step_no（ORDER BY step_no,rowid 时排在同轮之后），
            # append_step 会把 steps_count 同步为该值，不会污染轮次计数
            await self._repo.append_step(
                run_id,
                StepRecord(
                    run_id=run_id, step_no=last_step_no, kind="error", content=message
                ),
            )
            await self._repo.finish_run(
                run_id, "failed", "".join(answer_parts) or None, last_step_no
            )
            yield Event(name="error", data={"message": message})


_agent_service: AgentService | None = None


def init_agent_service(repo: Repository, agent=None) -> AgentService:
    global _agent_service
    _agent_service = AgentService(repo, agent)
    return _agent_service


def get_agent_service() -> AgentService:
    if _agent_service is None:
        raise RuntimeError("AgentService 尚未初始化")
    return _agent_service
