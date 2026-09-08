from abc import ABC, abstractmethod

from app.schemas import DocumentMeta, SessionMeta, StepRecord


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
    async def get_run_steps(self, run_id: str) -> list[StepRecord]: ...
