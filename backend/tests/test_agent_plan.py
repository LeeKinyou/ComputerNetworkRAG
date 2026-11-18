from app.agent import _plan


def keys(steps: list[dict]) -> list[str]:
    return [step["key"] for step in steps]


def test_rag_plan_skips_tools_and_approval():
    steps = _plan("计算 10.0.0.0/26 的网络地址", False, "rag")
    assert keys(steps) == ["understand", "retrieve", "compose"]


def test_agent_plan_adds_calculate_for_subnet_question():
    steps = _plan("计算 10.0.0.0/26 的网络地址", False, "agent")
    assert "calculate" in keys(steps)
    assert "approval" not in keys(steps)
    assert keys(steps)[-1] == "compose"


def test_agent_plan_adds_approval_for_write_intent():
    steps = _plan("重建第 4 章索引，把新文档一起入库", True, "agent")
    assert keys(steps) == ["understand", "retrieve", "approval", "compose"]


def test_agent_plan_can_hold_both_calculate_and_approval():
    steps = _plan("重建索引后计算 10.0.0.0/26", True, "agent")
    assert keys(steps) == ["understand", "retrieve", "calculate", "approval", "compose"]


def test_rag_plan_never_requests_approval():
    steps = _plan("重建第 4 章索引", True, "rag")
    assert "approval" not in keys(steps)
