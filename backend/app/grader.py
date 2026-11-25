"""作业批改：模型按评分要点结构化给分，失败时用规则兜底。

设计取舍：
- `rule_grade` 是纯函数，不碰网络与数据库，单测直接覆盖；
- `grade_item` 一次只批一题，并发与超时由调用方（API）控制；
- 模型给的每题分数一律按评分要点上限截断，避免要点分和题分对不上。
"""

from __future__ import annotations

import base64
import json
import math
import mimetypes
import re
from pathlib import Path
from typing import Any

from app.config import settings

MAX_FEEDBACK = 80
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
PUNCT_RE = re.compile(r"[，。、；：？！（）()《》「」【】\s,.;:!?\"'`]")

# 规则兜底用的停用词：只保留能区分答案对错的实词
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "are", "was", "has", "have",
    "是", "的", "了", "和", "与", "及", "或", "在", "对", "从", "把", "被",
    "一个", "一种", "进行", "可以", "能够", "需要", "通过", "以及", "不是",
}


def _rubric_points(item: dict) -> list[dict]:
    """取出评分要点；没有要点时整题算一个要点，避免除零与空批改。"""
    rubric = item.get("rubric") or []
    points = [
        {"text": str(entry.get("text", "")).strip(), "score": max(0, int(entry.get("score", 0)))}
        for entry in rubric
        if isinstance(entry, dict) and str(entry.get("text", "")).strip()
    ]
    if points:
        return points
    total = max(1, int(item.get("score") or 10))
    return [{"text": (item.get("reference") or item.get("stem") or "完整作答").strip(), "score": total}]


def _keywords(text: str) -> list[str]:
    """中文按停用词切开后取 2~4 字片段，英文按单词；不引入分词依赖。"""
    cleaned = PUNCT_RE.sub(" ", text).strip()
    raw: list[str] = []
    for chunk in cleaned.split():
        if re.fullmatch(r"[A-Za-z0-9.\-/]+", chunk):
            raw.append(chunk.lower())
            continue
        # 中文片段：按标点已切开，再按助词切，最后滑窗取 2~4 字
        for piece in re.split(r"[的了和与及或在把被]", chunk):
            piece = piece.strip()
            if not piece:
                continue
            if len(piece) <= 4:
                raw.append(piece)
            else:
                raw.extend(piece[i : i + 2] for i in range(0, len(piece) - 1))
    return [token for token in raw if token and token not in STOPWORDS]


def _coverage(point: str, answer: str) -> float:
    keys = _keywords(point)
    if not keys:
        return 0.0
    lowered = answer.lower()
    hits = sum(1 for token in keys if token in lowered)
    return hits / len(keys)


def _numbers_ok(point: str, answer: str) -> bool:
    """要点里出现数值时，答案必须给出同一个数（按 float 比较，容忍 30 与 30.0）。"""
    expected = [float(value) for value in NUMBER_RE.findall(point)]
    if not expected:
        return True
    given = [float(value) for value in NUMBER_RE.findall(answer)]
    return all(any(math.isclose(item, value, rel_tol=1e-6) for value in given) for item in expected)


def rule_grade(item: dict, answer: str) -> dict:
    """规则兜底：要点覆盖率 + 数值校验，给出可解释的部分分。"""
    answer = (answer or "").strip()
    max_score = max(1, int(item.get("score") or 10))
    points: list[dict] = []
    for ref in _rubric_points(item):
        ratio = _coverage(ref["text"], answer) if answer else 0.0
        numbers_ok = _numbers_ok(ref["text"], answer)
        if not answer or not numbers_ok or ratio < 0.3:
            hit, score = False, 0
        elif ratio >= 0.6:
            hit, score = True, ref["score"]
        else:
            # 命中一半关键词给一半分，向下取整；仍标点未完全命中
            hit, score = False, math.floor(ref["score"] / 2)
        points.append({"point": ref["text"], "hit": hit, "partial": bool(score and not hit), "score": score})

    score = min(max_score, sum(point["score"] for point in points))
    missing = [point["point"] for point in points if not point["hit"]]
    if not answer:
        feedback = "未作答。"
    elif missing:
        clipped = "、".join(missing)[:40]
        feedback = f"命中 {sum(1 for p in points if p['hit'])}/{len(points)} 个要点，缺少：{clipped}（机器初评）"
    else:
        feedback = "要点齐全（机器初评）"
    return {
        "score": score,
        "max_score": max_score,
        "verdict": _verdict(score, max_score),
        "points": points,
        "feedback": feedback[:MAX_FEEDBACK],
        "source": "rule",
        "needs_review": True,
        "confidence": 0.35,
    }


def _verdict(score: int, max_score: int) -> str:
    if score >= max_score:
        return "correct"
    if score <= 0:
        return "wrong"
    return "partial"


