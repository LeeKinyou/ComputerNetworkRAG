"""大屏图表与动效（09 号文档 Task 5.3）：静态契约测试。

大屏是纯静态页，没有 JS 测试运行器，锁的是"改坏了会整块空白"的几条硬约束：
图容器 id 与脚本引用必须一一对应、共用布局模块的加载顺序、无 Vue 依赖、动效与轮询参数。
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
SCREEN_HTML = (STATIC / "screen.html").read_text(encoding="utf-8")
SCREEN_JS = (STATIC / "assets/js/screen/screen.js").read_text(encoding="utf-8")
SCREEN_CSS = (STATIC / "assets/css/screen.css").read_text(encoding="utf-8")
LAYOUT_JS = (STATIC / "assets/js/components/graph-layout.js").read_text(encoding="utf-8")
GRAPH_VIEW_JS = (STATIC / "assets/js/components/graph-view.js").read_text(encoding="utf-8")
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")

CHART_IDS = [
    "chart-graph", "chart-entity-types", "chart-trend",
    "chart-tools", "chart-chapters", "chart-top-entities",
]


def _script_order(html: str, names):
    return [html.index(name) for name in names]


def test_screen_html_has_all_chart_containers():
    for cid in CHART_IDS:
        assert 'id="%s"' % cid in SCREEN_HTML, cid
    for sid in ("stat-documents", "stat-entities", "stat-relations",
                "stat-chunks", "stat-sessions", "stat-runs"):
        assert 'id="%s"' % sid in SCREEN_HTML, sid


def test_screen_script_renders_every_chart_container():
    """容器 id 与脚本引用必须一一对应：写错一个字母就是一块永久空白。"""
    for cid in CHART_IDS + ["stat-documents", "stat-runs", "scFeed"]:
        assert cid in SCREEN_JS, cid


def test_screen_loads_shared_layout_module_before_script():
    layout, script = _script_order(SCREEN_HTML, ("components/graph-layout.js", "screen/screen.js"))
    assert layout < script


def test_index_loads_shared_layout_module_before_graph_view():
    """工作台同样按依赖顺序加载，否则 graph-view 取不到共用件。"""
    layout, view = _script_order(
        INDEX_HTML, ("components/graph-layout.js", "components/graph-view.js")
    )
    assert layout < view


def test_layout_module_exports_shared_helpers():
    for name in ("TYPE_COLORS", "nodeSize", "harvest", "fitToCanvas", "placeLabels"):
        assert name in LAYOUT_JS, name
    assert "graphLayout" in LAYOUT_JS


def test_screen_does_not_depend_on_vue_or_workspace_modules():
    """大屏与工作台两套生命周期互不干扰（09 §2.2）。"""
    assert "Vue" not in SCREEN_JS
    assert "Store" not in SCREEN_JS
    assert "components/graph-view.js" not in SCREEN_HTML


def test_screen_js_wires_aggregate_endpoint_and_polling():
    assert "/api/screen/overview" in SCREEN_JS
    assert "/api/graph" in SCREEN_JS
    assert "POLL_MS = 30000" in SCREEN_JS
    assert "FOCUS_MS = 8000" in SCREEN_JS          # 中央图谱 8s 换一类聚焦
    assert "GRAPH_NODES = 300" in SCREEN_JS        # 投屏掉帧护栏（09 §6）
    assert "devicePixelRatio: 2" in SCREEN_JS      # scale 后 canvas 不糊
    assert "GRAPH_POLL_MS" in SCREEN_JS            # 图谱比数字轮询慢，别每 30s 重排


def test_screen_js_has_the_five_animations():
    assert "requestAnimationFrame" in SCREEN_JS    # ① 数字卡滚动
    assert "dispatchAction" in SCREEN_JS           # ② 聚焦轮播
    assert "animationDuration" in SCREEN_JS        # ③ 图表瀑布入场
    assert "animationDelay" in SCREEN_JS
    assert "sc-marquee-content" in SCREEN_JS       # ④ 跑马灯内容由脚本灌入
    assert "sc-panel::before" in SCREEN_CSS        # ⑤ 面板切角发光（CSS）


def test_screen_js_degrades_per_chart():
    """任一图取不到数据只该自己显示占位，不允许整屏白（09 §2.1 第 2 条）。"""
    assert "placeholder(" in SCREEN_JS
    assert "clearPlaceholder(" in SCREEN_JS
    assert "catch" in SCREEN_JS


def test_coverage_card_wired_html_to_script():
    """覆盖率卡：容器 id 与脚本引用一一对应，分子分母都取后端字段（口径与 #/path 同源）。"""
    for sid in ("stat-coverage", "coverageSub", "coverageBar"):
        assert 'id="%s"' % sid in SCREEN_HTML, sid
        assert sid in SCREEN_JS, sid
    assert "data.coverage" in SCREEN_JS
    assert ".touched" in SCREEN_JS and ".total" in SCREEN_JS


def test_coverage_card_keeps_placeholder_when_field_absent():
    """老进程（改动后没重启）返回里没有 coverage 字段：卡片必须停在占位符。
    滚成 0.00% 会被读成"没人问过"，跟"后端根本不认识这个字段"是两回事。"""
    assert "if (!coverage) return" in SCREEN_JS


def test_coverage_card_spans_whole_stat_grid():
    """第 7 张卡横跨两列：2×3 栅格里塞第七个小方块会留洞，进度条反而需要整行宽。"""
    assert "sc-stat-wide" in SCREEN_HTML
    assert "grid-column: 1 / -1" in SCREEN_CSS


def test_graph_view_delegates_layout_to_shared_module():
    assert "graphLayout" in GRAPH_VIEW_JS
    # 类型配色只在共用件里定义一份
    assert "'设备': '#EA580C'" in LAYOUT_JS
    assert "'设备': '#EA580C'" not in GRAPH_VIEW_JS


def test_labels_stay_hidden_until_coordinates_are_frozen():
    """避碰要拿冻结后的坐标算：坐标没就绪时 placed 永不增长，cap 形同虚设，
    500 个实体的标签会全糊在图上——这正是注释里点名要避免的那一幕。"""
    body = LAYOUT_JS[LAYOUT_JS.index("placeLabels:"):]
    assert re.search(r"if \(!frozenPos\) return \{\};", body), "placeLabels 必须先挡掉未冻结态"


def test_every_unfreeze_path_refreezes():
    """清掉 frozenPos 的四处（挂载/尺寸变化/重新布局/换数据）都得重新冻结，漏一处就永远停在力导实时态。"""
    assert GRAPH_VIEW_JS.count("frozenPos = null; render(); freezeIfReady();") == 2
    assert GRAPH_VIEW_JS.count("freezeIfReady();") >= 4


def test_resource_version_bumped_on_both_pages():
    """两个页面共用一个全局版本号：改过 JS/CSS 必须整站 +1，否则演示时吃到旧缓存。"""
    versions = set(re.findall(r"\?v=(m\d+)", SCREEN_HTML)) | set(re.findall(r"\?v=(m\d+)", INDEX_HTML))
    assert versions == {"m75"}
