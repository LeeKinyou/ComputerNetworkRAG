from abc import ABC, abstractmethod

from app.schemas import (
    DocumentMeta,
    KnowledgeNode,
    MessageRecord,
    PrereqEdge,
    RunRecord,
    SessionMeta,
    StepRecord,
    TouchRecord,
)


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

    # ----- 知识点触达（Task 5.4） -----

    @abstractmethod
    async def add_touches(self, records: list[TouchRecord]) -> int:
        """批量写入触达记录，返回写入条数。"""

    @abstractmethod
    async def lookup_kp_ids(self, names: list[str]) -> dict[str, str]:
        """按实体名反查 kp_id，只返回物化快照（knowledge_node）里存在的名字。"""

    # ----- 学习路径物化（Task 5.5） -----

    @abstractmethod
    async def upsert_knowledge_nodes(self, rows: list[KnowledgeNode]) -> int:
        """写入/刷新知识点快照，返回写入条数；同一实体名重建不换 kp_id。"""

    @abstractmethod
    async def list_knowledge_nodes(self, chapter: int | None = None) -> list[KnowledgeNode]:
        """chapter=None 返回全部（含未归章的实体）。"""

    @abstractmethod
    async def replace_prereq_edges(self, chapter: int, rows: list[PrereqEdge]) -> int:
        """整体替换该章的前驱边，重跑幂等。"""

    @abstractmethod
    async def list_prereq_edges(self, chapter: int | None = None) -> list[PrereqEdge]: ...

    @abstractmethod
    async def relink_touch_kp_ids(self) -> int:
        """按 kp_name 回填触达记录的 kp_id（只补空值），返回回填条数。"""

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
