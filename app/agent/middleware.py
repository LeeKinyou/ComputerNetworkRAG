"""CompoundTaskMiddleware：复合问题多轮推进（05 §1.1）。

实测 deepseek-chat 对 system prompt 里的多轮要求阳奉阴违——一轮工具拿到
结果就直接作答。本中间件在 wrap_model_call 拦截：复合问题且已完成工具
轮数未达下限时，向**当次** model 请求末尾注入一条调度提醒，阻止过早作答。

提醒走 request.override(messages=...)，只作用于当轮调用、不写检查点状态：
若改为 after_model 注入消息跳回 model，过早答案与续跑答案会先后两次流式
下发（前端出现重复回答），这是选择调用前注入的根本原因。
"""

import re

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage

# 形如 a.b.c.d/n 的 CIDR 串：出现即认为该问题带计算型子问题
_CIDR_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b")
# 溯源要求关键词：计算结果需要课件依据佐证，至少还需一轮 course_rag_query
_EVIDENCE_KEYWORDS = ("为什么", "原因", "课件", "教材", "依据", "解释")

NUDGE_TEXT = (
    "【调度提醒】该问题包含多个子问题，目前仅完成 {rounds} 轮工具调用，"
    "还有子问题没有得到工具观察结果支撑。禁止现在直接给出最终答案："
    "请继续调用工具核实剩余子问题，全部核实后再作答。"
)


class CompoundTaskMiddleware(AgentMiddleware):
    """复合问题至少 min_tool_rounds 轮工具；轮数达标后不再干预。"""

    def __init__(self, min_tool_rounds: int = 2):
        self.min_tool_rounds = min_tool_rounds

    def is_compound(self, question: str) -> bool:
        if question.count("？") + question.count("?") >= 2:
            return True
        return bool(_CIDR_RE.search(question)) and any(
            k in question for k in _EVIDENCE_KEYWORDS
        )

    def _question_text(self, messages) -> str:
        for m in messages:
            if isinstance(m, HumanMessage):
                if isinstance(m.content, str):
                    return m.content
                if isinstance(m.content, list):
                    return "".join(
                        b.get("text", "") for b in m.content if isinstance(b, dict)
                    )
                return str(m.content or "")
        return ""

    async def awrap_model_call(self, request, handler):
        messages = request.messages
        tool_rounds = sum(
            1 for m in messages if isinstance(m, AIMessage) and m.tool_calls
        )
        if 0 < tool_rounds < self.min_tool_rounds:
            question = self._question_text(messages)
            if question and self.is_compound(question):
                nudge = HumanMessage(content=NUDGE_TEXT.format(rounds=tool_rounds))
                request = request.override(messages=[*messages, nudge])
        return await handler(request)
