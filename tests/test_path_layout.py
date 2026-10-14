"""路径画布布局的数值回归（node 驱动，缺 node 时跳过）。

test_path_view.py 里的静态契约只能锁"代码里还有这段逻辑"，锁不住像素：
S1 的原始症状是 280 个节点被缩进行距 7px 对高 44px 的方块叠成一整块色块，
后续又暴露出 fitBox 把整张网格平移到了画布右下象限（中心坐标从 w/2 起算）。
两种都只有真跑一遍排版代码才量得出来，所以这里用假的 Vue/echarts 驱动组件，
断言"绘制的方块两两不相交、且全部落在容器内"。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests" / "fixtures" / "path_layout_driver.js"
LAYOUT_JS = ROOT / "static" / "assets" / "js" / "components" / "graph-layout.js"
GRAPH_JS = ROOT / "static" / "assets" / "js" / "components" / "path-graph.js"

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="布局数值回归需要 node")

LONG = "域名系统 DNS 报文格式与查询过程"
SHORT = "TCP"


def node(i, chapter=4, layer=0, degree=5, name=None):
    return {
        "kp_id": f"kp_{i:04d}",
        "name": name or (LONG if i % 3 == 0 else f"知识点{i:03d}"),
        "type": "概念",
        "chapter": chapter,
        "layer": layer,
        "degree": degree,
        "touch_count": 3 if i % 5 == 0 else 0,
        "description": "描述",
    }


def make_nodes(count, **kw):
    return [node(i, **kw) for i in range(count)]


def layered_nodes(count, layers):
    """按 layer 轮转分布，模拟 prereq_edge 有边之后的真实分层。"""
    return [node(i, layer=layers[i % len(layers)], name=f"前置知识点{i:03d}")
            for i in range(count)]


def edges_between(nodes):
    """链式边：只连相邻两层，两端都在节点集内。"""
    by_layer = {}
    for n in nodes:
        by_layer.setdefault(n["layer"], []).append(n)
    layers = sorted(by_layer)
    links = []
    for a, b in zip(layers, layers[1:]):
        for i in range(min(len(by_layer[a]), len(by_layer[b]))):
            links.append({
                "source": by_layer[a][i]["kp_id"],
                "target": by_layer[b][i]["kp_id"],
                "reason": "先学 A 再学 B",
                "confidence": 0.8,
            })
    return links


def run(cases, tmp_path):
    payload = tmp_path / "cases.json"
    payload.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(DRIVER), str(payload), str(LAYOUT_JS), str(GRAPH_JS)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return {r["label"]: r for r in json.loads(proc.stdout)}


def assert_clean(result, label):
    assert result["overlaps"] == 0, (
        f"{label}: 有 {result['overlaps']} 对方块互相压叠，例如 {result['sampleOverlap']}"
    )
    assert result["off"] == 0, (
        f"{label}: 有 {result['off']} 个方块越出画布，例如 {result['offIds']}"
    )
    assert result["drawn"] >= 1, f"{label}: 一个节点都没画出来"


def test_isolated_chapter_fits_the_desktop_canvas(tmp_path):
    """prereq_edge 还是空表时的现场：/api/path?chapter=0 给 280 个 layer=0 的孤立节点。"""
    r = run([{
        "label": "isolated-280-desktop", "nodes": make_nodes(280), "edges": [],
        "width": 1200, "height": 700,
    }], tmp_path)["isolated-280-desktop"]
    assert_clean(r, "桌面 1200x700")
    assert r["cap"]["total"] == 280
    assert r["drawn"] == r["cap"]["drawn"] < 280, "放不下的必须裁掉并通过 cap 说明"


def test_isolated_chapter_fits_the_phone_canvas(tmp_path):
    r = run([{
        "label": "isolated-40-phone", "nodes": make_nodes(40), "edges": [],
        "width": 390, "height": 620, "phone": True,
    }], tmp_path)["isolated-40-phone"]
    assert_clean(r, "手机 390x620")
    assert r["cap"]["total"] == 40


def test_layered_graph_stays_on_canvas(tmp_path):
    """有边之后按层排开：多层的横向展开同样不能越界。"""
    nodes = layered_nodes(64, [0, 1, 2, 3, 4, 5, 6, 7])
    r = run([{
        "label": "layered-64", "nodes": nodes, "edges": edges_between(nodes),
        "width": 1440, "height": 820,
    }], tmp_path)["layered-64"]
    assert_clean(r, "分层 8 层 1440x820")
    assert r["linkCount"] > 0, "两端都绘制了的边必须保留"


def test_ring_mode_falls_back_instead_of_overlapping(tmp_path):
    nodes = make_nodes(30)
    r = run([{
        "label": "ring-30", "nodes": nodes, "edges": [],
        "width": 1200, "height": 700, "mode": "ring",
    }], tmp_path)["ring-30"]
    assert_clean(r, "环形 30 节点")
    assert r["cap"]["fellBack"] is True, "圆周放不下时必须退回分层并上报"


def test_degenerate_container_draws_one_node_instead_of_nothing(tmp_path):
    """容器尺寸未就绪（隐藏时 echarts 给 100x100）：只画一个、不重叠就是正确行为。
    方块本身 240px 宽，100px 容器装不下任何一个，越界在这里不是缺陷而是几何事实；
    真正要守住的是"容器一旦装得下一个，它就必须完整落在画布内"。"""
    cases = [
        {"label": "tiny", "nodes": make_nodes(280), "edges": [], "width": 100, "height": 100},
        {"label": "one-wide", "nodes": make_nodes(280), "edges": [], "width": 300, "height": 300},
    ]
    r = run(cases, tmp_path)
    assert r["tiny"]["drawn"] == 1
    assert r["tiny"]["overlaps"] == 0
    assert_clean(r["one-wide"], "容器 300x300")
    assert 1 <= r["one-wide"]["drawn"] <= 3


def test_crop_still_happens_when_everything_is_too_wide(tmp_path):
    """全是最宽节点（240px）时列数骤减，截断必须更狠。"""
    r = run([{
        "label": "wide", "nodes": make_nodes(120, name=LONG), "edges": [],
        "width": 900, "height": 500,
    }], tmp_path)["wide"]
    assert_clean(r, "宽节点 900x500")
    assert r["drawn"] < 120
