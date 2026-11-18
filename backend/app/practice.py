"""练习批改：单选与判断的答案归一化、判分与作答摘要。不依赖模型与网络。"""

from __future__ import annotations

TRUE_TOKENS = {"T", "TRUE", "Y", "YES", "对", "正确", "是"}
FALSE_TOKENS = {"F", "FALSE", "N", "NO", "错", "错误", "否"}
CHOICE_KEYS = {"A", "B", "C", "D"}


def normalize_answer(raw: str | None) -> str:
    """把前端/人工输入归一化成 A/B/C/D 或 T/F。"""
    value = (raw or "").strip().upper()
    if not value:
        return ""
    if value in TRUE_TOKENS:
        return "T"
    if value in FALSE_TOKENS:
        return "F"
    head = value[0]
    if head in CHOICE_KEYS:
        return head
    return value


def is_correct(given: str | None, expected: str) -> bool:
    """空作答一律判错；其余按归一化后的答案比较。"""
    normalized = normalize_answer(given)
    if not normalized:
        return False
    return normalized == normalize_answer(expected)


def answer_summary(question_type: str, given: str | None, expected: str) -> dict:
    """返回批改结果，供接口直接拼装响应。"""
    correct = is_correct(given, expected)
    return {
        "type": question_type,
        "answer": normalize_answer(given),
        "expected": normalize_answer(expected),
        "correct": correct,
    }
