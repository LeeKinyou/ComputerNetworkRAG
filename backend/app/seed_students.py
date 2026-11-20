"""给演示灌入两名示例学生的作答，让教师端的「全班」视图有对比。

幂等：按 (user_key, question_id) 判断，已存在的跳过，可重复执行。
只写 attempts，不改题库、不改运行记录；要撤销就按 user_key 删这两行。

用法：
    cd backend
    .venv\\Scripts\\python.exe -m app.seed_students
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import SessionFactory, init_db
from app.models import Attempt, Question
from app.seed import COURSE_ID

# 每个概念取前 3 题；correct 表示其中答对几道
PLANS: dict[str, tuple[list[str], int]] = {
    # 林晓：基础偏弱，六个概念都是 33%，教师端会看到明显的短板
    "stu_lin": (["arp", "handshake", "csma", "udp", "cidr", "tls"], 1),
    # 赵一鸣：基础较好，同六个概念全对
    "stu_zhao": (["arp", "handshake", "csma", "udp", "cidr", "tls"], 3),
}


def _wrong_answer(question: Question) -> str:
    """挑一个与正确答案不同的选项 key，仅用于让历史记录看起来像真的作答。"""
    correct = str(question.answer or "").strip().upper()
    for option in question.options or []:
        key = str(option.get("key", "")).strip().upper()
        if key and key != correct:
            return key
    return ""


async def main() -> None:
    await init_db()
    async with SessionFactory() as session:
        questions = (
            await session.execute(select(Question).where(Question.course_id == COURSE_ID))
        ).scalars().all()
        by_concept: dict[str, list[Question]] = {}
        for question in questions:
            if question.concept_id:
                by_concept.setdefault(question.concept_id, []).append(question)

        taken = {
            (row[0], row[1])
            for row in (await session.execute(select(Attempt.user_key, Attempt.question_id))).all()
        }

        added = 0
        for user_key, (concepts, correct_count) in PLANS.items():
            for concept_id in concepts:
                picked = by_concept.get(concept_id, [])[:3]
                for offset, question in enumerate(picked):
                    if (user_key, question.id) in taken:
                        continue
                    is_correct = offset < correct_count
                    session.add(
                        Attempt(
                            course_id=COURSE_ID,
                            question_id=question.id,
                            user_key=user_key,
                            chapter_id=question.chapter_id,
                            answer=question.answer if is_correct else _wrong_answer(question),
                            is_correct=is_correct,
                        )
                    )
                    added += 1
        await session.commit()

    print(f"seeded {added} attempts for {', '.join(PLANS)}")


if __name__ == "__main__":
    asyncio.run(main())
