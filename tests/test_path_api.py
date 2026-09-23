"""学习路径只读接口（09 号文档 Task 5.6）：GET /api/path 与 GET /api/path/plan。

要锁住的点：
1. 边不悬空——limit 截断节点后必须同时裁掉两端不在节点集里的边，否则 ECharts 直接报错；
2. 触达口径——节点的 touch_count 来自 knowledge_touch.kp_id，kp_id 是名字散列，重建不变；
3. plan 的排序——主键章号、次键拓扑层，验收标准是"结果章号单调不减"，
   LLM 抽错边也不能把第 8 章排到第 2 章前面；
4. plan 不吊死——prereq_edge 允许人工改，万一出现环，闭包内节点仍要全部输出。
"""

import httpx
import pytest

from app.schemas import KnowledgeNode, PrereqEdge, TouchRecord
from app.services import path_service
from app.storage.sqlite_repo import SqliteRepository, get_repo, init_repo

PATH_FIELDS = {"nodes", "edges", "chapters", "truncated"}
PLAN_FIELDS = {"target", "steps", "no_prereq"}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


@pytest.fixture
async def repo(db_path):
    r = SqliteRepository(db_path)
    await r.init()
    yield r
    await r.close()


def _kn(name: str, chapter: int | None, degree: int = 0) -> KnowledgeNode:
    return KnowledgeNode(
        kp_id=path_service.kp_id_for(name), name=name, entity_type="概念",
        chapter=chapter, description=f"{name}的描述", degree=degree, built_at="2026-09-23T00:00:00",
    )


def _pe(source: str, target: str, chapter: int, reason: str = "", confidence: float = 0.9) -> PrereqEdge:
    return PrereqEdge(
        source=path_service.kp_id_for(source), target=path_service.kp_id_for(target),
        chapter=chapter, reason=reason, confidence=confidence,
    )


async def seed(repo, nodes, edges, touches=()):
    await repo.upsert_knowledge_nodes(nodes)
    for chapter in {e.chapter for e in edges}:
        await repo.replace_prereq_edges(chapter, [e for e in edges if e.chapter == chapter])
    for name in touches:
        await repo.add_touches([TouchRecord(
            kp_name=name, kp_id=path_service.kp_id_for(name),
            session_id="s1", run_id="r1", via="rag_hit",
        )])


# ----- /api/path -----

async def test_path_shape_and_chapter_filter(repo):
    await seed(
        repo,
        [_kn("IP地址", 3, 9), _kn("子网划分", 3, 5), _kn("虚电路", 4, 7), _kn("游离实体", None, 3)],
        [_pe("IP地址", "子网划分", 3, "先会地址结构才能划子网")],
    )
    data = await path_service.get_path(repo, chapter=3)
    assert set(data) == PATH_FIELDS
    assert [n["name"] for n in data["nodes"]] == ["IP地址", "子网划分"]      # 度数降序
    assert set(data["nodes"][0]) == {
        "kp_id", "name", "type", "chapter", "degree", "description", "layer", "touch_count",
    }
    assert data["truncated"] is False
    # 未归章实体不参与路径
    assert "游离实体" not in [n["name"] for n in (await path_service.get_path(repo))["nodes"]]


async def test_path_chapters_list_only_real_ones(repo):
    await seed(repo, [_kn("A", 2), _kn("B", 5), _kn("C", None)], [])
    data = await path_service.get_path(repo)
    assert data["chapters"] == [2, 5]          # 第 7/9 章没有实体，就不该出现在下拉里


async def test_path_edges_never_dangle_after_limit(repo):
    nodes = [_kn(f"n{i}", 4, 100 - i) for i in range(6)]
    edges = [_pe("n0", "n1", 4), _pe("n1", "n2", 4), _pe("n4", "n5", 4), _pe("n5", "n0", 4)]
    await seed(repo, nodes, edges)
    data = await path_service.get_path(repo, chapter=4, limit=3)
    kept = {n["kp_id"] for n in data["nodes"]}
    assert kept == {path_service.kp_id_for(n) for n in ("n0", "n1", "n2")}
    assert data["truncated"] is True
    assert {(e["source"], e["target"]) for e in data["edges"]} == {
        (path_service.kp_id_for("n0"), path_service.kp_id_for("n1")),
        (path_service.kp_id_for("n1"), path_service.kp_id_for("n2")),
    }
    for e in data["edges"]:
        assert e["source"] in kept and e["target"] in kept