PROMPT_TEMPLATE = """你在批改《计算机网络》课程作业，按评分要点给分，允许部分得分。

题目（{kind}，满分 {score} 分）：{stem}
参考答案：{reference}
评分要点：
{rubric}

学生作答：
{answer}

要求：
1. 每题得分等于命中要点的分值之和，不得超过满分；
2. 计算题若最终数值错误但过程要点正确，只给过程分；
3. feedback 用中文，不超过 60 字，直接指出缺什么；
4. 只输出 JSON，不要代码块、不要任何解释。

JSON 结构：
{{"score": 数字, "max_score": 数字, "verdict": "correct|partial|wrong",
 "points": [{{"point": "要点原文", "hit": true/false, "score": 数字}}],
 "feedback": "评语", "confidence": 0~1 的小数}}"""


def build_prompt(item: dict, answer: str, has_image: bool = False) -> str:
    rubric = "\n".join(f"- {p['text']}（{p['score']} 分）" for p in _rubric_points(item))
    prompt = PROMPT_TEMPLATE.format(
        kind="计算题" if item.get("type") == "calc" else "简答题",
        score=int(item.get("score") or 10),
        stem=item.get("stem", ""),
        reference=item.get("reference", ""),
        rubric=rubric,
        answer=answer or "（空）",
    )
    if has_image:
        prompt += "\n\n补充说明：学生作答以照片形式提交，请先识别图片中的手写文字与演算过程，再按评分要点给分。"
    return prompt


def parse_payload(raw: str) -> dict[str, Any]:
    """从模型输出里取第一个 JSON 对象；允许 ```json 包裹。"""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no json object in grader output")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("grader output is not an object")
    return payload


def normalize(payload: dict, item: dict, source: str = "llm") -> dict:
    """把模型结果对齐到本地评分要点：分数以要点上限为准，verdict 由分数推导。"""
    rubric = _rubric_points(item)
    max_score = max(1, int(item.get("score") or sum(p["score"] for p in rubric)))
    raw_points = payload.get("points") if isinstance(payload.get("points"), list) else []

    points: list[dict] = []
    for index, ref in enumerate(rubric):
        raw = raw_points[index] if index < len(raw_points) and isinstance(raw_points[index], dict) else {}
        hit = bool(raw.get("hit"))
        score = ref["score"] if hit else 0
        points.append(
            {
                "point": ref["text"],
                "hit": hit,
                "score": min(ref["score"], score),
                "reason": str(raw.get("reason") or "")[:60],
            }
        )

    score = min(max_score, sum(point["score"] for point in points))
    feedback = str(payload.get("feedback") or "").strip()
    if not feedback:
        missing = [point["point"] for point in points if not point["hit"]]
        feedback = "要点齐全" if not missing else f"缺少：{'、'.join(missing)[:50]}"
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    return {
        "score": score,
        "max_score": max_score,
        "verdict": _verdict(score, max_score),
        "points": points,
        "feedback": feedback[:MAX_FEEDBACK],
        "source": source,
        "needs_review": confidence < 0.5,
        "confidence": round(confidence, 2),
    }


async def _call_llm(prompt: str) -> str:
    """与问答共用一套 LLM 配置；单测通过 monkeypatch 覆盖。"""
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        timeout=45,
    )
    result = await model.ainvoke(prompt)
    return str(result.content)


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


async def _call_vision(prompt: str, image_paths: list[Path]) -> str:
    """图片走独立多模态端点；只取前三张，避免单题请求体过大。"""
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=settings.llm_vision_model,
        api_key=settings.llm_vision_api_key or settings.llm_api_key,
        base_url=settings.llm_vision_base_url or settings.llm_base_url,
        temperature=0,
        timeout=60,
    )
    content: list[dict] = [{"type": "text", "text": prompt}]
    for path in image_paths[:3]:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(path)}})
    result = await model.ainvoke([HumanMessage(content=content)])
    return str(result.content)


def pending_result(item: dict) -> dict:
    """只有照片又没有多模态端点时不硬判 0 分，标记待复核，避免误伤学生。"""
    max_score = max(1, int(item.get("score") or 10))
    return {
        "score": 0,
        "max_score": max_score,
        "verdict": "wrong",
        "points": [],
        "feedback": "已收到作答照片，当前未配置图片识别模型，待教师复核",
        "source": "pending",
        "needs_review": True,
        "confidence": 0.0,
    }


async def grade_item(item: dict, answer: str, image_paths: list[Path] | None = None) -> dict:
    """批一题：模型优先，两次解析失败或异常一律退回规则。"""
    answer = (answer or "").strip()
    images = image_paths or []
    if images and not settings.vision_ready and not answer:
        return pending_result(item)
    if not settings.llm_ready:
        return rule_grade(item, answer)

    prompt = build_prompt(item, answer, has_image=bool(images))
    last_error = ""
    for attempt in range(2):
        try:
            if images:
                raw = await _call_vision(prompt, images)
            else:
                raw = await _call_llm(prompt if attempt == 0 else prompt + "\n\n再次强调：只输出 JSON。")
            return normalize(parse_payload(raw), item, source="vision" if images else "llm")
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"[:120]

    result = rule_grade(item, answer)
    result["fallback"] = True
    result["error"] = last_error
    return result
