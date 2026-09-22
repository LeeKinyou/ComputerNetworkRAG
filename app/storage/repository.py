from abc import ABC, abstractmethod

from app.schemas import DocumentMeta, MessageRecord, RunRecord, SessionMeta, StepRecord


class Repository(ABC):
    async def init(self) -> None:
        """初始化存储（建表等）。"""

    async def close(self) -> None:
        """释放存储连接。"""

    # ----- documents -----

    @abstractmethod
    async def upsert_document(self, meta: DocumentMeta) -> None: ...

    @abstractmethod
    async def list_documents(self) -> list[DocumentMeta]: ...

    @abstractmethod
    async def set_document_status(self, doc_id: str, status: str, **kw) -> None: ...

    @abstractmethod
    async def delete_document(self, doc_id: str) -> None: ...

    # ----- sessions / messages -----

    @abstractmethod
    async def create_session(self, mode: str, title: str) -> str: ...

    @abstractmethod
    async def list_sessions(self) -> list[SessionMeta]: ...

    @abstractmethod
    async def add_message(
        self, session_id: str, role: str, content: str, run_id: str | None = None
    ) -> str: ...

    @abstractmethod
    async def list_messages(self, session_id: str) -> list[MessageRecord]: ...

    # ----- agent trace -----

    @abstractmethod
    async def create_run(self, session_id: str, question: str) -> str: ...

    @abstractmethod
    async def append_step(self, run_id: str, step: StepRecord) -> None: ...

    @abstractmethod
    async def finish_run(
        self, run_id: str, status: str, answer: str | None, steps_count: int
    ) -> None: ...

    @abstractmethod
    async def get_run(self, run_id: str) -> RunRecord | None: ...

    @abstractmethod
    async def get_run_steps(self, run_id: str) -> list[StepRecord]: ...

    # ----- 大屏聚合（只读） -----

    @abstractmethod
    async def screen_tool_stats(self) -> list[dict]: ...

    @abstractmethod
    async def screen_message_trend(self, since: str) -> dict[str, int]: ...

    @abstractmethod
    async def screen_run_stats(self) -> dict: ...

    @abstractmethod
    async def screen_feed(self, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    async def screen_chapter_entities(self) -> dict[int, int]: ...
