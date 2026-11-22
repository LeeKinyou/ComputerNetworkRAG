r"""把本地 SQLite 演示数据搬到 PostgreSQL。

用法（在 backend 目录下）：
    .\.venv\Scripts\python.exe scripts\migrate_sqlite_to_pg.py --dry-run
    .\.venv\Scripts\python.exe scripts\migrate_sqlite_to_pg.py

行为：
- 按 `app.models` 的 metadata 建表（幂等）；
- 清空目标库中这些业务表，再把 SQLite 全量灌进去（先清后灌，可重复执行）；
- JSON / 布尔 / 时间列按模型类型还原，最后逐表核对行数。
LangGraph 的 checkpoint 表不在 metadata 里，脚本不会动它们。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import DateTime, JSON, Boolean, func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import Base  # noqa: E402


def convert(value, column):
    if value is None:
        return None
    if isinstance(column.type, JSON):
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return []
        return value
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime) and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value


def read_sqlite(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        raise SystemExit(f"SQLite 文件不存在：{path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    data: dict[str, list[dict]] = {}
    tables = list(Base.metadata.sorted_tables)
    for table in tables:
        columns = [column.name for column in table.columns]
        rows = connection.execute(f"SELECT * FROM {table.name}").fetchall()
        data[table.name] = [
            {name: convert(row[name], table.columns[name]) for name in columns if name in row.keys()}
            for row in rows
        ]
    connection.close()
    return data


async def migrate(data: dict[str, list[dict]], dry_run: bool) -> None:
    engine = create_async_engine(settings.db_postgres_dsn, echo=False)
    tables = list(Base.metadata.sorted_tables)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if dry_run:
                for table in tables:
                    print(f"{table.name}: {len(data[table.name])} 行（未写入）")
                return

            names = ", ".join(table.name for table in tables)
            await conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
            for table in tables:
                rows = data[table.name]
                if rows:
                    await conn.execute(table.insert(), rows)
            print(f"已写入 {len(tables)} 张表：")
            for table in tables:
                target = await conn.scalar(select(func.count()).select_from(table))
                source = len(data[table.name])
                flag = "OK" if target == source else "MISMATCH"
                print(f"  {table.name:<16} sqlite={source:<5} postgres={target:<5} {flag}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(settings.sqlite_path))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = read_sqlite(Path(args.sqlite))
    asyncio.run(migrate(data, args.dry_run))


if __name__ == "__main__":
    main()
