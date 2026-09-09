import json
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.schemas import DocumentMeta, MessageRecord, RunRecord, SessionMeta, StepRecord
from app.storage.repository import Repository

DDL = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id      TEXT PRIMARY KEY,
  filename    TEXT NOT NULL,
  safe_name   TEXT NOT NULL,
  ext         TEXT NOT NULL,
  size_bytes  INTEGER NOT NULL,
  parser      TEXT NOT NULL,
  status      TEXT NOT NULL,
  chunk_count INTEGER DEFAULT 0,
  error       TEXT,
  raw_path    TEXT NOT NULL,
  parsed_path TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id     TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  mode           TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  last_active_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  msg_id     TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  role       TEXT NOT NULL,
  content    TEXT NOT NULL,
  run_id     TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

CREATE TABLE IF NOT EXISTS agent_runs (
  run_id       TEXT PRIMARY KEY,
  session_id   TEXT NOT NULL REFERENCES sessions(session_id),
  question     TEXT NOT NULL,
  final_answer TEXT,
  status       TEXT NOT NULL,
  steps_count  INTEGER DEFAULT 0,
  started_at   TEXT NOT NULL,
  finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS agent_steps (
  step_id    TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL REFERENCES agent_runs(run_id),
  step_no    INTEGER NOT NULL,
  kind       TEXT NOT NULL,
  tool_name  TEXT,
  tool_args  TEXT,
  content    TEXT,
  structured TEXT,
  status     TEXT,
  elapsed_ms INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON agent_steps(run_id);
"""

_STATUS_FIELDS = {"error", "chunk_count", "parsed_path"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class SqliteRepository(Repository):
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(DDL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SqliteRepository 尚未 init()")
        return self._db

    # ----- documents -----

    async def upsert_document(self, meta: DocumentMeta) -> None:
        ts = now()
        await self._conn().execute(
            """
            INSERT INTO documents (doc_id, filename, safe_name, ext, size_bytes, parser,
                                   status, chunk_count, error, raw_path, parsed_path,
                                   created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
              filename=excluded.filename, safe_name=excluded.safe_name,
              ext=excluded.ext, size_bytes=excluded.size_bytes, parser=excluded.parser,
              status=excluded.status, chunk_count=excluded.chunk_count,
              error=excluded.error, raw_path=excluded.raw_path,
              parsed_path=excluded.parsed_path, updated_at=excluded.updated_at
            """,
            (
                meta.doc_id, meta.filename, meta.safe_name, meta.ext, meta.size_bytes,
                meta.parser, meta.status, meta.chunk_count, meta.error, meta.raw_path,
                meta.parsed_path, meta.created_at or ts, ts,
            ),
        )
        await self._conn().commit()

    async def list_documents(self) -> list[DocumentMeta]:
        async with self._conn().execute(
            "SELECT * FROM documents ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [DocumentMeta(**dict(row)) for row in rows]

    async def set_document_status(self, doc_id: str, status: str, **kw) -> None:
        unknown = set(kw) - _STATUS_FIELDS
        if unknown:
            raise ValueError(f"不支持的状态附加字段: {unknown}")
        sets = ["status = ?", "updated_at = ?"]
        params: list = [status, now()]
        for field in ("error", "chunk_count", "parsed_path"):
            if field in kw:
                sets.append(f"{field} = ?")
                params.append(kw[field])
        params.append(doc_id)
        await self._conn().execute(
            f"UPDATE documents SET {', '.join(sets)} WHERE doc_id = ?", params
        )
        await self._conn().commit()

    async def delete_document(self, doc_id: str) -> None:
        await self._conn().execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        await self._conn().commit()

    # ----- sessions / messages -----

    async def create_session(self, mode: str, title: str) -> str:
        session_id = new_id("s")
        ts = now()
        await self._conn().execute(
            "INSERT INTO sessions (session_id, title, mode, created_at, last_active_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, title, mode, ts, ts),
        )
        await self._conn().commit()
        return session_id

    async def list_sessions(self) -> list[SessionMeta]:
        async with self._conn().execute(
            "SELECT * FROM sessions ORDER BY last_active_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [SessionMeta(**dict(row)) for row in rows]

    async def add_message(
        self, session_id: str, role: str, content: str, run_id: str | None = None
    ) -> str:
        msg_id = new_id("m")
        ts = now()
        await self._conn().execute(
            "INSERT INTO messages (msg_id, session_id, role, content, run_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, run_id, ts),
        )
        await self._conn().execute(
            "UPDATE sessions SET last_active_at = ? WHERE session_id = ?", (ts, session_id)
        )
        await self._conn().commit()
        return msg_id

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        async with self._conn().execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at, rowid",
            (session_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [MessageRecord(**dict(row)) for row in rows]

    # ----- agent trace -----

    async def create_run(self, session_id: str, question: str) -> str:
        run_id = new_id("r")
        await self._conn().execute(
            "INSERT INTO agent_runs (run_id, session_id, question, status, steps_count, started_at) "
            "VALUES (?, ?, ?, 'running', 0, ?)",
            (run_id, session_id, question, now()),
        )
        await self._conn().commit()
        return run_id

    async def append_step(self, run_id: str, step: StepRecord) -> None:
        step_id = step.step_id or new_id("st")
        await self._conn().execute(
            """
            INSERT INTO agent_steps (step_id, run_id, step_no, kind, tool_name, tool_args,
                                     content, structured, status, elapsed_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id, run_id, step.step_no, step.kind, step.tool_name,
                json.dumps(step.tool_args, ensure_ascii=False) if step.tool_args is not None else None,
                step.content,
                json.dumps(step.structured, ensure_ascii=False) if step.structured is not None else None,
                step.status, step.elapsed_ms, step.created_at or now(),
            ),
        )
        await self._conn().execute(
            "UPDATE agent_runs SET steps_count = ? WHERE run_id = ?", (step.step_no, run_id)
        )
        await self._conn().commit()

    async def finish_run(
        self, run_id: str, status: str, answer: str | None, steps_count: int
    ) -> None:
        await self._conn().execute(
            "UPDATE agent_runs SET status = ?, final_answer = ?, steps_count = ?, finished_at = ? "
            "WHERE run_id = ?",
            (status, answer, steps_count, now(), run_id),
        )
        await self._conn().commit()

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with self._conn().execute(
            "SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()
        return RunRecord(**dict(row)) if row else None

    async def get_run_steps(self, run_id: str) -> list[StepRecord]:
        async with self._conn().execute(
            "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY step_no, rowid", (run_id,)
        ) as cur:
            rows = await cur.fetchall()
        steps = []
        for row in rows:
            data = dict(row)
            data["tool_args"] = json.loads(data["tool_args"]) if data["tool_args"] else None
            data["structured"] = json.loads(data["structured"]) if data["structured"] else None
            steps.append(StepRecord(**data))
        return steps


_repo: SqliteRepository | None = None


def init_repo(db_path: Path) -> SqliteRepository:
    global _repo
    _repo = SqliteRepository(db_path)
    return _repo


def get_repo() -> Repository:
    if _repo is None:
        raise RuntimeError("Repository 尚未初始化")
    return _repo
