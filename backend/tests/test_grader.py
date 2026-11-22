"""批改服务契约：规则兜底、模型结果归一化、模型异常降级。"""

from __future__ import annotations

import pytest

from app import grader
from app.config import settings

SHORT_ITEM = {
    "type": "short",
    "stem": "TCP 三次握手中，第三次 ACK 的作用是什么？",
    "reference": "客户端确认收到 SYN+ACK，证明客户端接收与服务端发送通道可用；同步序号，避免历史重复连接被误接受。",
    "rubric": [
        {"text": "确认客户端接收能力与服务端发送通道", "score": 4},
        {"text": "同步并确认序号", "score": 3},
        {"text": "避免历史重复连接被误接受", "score": 3},
    ],
    "score": 10,
}

CALC_ITEM = {
    "type": "calc",
    "stem": "192.168.10.0/27 的网络地址和可用主机数？",
    "reference": "块大小 32，网络地址 192.168.10.0，广播 192.168.10.31，可用主机 30 个。",
    "rubric": [
        {"text": "网络地址 192.168.10.0", "score": 4},
        {"text": "可用主机 30 个", "score": 4},
        {"text": "块大小 32，去掉网络与广播地址", "score": 2},
    ],
    "score": 10,
}

GOOD_SHORT = "客户端确认收到了服务端的 SYN+ACK，证明客户端接收与服务端发送通道可用；同时同步并确认序号，避免历史重复连接被误接受。"
GOOD_CALC = "/27 的块大小是 32，所以网络地址是 192.168.10.0，广播地址 192.168.10.31，去掉这两个可用主机是 30 个。"


def test_rule_full_marks_on_complete_answer():
    result = grader.rule_grade(SHORT_ITEM, GOOD_SHORT)
    assert result["score"] == 10
    assert result["verdict"] == "correct"
    assert result["source"] == "rule"
    assert result["needs_review"] is True


def test_rule_zero_on_empty_answer():
    result = grader.rule_grade(SHORT_ITEM, "")
    assert result["score"] == 0
    assert result["verdict"] == "wrong"
    assert "未作答" in result["feedback"]


def test_rule_numbers_must_match_for_calc():
    result = grader.rule_grade(CALC_ITEM, "网络地址 192.168.10.32，可用主机 32 个。")
    assert result["score"] <= 2
    assert result["verdict"] != "correct"


def test_rule_calc_full_marks():
    result = grader.rule_grade(CALC_ITEM, GOOD_CALC)
    assert result["score"] == 10


def test_rule_never_exceeds_max_score():
    item = dict(SHORT_ITEM, rubric=[{"text": "确认接收", "score": 6}, {"text": "同步序号", "score": 6}], score=10)
    result = grader.rule_grade(item, "确认接收 同步序号")
    assert result["score"] <= 10


def test_parse_payload_accepts_code_fence_and_noise():
    raw = '好的，结果如下：\n```json\n{"score": 4, "points": []}\n```'
    assert grader.parse_payload(raw)["score"] == 4


def test_parse_payload_rejects_non_json():
    with pytest.raises(ValueError):
        grader.parse_payload("我觉得答得还行")


def test_normalize_clips_to_rubric_and_derives_verdict():
    payload = {
        "score": 99,
        "max_score": 99,
        "verdict": "correct",
        "points": [
            {"point": "确认接收", "hit": True, "score": 99},
            {"point": "同步序号", "hit": False},
            {"point": "避免旧连接", "hit": True},
        ],
        "feedback": "还行",
        "confidence": 1.4,
    }
    result = grader.normalize(payload, SHORT_ITEM)
    assert result["score"] == 7  # 4 + 0 + 3，且不超过 10
    assert result["verdict"] == "partial"
    assert result["confidence"] == 1.0
    assert result["source"] == "llm"


async def test_grade_item_uses_model_when_json_is_valid(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    async def fake_call(prompt: str) -> str:
        return (
            '{"score": 4, "points": [{"point": "确认接收", "hit": true},'
            ' {"point": "同步序号", "hit": false}, {"point": "避免旧连接", "hit": false}],'
            ' "feedback": "只答了确认作用", "confidence": 0.8}'
        )

    monkeypatch.setattr(grader, "_call_llm", fake_call)
    result = await grader.grade_item(SHORT_ITEM, "客户端确认收到了")
    assert result["source"] == "llm"
    assert result["score"] == 4
    assert result["verdict"] == "partial"
    assert result["needs_review"] is False


async def test_grade_item_falls_back_on_broken_output(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    async def fake_call(prompt: str) -> str:
        return "这道题答得不错"

    monkeypatch.setattr(grader, "_call_llm", fake_call)
    result = await grader.grade_item(CALC_ITEM, GOOD_CALC)
    assert result["source"] == "rule"
    assert result["fallback"] is True
    assert result["score"] == 10


async def test_grade_item_falls_back_when_model_raises(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "test-key")

    async def boom(prompt: str) -> str:
        raise RuntimeError("upstream 502")

    monkeypatch.setattr(grader, "_call_llm", boom)
    result = await grader.grade_item(SHORT_ITEM, GOOD_SHORT)
    assert result["source"] == "rule"
    assert result["fallback"] is True
