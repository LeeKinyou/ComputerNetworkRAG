r"""给演示库补上「上周」的作答记录，让学习报告的本周/上周趋势线有真实对比。

用法（在 backend 目录下）：
    .\.venv\Scripts\python.exe scripts\seed_demo_history.py --dry-run
    .\.venv\Scripts\python.exe scripts\seed_demo_history.py

行为：
- 只补 7~13 天前的作答（滚动 14 天窗口的上半段），本周数据保持原样；
- 每人的历史 id 固定为 `hist-<user>-<期号>-<序号>`，重复执行时已存在的整批跳过；
- 不改题库、不删任何已有记录。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.db import SessionFactory, engine  # noqa: E402
from app.models import Attempt, Question  # noqa: E402

COURSE_ID = "course_cn"
BATCH = "w13"  # 期号写进 id，换一批历史时改这里即可再补

# (days_ago, 当天题数, 其中做对几题)
PLAN: dict[str, list[tuple[int, int, int]]] = {
    "demo_user": [(13, 2, 0), (11, 2, 1), (9, 3, 1)],   # 3/7 ≈ 43%，本周约 60%
    "stu_lin": [(12, 2, 0), (10, 2, 1), (8, 2, 0)],     # 1/6 ≈ 17%，本周约 40%
    "stu_zhao": [(12, 2, 2), (10, 2, 1), (8, 2, 1)],    # 4/6 ≈ 67%，本周 100%
}


# 演示身份当前就有的错题：历史里的错误作答只从这批题里挑，
# 否则会把从没错过的题也拉进错题本，破坏演示口径。
WRONG_POOL = ["q_ch2_03", "q_ch6_03", "q_ch4_01", "q_ch2_02", "q_ch6_04"]


def history_id(user_key: str, days_ago: int, index: int) -> str:
    return f"hist-{BATCH}-{user_key}-{days_ago}-{index}"[:36]


async def main(dry_run: bool, reset: bool = False) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with SessionFactory() as session:
        if reset:
            result = await session.execute(
                delete(Attempt).where(Attempt.id.like(f"hist-{BATCH}-%"))
            )
            print(f"{'DRY-RUN ' if dry_run else ''}reset removed={result.rowcount}")
        questions = (
            await session.execute(
                select(Question).where(Question.course_id == COURSE_ID).order_by(Question.sort_order, Question.id)
            )
        ).scalars().all()
        if not questions:
            raise SystemExit("题库为空，先跑 seed 再补历史")

        wrong_questions = [item for item in questions if item.id in WRONG_POOL] or questions

        created = skipped = 0
        for user_key, days in PLAN.items():
            for days_ago, count, correct in days:
                start = (days_ago * 7 + len(user_key)) % len(questions)
                picked = []
                for step in range(count):
                    if step < correct:
                        picked.append(questions[(start + step) % len(questions)])
                    else:
                        picked.append(wrong_questions[(start + step) % len(wrong_questions)])
                created_at = now - timedelta(days=days_ago)
                for index, question in enumerate(picked):
                    attempt_id = history_id(user_key, days_ago, index)
                    exists = await session.get(Attempt, attempt_id)
                    if exists:
                        skipped += 1
                        continue
                    is_correct = index < correct
                    session.add(
                        Attempt(
                            id=attempt_id,
                            course_id=COURSE_ID,
                            question_id=question.id,
                            user_key=user_key,
                            chapter_id=question.chapter_id,
                            answer=question.answer if is_correct else "X",
                            is_correct=is_correct,
                            created_at=created_at.replace(hour=9 + index, minute=12),
                        )
                    )
                    created += 1
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
        print(f"{'DRY-RUN ' if dry_run else ''}created={created} skipped={skipped}")
    await engine.dispose()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="先删掉本期（hist-w13）历史再重写")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run, args.reset))
