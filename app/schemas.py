from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None


class Event(BaseModel):
    name: str
    data: dict[str, Any] = Field(default_factory=dict)


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