async def test_path_layers_for_manual_coordinates(repo):
    """前端按 x = layer × 180 手工排版，层号必须由后端算好，别在 JS 里再实现一遍。"""
    await seed(
        repo,
        [_kn("IP", 3, 9), _kn("TCP", 3, 8), _kn("HTTP", 3, 7), _kn("VLAN", 3, 6)],
        [_pe("IP", "TCP", 3), _pe("TCP", "HTTP", 3), _pe("HTTP", "IP", 3)],
    )
    data = await path_service.get_path(repo, chapter=3)
    layers = {n["name"]: n["layer"] for n in data["nodes"]}
    assert layers["VLAN"] == 0
    assert len(layers) == 4      # 人工改出的环也要每个节点都有层号，不能漏


async def test_path_touch_count(repo):
    await seed(repo, [_kn("TCP", 6, 8)], [], touches=["TCP", "TCP", "不在快照里"])
    data = await path_service.get_path(repo, chapter=6)
    assert data["nodes"][0]["touch_count"] == 2


async def test_path_empty_db_returns_empty_structure(repo):
    data = await path_service.get_path(repo, chapter=4)
    assert data == {"nodes": [], "edges": [], "chapters": [], "truncated": False}


# ----- /api/path/plan -----

async def test_plan_reverse_closure_only_prereqs(repo):
    """只取前驱闭包：目标的下游（依赖它的知识点）不该混进必修链。"""
    await seed(
        repo,
        [_kn("应用层", 8), _kn("HTTP", 7), _kn("TCP", 6), _kn("IP", 3), _kn("UDP", 8)],
        [
            _pe("IP", "TCP", 3, "传输层建立在网络层之上"),
            _pe("TCP", "HTTP", 6, "HTTP 用 TCP 传报文"),
            _pe("HTTP", "应用层", 7, "下游：应用层协议建立在 HTTP 之上"),
            _pe("HTTP", "UDP", 7, "下游：另一条不相关的下游分支"),
        ],
    )
    plan = await path_service.plan(repo, path_service.kp_id_for("HTTP"))
    assert set(plan) == PLAN_FIELDS
    names = [s["name"] for s in plan["steps"]]
    assert names == ["IP", "TCP", "HTTP"]
    assert plan["steps"][-1]["kp_id"] == path_service.kp_id_for("HTTP")
    assert plan["no_prereq"] is False
    assert set(plan["steps"][0]) == {
        "kp_id", "name", "type", "chapter", "degree", "reason", "touch_count",
    }


async def test_plan_chapters_monotonic(repo):
    """验收标准：任选一节点，plan 结果章号单调不减。"""
    await seed(
        repo,
        [_kn(name, chapter) for name, chapter in (
            ("物理层", 1), ("CSMA/CD", 3), ("IP", 3), ("ARP", 3),
            ("TCP", 4), ("拥塞控制", 4), ("HTTP", 6),
        )],
        [
            _pe("物理层", "CSMA/CD", 1),
            _pe("CSMA/CD", "IP", 3),
            _pe("ARP", "IP", 3),
            _pe("IP", "TCP", 3),
            _pe("TCP", "拥塞控制", 4),
            _pe("拥塞控制", "HTTP", 6),
            _pe("物理层", "HTTP", 1),
        ],
    )
    for name in ("HTTP", "TCP", "IP", "拥塞控制", "ARP"):
        plan = await path_service.plan(repo, path_service.kp_id_for(name))
        chapters = [s["chapter"] for s in plan["steps"]]
        assert chapters == sorted(chapters), (name, chapters)
        assert plan["steps"][-1]["name"] == name


