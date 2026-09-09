"""course_rag_query：把课程检索交给智能体自主调用（05 §2.4）。"""

from app.agent.registry import BaseTool, ToolResult

_CONTEXT_LIMIT = 1500


class CourseRagTool(BaseTool):
    name = "course_rag_query"
    description = (
        "课程知识检索：从课程课件与教材中检索与问题相关的原文片段（不生成答案），"
        "回答概念/原理/协议类问题前先调用本工具查课件。"
        '示例：{"query": "TCP 三次握手的流程"}'
    )
    args_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题"},
            "mode": {
                "type": "string",
                "enum": ["naive", "local", "global", "hybrid"],
                "description": "检索模式，缺省跟随全局配置",
            },
        },
        "required": ["query"],
    }

    def __init__(self, rag_service):
        self._rag = rag_service

    async def _run(self, query: str = "", mode: str | None = None) -> ToolResult:
        data = await self._rag.retrieve(str(query).strip(), mode)
        chunks = data.get("chunks") or []
        resolved_mode = data.get("mode") or mode or ""
        sources = [
            {
                "doc_name": c.get("doc_name") or "未知文档",
                "chunk_id": c.get("chunk_id") or "",
                "snippet": c.get("content") or "",
            }
            for c in chunks
        ]
        structured = {"mode": resolved_mode, "sources": sources}
        if not chunks:
            return ToolResult(
                status="success",
                output=f"未检索到与“{query}”相关的课程内容",
                structured=structured,
            )

        output = ""
        used = 0
        for i, c in enumerate(chunks, 1):
            line = f"[{i}] {c.get('doc_name') or '未知文档'}：{c.get('content') or ''}"
            if len(output) + len(line) + 1 > _CONTEXT_LIMIT:
                break
            output = f"{output}\n{line}" if output else line
            used = i
        output += f"\n（共检索到 {len(chunks)} 个相关分块，以上为前 {used} 个，限长 {_CONTEXT_LIMIT} 字）"
        return ToolResult(status="success", output=output, structured=structured)
