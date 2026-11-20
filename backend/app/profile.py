"""学习画像：把练习作答聚合成概念级掌握度，供问答注入与检索加权。

设计取舍：
- 纯函数 `summarize_concepts` / `build_profile_payload` 不碰数据库，便于单测；
- `build_profile` 只负责一次查询，不缓存：演示数据量小，实时反映最近作答；
- 画像只描述“该补什么”，不把统计数字读给模型听，避免回答变成成绩单。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attempt, Concept, Question
from app.seed import COURSE_ID

WEAK_THRESHOLD = 60
MASTERED_THRESHOLD = 80
MAX_WEAK = 4
MAX_UNTRIED = 5
MAX_STRONG = 3


def summarize_concepts(
    concepts: list[dict],
    question_concepts: dict[str, str],
    attempts: list[dict],
) -> list[dict]:
    """按 concept 聚合作答。入参都是普通 dict，方便测试与复用。"""
    buckets: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        concept_id = question_concepts.get(attempt["question_id"])
        if not concept_id:
            continue
        bucket = buckets.setdefault(concept_id, {"total": 0, "correct": 0})
        bucket["total"] += 1
        if attempt.get("is_correct"):
            bucket["correct"] += 1

    items: list[dict] = []
    for concept in concepts:
        bucket = buckets.get(concept["id"], {"total": 0, "correct": 0})
        total = bucket["total"]
        correct = bucket["correct"]
        rate = round(correct / total * 100) if total else 0
        if not total:
            state = "no_data"
        elif rate < WEAK_THRESHOLD:
            state = "weak"
        elif rate < MASTERED_THRESHOLD:
            state = "normal"
        else:
            state = "mastered"
        items.append(
            {
                "concept_id": concept["id"],
                "title": concept["title"],
                "chapter_id": concept.get("chapter_id"),
                "attempts": total,
                "correct": correct,
                "rate": rate,
                "state": state,
            }
        )
    return items


def build_profile_payload(items: list[dict], user_key: str, course_id: str = COURSE_ID) -> dict:
    """把概念明细压成问答/检索需要的画像字段。"""
    total = sum(item["attempts"] for item in items)
    correct = sum(item["correct"] for item in items)
    accuracy = round(correct / total * 100) if total else 0
    covered = sum(1 for item in items if item["attempts"])
    weak = sorted(
        (item for item in items if item["state"] == "weak"),
        key=lambda item: (item["rate"], -item["attempts"]),
    )[:MAX_WEAK]
    untried = [item for item in items if not item["attempts"]][:MAX_UNTRIED]
    strong = [item for item in items if item["state"] == "mastered"][:MAX_STRONG]
    weak_chapters = sorted(
        {item["chapter_id"] for item in weak + untried if item.get("chapter_id")}
    )
    return {
        "user_key": user_key,
        "course_id": course_id,
        "concepts": items,
        "attempts": total,
        "correct": correct,
        "accuracy": accuracy,
        "covered": covered,
        "weak": weak,
        "untried": untried,
        "strong": strong,
        "weak_chapters": weak_chapters,
    }


def profile_prompt(profile: dict | None) -> str:
    """生成注入 system prompt 的片段；没有作答记录时返回空串。"""
    if not profile or not profile.get("attempts"):
        return ""

    def label(item: dict, with_rate: bool = True) -> str:
        if with_rate:
            return f"{item['title']}（{item['rate']}%，{item['attempts']} 题）"
        return item["title"]

    lines = ["学生近期练习画像（只用于调整讲解深浅，不要在回答里罗列这些统计）："]
    if profile.get("weak"):
        lines.append("- 薄弱：" + "、".join(label(item) for item in profile["weak"]))
    if profile.get("untried"):
        lines.append("- 还没练过：" + "、".join(label(item, with_rate=False) for item in profile["untried"]))
    if profile.get("strong"):
        lines.append("- 已掌握：" + "、".join(label(item, with_rate=False) for item in profile["strong"]))
    lines.append(
        "要求：问题涉及薄弱或未练概念时，先用一句话补基础直觉再给结论；"
        "已掌握的概念可以略过基础铺垫，直接讲重点。"
    )
    return "\n".join(lines)


async def build_profile(
    session: AsyncSession,
    user_key: str = "demo_user",
    course_id: str = COURSE_ID,
) -> dict:
    """查询并聚合该学生最近的全部作答。"""
    concepts = (
        await session.execute(select(Concept).where(Concept.course_id == course_id))
    ).scalars().all()
    questions = (
        await session.execute(select(Question).where(Question.course_id == course_id))
    ).scalars().all()
    attempts = (
        await session.execute(
            select(Attempt).where(Attempt.course_id == course_id, Attempt.user_key == user_key)
        )
    ).scalars().all()

    question_concepts = {question.id: question.concept_id for question in questions if question.concept_id}
    concept_rows = [
        {"id": concept.id, "title": concept.title, "chapter_id": concept.chapter_id}
        for concept in concepts
    ]
    attempt_rows = [
        {"question_id": attempt.question_id, "is_correct": bool(attempt.is_correct)}
        for attempt in attempts
    ]
    items = summarize_concepts(concept_rows, question_concepts, attempt_rows)
    return build_profile_payload(items, user_key, course_id)
