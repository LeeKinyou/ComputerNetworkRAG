"""作业题目文件解析：P0 只支持纯文本（.md / .txt）的固定格式。

格式约定（面向教师，宁可严格也不猜）：

    # 作业标题
    ### 题目 1 | 简答 | 10 分
    题干……
    参考答案: ……
    评分要点: 要点A=4; 要点B=3; 要点C=3

解析失败时抛 `ImportError`，带行号与原因；能解析但分值对不上时，均分并给 warning。
"""

from __future__ import annotations

import re

TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")
ITEM_RE = re.compile(
    r"^###\s*题目\s*(\d+)\s*[|｜]\s*(简答|计算|short|calc)\s*[|｜]\s*(\d+)\s*分\s*$",
    re.IGNORECASE,
)
REF_RE = re.compile(r"^\s*参考答案\s*[:：]\s*(.*)$")
RUBRIC_RE = re.compile(r"^\s*评分要点\s*[:：]\s*(.*)$")
RUBRIC_ENTRY_RE = re.compile(r"(.+?)\s*[=＝:：]\s*(\d+)\s*分?\s*$")

TYPE_MAP = {"简答": "short", "short": "short", "计算": "calc", "calc": "calc"}


class AssignmentImportError(Exception):
    """解析失败：line=0 表示文件级错误。"""

    def __init__(self, line: int, message: str):
        super().__init__(message)
        self.line = line
        self.message = message


def _split_rubric(text: str) -> list[dict]:
    entries: list[dict] = []
    for chunk in re.split(r"[;；\n]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = RUBRIC_ENTRY_RE.match(chunk)
        if match:
            entries.append({"text": match.group(1).strip(), "score": int(match.group(2))})
        else:
            entries.append({"text": chunk, "score": 0})
    return entries


def _rebalance_rubric(entries: list[dict], total: int, line: int, warnings: list[dict]) -> list[dict]:
    """把要点分值校准到题目总分：能解析的保留，其余均分。"""
    if not entries:
        warnings.append({"line": line, "message": "缺少评分要点，已按总分均分"})
        return [{"text": "完整作答", "score": total}]

    current = sum(entry["score"] for entry in entries)
    if current == total and all(entry["score"] > 0 for entry in entries):
        return entries

    warnings.append({"line": line, "message": f"评分要点合计 {current} 分与题目 {total} 分不一致，已均分"})
    base = total // len(entries)
    result = []
    for index, entry in enumerate(entries):
        score = total - base * (len(entries) - 1) if index == len(entries) - 1 else base
        result.append({"text": entry["text"], "score": max(1, score)})
    return result


def parse_assignment_text(text: str) -> dict:
    """返回 {title, items, warnings}；items 结构与 AssignmentItem 字段对齐。"""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    title = ""
    items: list[dict] = []
    warnings: list[dict] = []

    current: dict | None = None
    mode: str | None = None  # stem / reference / rubric
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, mode, buffer
        if current is None:
            return
        stem = "\n".join(current.pop("stem_lines")).strip()
        reference = "\n".join(current.pop("reference_lines")).strip()
        rubric_text = " ".join(current.pop("rubric_lines")).strip()
        if not stem:
            raise AssignmentImportError(current["line"], f"第 {current['ordinal']} 题缺少题干")

        rubric = _rebalance_rubric(_split_rubric(rubric_text), current["score"], current["line"], warnings)
        items.append(
            {
                "ordinal": current["ordinal"],
                "type": current["type"],
                "stem": stem,
                "reference": reference,
                "rubric": rubric,
                "score": current["score"],
                "concept_id": current.get("concept_id"),
                "difficulty": "medium",
            }
        )
        current = None
        mode = None
        buffer = []

    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        if not line.strip():
            if mode in ("reference", "rubric"):
                buffer.append("")
            continue

        title_match = TITLE_RE.match(line)
        if title_match and not title:
            title = title_match.group(1).strip()
            continue

        item_match = ITEM_RE.match(line)
        if item_match:
            flush()
            current = {
                "line": number,
                "ordinal": int(item_match.group(1)),
                "type": TYPE_MAP[item_match.group(2).lower()],
                "score": int(item_match.group(3)),
                "stem_lines": [],
                "reference_lines": [],
                "rubric_lines": [],
            }
            mode = "stem"
            continue

        if current is None:
            # 题目块之外的散行忽略（允许说明性前言），但保留标题解析
            continue

        if REF_RE.match(line):
            mode = "reference"
            buffer = [REF_RE.match(line).group(1)]
            current["reference_lines"] = buffer
            continue
        if RUBRIC_RE.match(line):
            mode = "rubric"
            buffer = [RUBRIC_RE.match(line).group(1)]
            current["rubric_lines"] = buffer
            continue

        if mode == "stem":
            current["stem_lines"].append(line)
        elif mode == "reference":
            current["reference_lines"].append(line)
        elif mode == "rubric":
            current["rubric_lines"].append(line)

    flush()

    if not items:
        raise AssignmentImportError(0, "未找到题目，需要形如 `### 题目 1 | 简答 | 10 分` 的题目行")
    if not title:
        title = "未命名作业"
        warnings.append({"line": 0, "message": "未找到一级标题，已命名「未命名作业」"})
    return {"title": title, "items": items, "warnings": warnings}
