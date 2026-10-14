import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import aiosqlite

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
from app.storage.repository import Repository

logger = logging.getLogger(__name__)

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

-- 触达记录（Task 5.4）：kp_name 先于 knowledge_node 存在（Task 5.5 建表），
-- 故 kp_id 可空、由构建脚本按 name 回填；via: rag_hit | agent_tool | path_view
CREATE TABLE IF NOT EXISTS knowledge_touch (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  kp_name    TEXT NOT NULL,
  kp_id      TEXT,
  session_id TEXT,
  run_id     TEXT,
  via        TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kt_kp ON knowledge_touch(kp_id);
CREATE INDEX IF NOT EXISTS idx_kt_name ON knowledge_touch(kp_name);

-- 知识点物化（Task 5.5）：图谱实体的离线快照，kp_id 由实体名散列得到，
-- 重建索引后仍可复用；chapter=NULL 表示归章失败，不参与路径但保留可查。
-- docs/09 §3.2 里的 section 列暂不落地：本章只做到章级归属。
CREATE TABLE IF NOT EXISTS knowledge_node (
  kp_id        TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  entity_type  TEXT,
  chapter      INTEGER,
  description  TEXT,
  degree       INTEGER DEFAULT 0,
  doc_id       TEXT,
  source_chunk TEXT,
  built_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kn_chapter ON knowledge_node(chapter);

-- 前驱边（Task 5.5）：source 先于 target，章内由 LLM 抽取 + 代码校验后落库，保证无环。
CREATE TABLE IF NOT EXISTS prereq_edge (
  source     TEXT NOT NULL,
  target     TEXT NOT NULL,
  chapter    INTEGER NOT NULL,
  reason     TEXT,
  confidence REAL DEFAULT 0.6,
  status     TEXT DEFAULT 'auto',
  PRIMARY KEY (source, target)
);
CREATE INDEX IF NOT EXISTS idx_pe_chapter ON prereq_edge(chapter);
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
        # 构建脚本与服务进程会并发写同一个库文件：默认 rollback journal 下并发写直接
        # 报 database is locked，WAL 让读写互不阻塞，busy_timeout 兜住偶发的写锁竞争。
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
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

    # ----- 知识点触达（Task 5.4） -----

    async def add_touches(self, records: list[TouchRecord]) -> int:
        if not records:
            return 0
        ts = now()
        await self._conn().executemany(
            "INSERT INTO knowledge_touch (kp_name, kp_id, session_id, run_id, via, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (r.kp_name, r.kp_id, r.session_id, r.run_id, r.via, r.created_at or ts)
                for r in records
            ],
        )
        await self._conn().commit()
        return len(records)

    async def lookup_kp_ids(self, names: list[str]) -> dict[str, str]:
        """按实体名反查 kp_id，只返回物化快照里存在的名字（未物化的长尾留空由 relink 补）。"""
        if not names:
            return {}
        marks = ",".join("?" * len(names))
        async with self._conn().execute(
            f"SELECT kp_id, name FROM knowledge_node WHERE name IN ({marks})", names
        ) as cur:
            rows = await cur.fetchall()
        return {r["name"]: r["kp_id"] for r in rows}

    # ----- 学习路径物化（Task 5.5） -----

    async def upsert_knowledge_nodes(self, rows: list[KnowledgeNode]) -> int:
        """kp_id 是实体名的散列，因此重建只更新属性、不换 ID（触达记录才不会失联）。"""
        if not rows:
            return 0
        await self._conn().executemany(
            """
            INSERT INTO knowledge_node (kp_id, name, entity_type, chapter, description,
                                        degree, doc_id, source_chunk, built_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kp_id) DO UPDATE SET
              name=excluded.name, entity_type=excluded.entity_type,
              chapter=excluded.chapter, description=excluded.description,
              degree=excluded.degree, doc_id=excluded.doc_id,
              source_chunk=excluded.source_chunk, built_at=excluded.built_at
            """,
            [
                (
                    r.kp_id, r.name, r.entity_type, r.chapter, r.description,
                    r.degree, r.doc_id, r.source_chunk, r.built_at or now(),
                )
                for r in rows
            ],
        )
        await self._conn().commit()
        return len(rows)

    async def list_knowledge_nodes(self, chapter: int | None = None) -> list[KnowledgeNode]:
        """chapter=None 时返回全部（含 chapter IS NULL 的未归章实体）。"""
        sql = "SELECT * FROM knowledge_node"
        params: tuple = ()
        if chapter is not None:
            sql += " WHERE chapter = ?"
            params = (chapter,)
        sql += " ORDER BY degree DESC, name"
        async with self._conn().execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [KnowledgeNode(**dict(row)) for row in rows]

    async def replace_prereq_edges(self, chapter: int, rows: list[PrereqEdge]) -> int:
        """按章整体替换：重跑同一章不累积旧边（§3.3 幂等要求）。

        主键是全局的 (source, target)，替换却是按章做的，所以先挑出被别的章占用的键
        跳过（人工把一条边改到别的章之后，重跑本章不该整批崩掉）；删与插放在同一个
        事务里，中途报错必须回滚，否则本章会停在"旧边已删、新边半截"的空状态。
        返回真正写入的条数。
        """
        conn = self._conn()
        await conn.execute("BEGIN IMMEDIATE")
        try:
            blocked = set()
            if rows:
                keys = ", ".join(["(?, ?)"] * len(rows))
                params: list[object] = []
                for r in rows:
                    params.extend((r.source, r.target))
                async with conn.execute(
                    f"SELECT source, target, chapter FROM prereq_edge "
                    f"WHERE (source, target) IN ({keys})",
                    tuple(params),
                ) as cur:
                    for row in await cur.fetchall():
                        if row["chapter"] != chapter:
                            blocked.add((row["source"], row["target"]))
                accepted = [r for r in rows if (r.source, r.target) not in blocked]
            else:
                accepted = []

            await conn.execute("DELETE FROM prereq_edge WHERE chapter = ?", (chapter,))
            if accepted:
                await conn.executemany(
                    "INSERT INTO prereq_edge (source, target, chapter, reason, confidence, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (r.source, r.target, r.chapter, r.reason, r.confidence, r.status)
                        for r in accepted
                    ],
                )
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise

        if blocked:
            logger.warning(
                "第 %s 章有 %s 条边的 (source, target) 已被其他章占用，本次未覆盖",
                chapter, len(blocked),
            )
        return len(accepted)

    async def count_prereq_edges(self, chapter: int) -> int:
        async with self._conn().execute(
            "SELECT COUNT(*) FROM prereq_edge WHERE chapter = ?", (chapter,)
        ) as cur:
            row = await cur.fetchone()
        return int(row[0])

    async def list_prereq_edges(self, chapter: int | None = None) -> list[PrereqEdge]:
        sql = "SELECT * FROM prereq_edge"
        params: tuple = ()
        if chapter is not None:
            sql += " WHERE chapter = ?"
            params = (chapter,)
        sql += " ORDER BY chapter, source, target"
        async with self._conn().execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [PrereqEdge(**dict(row)) for row in rows]

    async def list_chapters(self) -> list[int]:
        """物化快照里真正有知识点的章节：下拉框只列有数据的章，别让人点开空图。"""
        async with self._conn().execute(
            "SELECT DISTINCT chapter FROM knowledge_node "
            "WHERE chapter IS NOT NULL ORDER BY chapter"
        ) as cur:
            rows = await cur.fetchall()
        return [int(r["chapter"]) for r in rows]

    async def touch_counts_by_kp(self, kp_ids: list[str]) -> dict[str, int]:
        if not kp_ids:
            return {}
        marks = ",".join("?" * len(kp_ids))
        async with self._conn().execute(
            f"SELECT kp_id, COUNT(*) AS n FROM knowledge_touch WHERE kp_id IN ({marks}) GROUP BY kp_id",
            list(kp_ids),
        ) as cur:
            rows = await cur.fetchall()
        return {r["kp_id"]: r["n"] for r in rows}

    async def touch_coverage(self) -> dict:
        """覆盖率的分母必须与 #/path 一样只算已归章的知识点，否则大屏和路径页两个数字对不上。
        未回填 kp_id 的触达（5.4 早于 5.5 上线时留下的）进不了 JOIN，等于不计——宁少不假。"""
        async with self._conn().execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN t.n > 0 THEN 1 ELSE 0 END), 0) AS touched
            FROM knowledge_node kn
            LEFT JOIN (
              SELECT kp_id, COUNT(*) AS n FROM knowledge_touch
              WHERE kp_id IS NOT NULL GROUP BY kp_id
            ) t ON t.kp_id = kn.kp_id
            WHERE kn.chapter IS NOT NULL
            """
        ) as cur:
            row = await cur.fetchone()
        total = int(row["total"] or 0)
        touched = int(row["touched"] or 0)
        return {
            "touched": touched,
            "total": total,
            "rate": round(touched / total, 4) if total else 0.0,
        }

    async def relink_touch_kp_ids(self) -> int:
        """按 kp_name 回填触达记录的 kp_id；只补空值，已有 ID 不覆盖。返回回填条数。"""
        cur = await self._conn().execute(
            """
            UPDATE knowledge_touch SET kp_id = (
              SELECT MIN(kn.kp_id) FROM knowledge_node kn
              WHERE kn.name = knowledge_touch.kp_name
            )
            WHERE kp_id IS NULL
              AND EXISTS (
                SELECT 1 FROM knowledge_node kn2
                WHERE kn2.name = knowledge_touch.kp_name
              )
            """
        )
        await self._conn().commit()
        return cur.rowcount

    # ----- 大屏聚合（只读） -----

    async def screen_tool_stats(self) -> list[dict]:
        """工具调用统计：tool_name 只在 action 行、status/耗时只在 observation 行，
        按 (run_id, step_no) 自连接配对；unobserved 为没等到观察结果的调用数。"""
        async with self._conn().execute(
            """
            SELECT a.tool_name AS name,
                   COUNT(*) AS calls,
                   AVG(o.elapsed_ms) AS avg_ms,
                   SUM(CASE WHEN o.status = 'success' THEN 1 ELSE 0 END) AS ok_count,
                   SUM(CASE WHEN o.status IS NULL THEN 1 ELSE 0 END) AS unobserved
            FROM agent_steps a
            LEFT JOIN agent_steps o
              ON o.run_id = a.run_id AND o.step_no = a.step_no AND o.kind = 'observation'
            WHERE a.kind = 'action' AND a.tool_name IS NOT NULL AND a.tool_name <> ''
            GROUP BY a.tool_name
            ORDER BY calls DESC, name
            """
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def screen_message_trend(self, since: str) -> dict[str, int]:
        """since（含）起每日提问条数，只统计 role='user'；无数据的日期由上层补零。"""
        async with self._conn().execute(
            "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n FROM messages "
            "WHERE role = 'user' AND substr(created_at, 1, 10) >= ? GROUP BY day",
            (since,),
        ) as cur:
            rows = await cur.fetchall()
        return {r["day"]: r["n"] for r in rows}

    async def screen_run_stats(self) -> dict:
        async with self._conn().execute(
            """
            SELECT COUNT(*) AS total,
                   (SELECT COUNT(*) FROM agent_steps) AS steps,
                   COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS interrupted
            FROM agent_runs
            """
        ) as cur:
            row = await cur.fetchone()
        return dict(row)

    async def screen_feed(self, limit: int = 20) -> list[dict]:
        """最近提问，最新在前；同秒插入用 rowid 兜底保证顺序稳定。"""
        async with self._conn().execute(
            "SELECT content, created_at FROM messages WHERE role = 'user' "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def screen_chapter_entities(self) -> dict[int, int]:
        """按章统计物化知识点数；knowledge_node 由 Task 5.5 建表，未建表时返回空。"""
        try:
            async with self._conn().execute(
                "SELECT chapter, COUNT(*) AS n FROM knowledge_node "
                "WHERE chapter IS NOT NULL GROUP BY chapter"
            ) as cur:
                rows = await cur.fetchall()
        except aiosqlite.OperationalError:
            return {}
        return {int(r["chapter"]): r["n"] for r in rows}


_repo: SqliteRepository | None = None


def init_repo(db_path: Path) -> SqliteRepository:
    global _repo
    _repo = SqliteRepository(db_path)
    return _repo


def get_repo() -> Repository:
    if _repo is None:
        raise RuntimeError("Repository 尚未初始化")
    return _repo
