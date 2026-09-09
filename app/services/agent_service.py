"""AgentService：run 生命周期与 trace 落库（03 §3.2、04 §6.2/§6.4/§6.5）。

事件到库的对应关系：thought/action/observation 各写一行 agent_steps；
meta/step_start/token/interrupt/resumed 不落步骤表，final 落 agent_runs
（status/final_answer）并追加 assistant 消息。run 的状态有 success/failed/
waiting_approval 三种：客户端中途断开、模型异常走 failed；审批中断走
waiting_approval（final_answer 留空），resume 后由续跑流的 final 覆盖。
"""

import anyio
import asyncio
import logging
from typing import AsyncIterator

from app.agent.runner import (
    NoPendingInterruptError,
    get_pending_interrupts,
    resume_agent,
    run_agent,
)
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
        async for ev in self._stream_run(
            run_agent(self._agent, question, run_id, session_id), run_id, session_id
        ):
            yield ev

    async def assert_resumable(self, run_id: str):
        """resume 前置校验（04 §6.5）：run 存在、停在等待审批、检查点有中断。"""
        if self._agent is None:
            raise RuntimeError("Agent 尚未初始化")
        run = await self._repo.get_run(run_id)
        if run is None or run.status != "waiting_approval":
            raise NoPendingInterruptError("run 不存在或没有待审批的运行")
        requests = await get_pending_interrupts(self._agent, run_id)
        if not requests:
            raise NoPendingInterruptError("检查点中没有待审批的工具调用")
        return run

    async def stream_resume(
        self, run_id: str, decision: str, edited_args: dict | None = None
    ) -> AsyncIterator[Event]:
        run = await self.assert_resumable(run_id)
        step_no_start = int(run.steps_count or 0)
        async for ev in self._stream_run(
            resume_agent(self._agent, run_id, decision, edited_args, step_no_start),
            run_id,
            run.session_id,
            last_step_no=step_no_start,
        ):
            yield ev

    async def _stream_run(
        self,
        events: AsyncIterator[Event],
        run_id: str,
        session_id: str,
        last_step_no: int = 0,
    ) -> AsyncIterator[Event]:
        """事件落库 + 透传。流式来源可以是首轮 run_agent 或审批后的 resume_agent。"""
        answer_parts: list[str] = []

        try:
            async for ev in events:
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
                            step_no=ev.data.get("step_no") or 0,
                            kind="observation",
                            status=ev.data.get("status") or "failed",
                            elapsed_ms=int(ev.data.get("elapsed_ms") or 0),
                            content=ev.data.get("result") or "",
                            structured=ev.data.get("structured") or {},
                        ),
                    )
                elif ev.name == "token":
                    answer_parts.append(ev.data.get("delta") or "")
                elif ev.name == "interrupt":
                    # 审批中断：run 停在 waiting_approval，等 /resume 端点续跑
                    await self._repo.finish_run(run_id, "waiting_approval", None, last_step_no)
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
                run = await self._repo.get_run(run_id)
                if run is not None and run.status == "waiting_approval":
                    # 中断事件已落库后被断开：保留 waiting_approval，审批仍可继续
                    logger.info("Agent 流中断于等待审批，保留状态 run=%s", run_id)
                else:
                    await self._repo.finish_run(
                        run_id, "failed", "".join(answer_parts) or None, last_step_no
                    )
            raise
        except NoPendingInterruptError:
            # resume 前置条件不满足：原样上抛给端点转 409，不改 run 状态
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
