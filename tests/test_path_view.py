"""学习路径页面（09 号文档 Task 5.6）：静态契约 + 路由注册顺序。

前端没有 JS 测试运行器，这里锁的是"改坏了要么整块空白、要么演示当场翻车"的硬约束：
脚本加载顺序、tab 与组件三处注册必须齐、布局不能用 force、环形按钮的 ≤20 闸门、
三态必须带文字（06 §2 不允许只靠颜色）、异常走内联错误条而不是 alert。
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
INDEX_HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "assets/js/app.js").read_text(encoding="utf-8")
VIEW_JS = (STATIC / "assets/js/views/path.js").read_text(encoding="utf-8")
GRAPH_JS = (STATIC / "assets/js/components/path-graph.js").read_text(encoding="utf-8")
APP_CSS = (STATIC / "assets/css/app.css").read_text(encoding="utf-8")


def _order(*names):
    return [INDEX_HTML.index(n) for n in names]


def test_index_html_loads_path_scripts_in_dependency_order():
    """path-graph 要用共用件的 estimateTextWidth，视图要用 window.Components.pathGraph：顺序错了就是白屏。"""
    assert _order("components/graph-layout.js", "components/path-graph.js") == sorted(
        _order("components/graph-layout.js", "components/path-graph.js")
    )
    assert _order("views/path.js", "app.js") == sorted(_order("views/path.js", "app.js"))


def test_path_view_is_registered_in_all_three_places():
    """tab 项、app.component、<path-view> 三处缺一处就是"点了没反应"或"未知组件"警告。"""
    assert re.search(r"key:\s*'path'", APP_JS), "TABS 里少了路径页"
    assert "app.component('path-view', window.Views.path)" in APP_JS
    assert '<path-view v-show="currentView === \'path\'"' in INDEX_HTML


def test_path_view_declares_component_and_export():
    assert "window.Views.path" in VIEW_JS
    assert "'path-graph': window.Components.pathGraph" in VIEW_JS
    assert "window.Components.pathGraph" in GRAPH_JS


def test_canvas_uses_manual_coordinates_not_force_layout():
    """09 §3.5：路径要确定的顺序感。force 每次坐标不同，演示时会跳。"""
    assert "layout: 'none'" in GRAPH_JS
    assert "force:" not in GRAPH_JS
    assert "symbol: 'roundRect'" in GRAPH_JS          # 圆角矩形比圆形放得下中文标签


def test_ring_layout_is_gated_at_20_nodes():
    assert re.search(r"RING_MAX\s*=\s*20", VIEW_JS)
    assert ":disabled=\"ringDisabled\"" in VIEW_JS
    assert "mode.value = 'layer'" in VIEW_JS          # 切章后节点变多要自动退回分层


def test_three_states_carry_text_labels():
    """06 §2：语义不能只靠颜色表达——三态各有一行文字标签。"""
    for label in ("未触达", "已触达", "必修链"):
        assert label in GRAPH_JS, label
    assert "STATE" in GRAPH_JS and "rich" in GRAPH_JS


def test_path_failures_stay_inline():
    """06 §5：不许 alert/confirm，接口失败要能就地重试。"""
    assert "alert(" not in VIEW_JS
    assert "confirm(" not in VIEW_JS
    assert 'class="error-bar"' in VIEW_JS
    assert VIEW_JS.count("@click=\"refresh\"") >= 2


def test_empty_states_point_at_the_build_command():
    """prereq_edge 为空（未跑构建脚本）是演示现场最容易撞上的空态，必须给出命令。"""
    assert VIEW_JS.count("build_learning_path") >= 2
    assert "还没有前驱关系" in VIEW_JS


def test_tooltips_escape_server_text():
    """实体名与 reason 来自模型输出，直接拼进 tooltip 的 HTML 会执行脚本。"""
    assert "function esc(" in GRAPH_JS
    assert "esc(n.name)" in GRAPH_JS and "esc(e.reason" in GRAPH_JS


def test_path_css_defines_canvas_and_legend():
    for selector in (".path-canvas", ".path-legend", ".path-steps", ".path-suggest"):
        assert selector in APP_CSS, selector
    # 画布比图谱页矮一档：路径页多了章节条与必修链卡片
    assert ".path-canvas { height: calc(100vh - 340px)" in APP_CSS


def _flat_routes(routes):
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _flat_routes(inner.routes)
        else:
            yield route


def test_path_routes_registered_before_static_mount():
    from main import app

    paths = [getattr(r, "path", "") for r in _flat_routes(app.routes)]
    names = [getattr(r, "name", "") for r in _flat_routes(app.routes)]
    assert "/api/path" in paths and "/api/path/plan" in paths
    assert names.index("static") > paths.index("/api/path")