async def test_plan_reason_is_strongest_incoming_edge(repo):
    await seed(
        repo,
        [_kn("IP", 3), _kn("ICMP", 3), _kn("TCP", 4)],
        [
            _pe("IP", "TCP", 3, "可靠的端到端传输需要 IP 寻址", confidence=0.95),
            _pe("ICMP", "TCP", 3, "差错报告只是辅助", confidence=0.4),
        ],
    )
    plan = await path_service.plan(repo, path_service.kp_id_for("TCP"))
    reasons = {s["name"]: s["reason"] for s in plan["steps"]}
    assert reasons["TCP"] == "可靠的端到端传输需要 IP 寻址"
    assert reasons["IP"] == ""          # 闭包内没有指向它的前驱边


async def test_plan_without_prereq_is_explicit(repo):
    await seed(repo, [_kn("VLAN", 3, 4)], [])
    plan = await path_service.plan(repo, path_service.kp_id_for("VLAN"))
    assert plan["no_prereq"] is True
    assert [s["name"] for s in plan["steps"]] == ["VLAN"]


async def test_plan_survives_hand_edited_cycle(repo):
    """prereq_edge 可人工改；出现环时不能吊死，也不能漏节点。

    只保证这三条：终止、闭包完整、章号单调不减。环内的相对顺序无解——破环点选在
    下游时，它的上游祖先可能被排到 target 之后，这是坏数据的固有代价，不为它 special-case。
    """
    await seed(
        repo,
        [_kn("A", 3), _kn("B", 3), _kn("C", 3), _kn("D", 3)],
        [_pe("A", "B", 3), _pe("B", "C", 3), _pe("C", "A", 3), _pe("C", "D", 3)],
    )
    plan = await path_service.plan(repo, path_service.kp_id_for("D"))
    names = [s["name"] for s in plan["steps"]]
    assert sorted(names) == ["A", "B", "C", "D"]
    chapters = [s["chapter"] for s in plan["steps"]]
    assert chapters == sorted(chapters)


async def test_plan_touch_count(repo):
    await seed(repo, [_kn("IP", 3), _kn("TCP", 4)], [_pe("IP", "TCP", 4)], touches=["IP"])
    plan = await path_service.plan(repo, path_service.kp_id_for("TCP"))
    assert [s["touch_count"] for s in plan["steps"]] == [1, 0]


async def test_plan_unknown_target_raises_keyerror(repo):
    await seed(repo, [_kn("IP", 3)], [])
    with pytest.raises(KeyError):
        await path_service.plan(repo, "kp_not_exist")


# ----- HTTP 层 -----

async def test_http_endpoints(db_path, monkeypatch):
    from main import app

    init_repo(db_path)
    repo = get_repo()
    await repo.init()
    try:
        await seed(
            repo,
            [_kn("IP", 3, 9), _kn("子网划分", 3, 4), _kn("TCP", 4, 6), _kn("HTTP", 6, 3)],
            [_pe("IP", "TCP", 3, "网络层先于传输层"), _pe("TCP", "HTTP", 4, "应用层用 TCP")],
            touches=["IP"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            path_resp = await client.get("/api/path", params={"chapter": 0})
            limited = await client.get("/api/path", params={"chapter": 3, "limit": 1})
            plan_resp = await client.get(
                "/api/path/plan", params={"target": path_service.kp_id_for("HTTP")}
            )
            missing = await client.get("/api/path/plan", params={"target": "kp_zzz"})

        assert path_resp.status_code == 200
        body = path_resp.json()
        assert set(body) == PATH_FIELDS
        assert body["chapters"] == [3, 4, 6]
        assert [n["name"] for n in body["nodes"]] == ["IP", "子网划分", "TCP", "HTTP"]
        assert body["nodes"][0]["touch_count"] == 1
        assert len(limited.json()["nodes"]) == 1
        assert limited.json()["truncated"] is True
        assert limited.json()["edges"] == []      # 截断后不能留悬空边

        assert plan_resp.status_code == 200
        plan = plan_resp.json()
        assert [s["name"] for s in plan["steps"]] == ["IP", "TCP", "HTTP"]
        assert plan["target"]["name"] == "HTTP"

        assert missing.status_code == 404
        assert missing.json()["error_code"] == "PATH_TARGET_NOT_FOUND"
    finally:
        await repo.close()
