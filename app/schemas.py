from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None


class Event(BaseModel):
    name: str
    data: dict[str, Any] = Field(default_factory=dict)


class RAGChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: str | None = None
    session_id: str | None = None


class AgentChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    tools: list[str] | None = None  # P1 工具子集，P0 缺省全部启用


class ApprovalRequest(BaseModel):
    """人工审批决策（04 §6.5）：approve 原参 / edit 换参 / reject 拒绝。"""

    decision: Literal["approve", "edit", "reject"]
    edited_args: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _edit_needs_args(self):
        if self.decision == "edit" and self.edited_args is None:
            raise ValueError("edit 决策必须提供 edited_args")
        return self


class DocumentMeta(BaseModel):
    doc_id: str
    filename: str
    safe_name: str
    ext: str
    size_bytes: int
    parser: str
    status: str = "pending"
    chunk_count: int = 0
    error: str | None = None
    raw_path: str = ""
    parsed_path: str | None = None
    created_at: str = ""
    updated_at: str = ""


class SessionMeta(BaseModel):
    session_id: str
    title: str
    mode: str
    created_at: str = ""
    last_active_at: str = ""


class MessageRecord(BaseModel):
    msg_id: str = ""
    session_id: str
    role: str
    content: str
    run_id: str | None = None
    created_at: str = ""


class RunRecord(BaseModel):
    run_id: str = ""
    session_id: str
    question: str
    final_answer: str | None = None
    status: str = "running"
    steps_count: int = 0
    started_at: str = ""
    finished_at: str | None = None


class TouchRecord(BaseModel):
    kp_name: str
    kp_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    via: str = "rag_hit"
    created_at: str = ""


class KnowledgeNode(BaseModel):
    """图谱实体的物化快照（Task 5.5）：chapter=NULL 表示归章失败，不参与路径。"""

    kp_id: str
    name: str
    entity_type: str = "概念"
    chapter: int | None = None
    description: str = ""
    degree: int = 0
    doc_id: str = ""
    source_chunk: str = ""
    built_at: str = ""


class PrereqEdge(BaseModel):
    """前驱边：source 必须先于 target 学，chapter 取自 source 的归属章。"""

    source: str
    target: str
    chapter: int
    reason: str = ""
    confidence: float = 0.6
    status: str = "auto"


class StepRecord(BaseModel):
    step_id: str = ""
    run_id: str
    step_no: int
    kind: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    content: str | None = None
    structured: dict[str, Any] | None = None
    status: str | None = None
    elapsed_ms: int = 0
    created_at: str = ""
