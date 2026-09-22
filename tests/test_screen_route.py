"""大屏入口（09 号文档 Task 5.1）：GET /screen 返回独立大屏骨架页。

骨架期只锁三件事：路由存在且不被静态兜底遮蔽、页面含栅格占位、深色样式与工作台物理隔离。
"""

from pathlib import Path

from app.api.screen import screen_page

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


async def test_screen_page_returns_html():
    resp = await screen_page()
    assert resp.status_code == 200
    assert resp.media_type == "text/html"


def test_screen_html_has_grid_skeleton():
    html = (STATIC_DIR / "screen.html").read_text(encoding="utf-8")
    assert 'class="screen-root"' in html
    assert 'class="sc-grid"' in html
    assert html.count('class="sc-stat"') == 6          # 核心指标 6 卡
    assert 'class="sc-marquee"' in html                # 底部跑马灯
    assert "assets/css/screen.css" in html
    assert "assets/js/screen/screen.js" in html


def test_screen_html_does_not_load_workspace_style():
    """深浅两套样式必须隔离，避免大屏令牌污染五视图（09 §2.2）。"""
    html = (STATIC_DIR / "screen.html").read_text(encoding="utf-8")
    assert "app.css" not in html
    assert "app.js" not in html


def test_screen_css_defines_dark_tokens_and_fixed_canvas():
    css = (STATIC_DIR / "assets/css/screen.css").read_text(encoding="utf-8")
    for token in ("--sc-bg", "--sc-panel", "--sc-cyan"):
        assert token in css, token
    assert "1920px" in css and "1080px" in css        # 固定设计稿尺寸，靠 JS 等比缩放
    assert "transform-origin" in css


def _flat_routes(routes):
    """FastAPI 0.141 把 include_router 的产物包成 _IncludedRouter，需下钻取原始路由。"""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _flat_routes(inner.routes)
        else:
            yield route


def test_screen_route_registered_before_static_mount():
    """顺序错则 /screen 被 StaticFiles("/") 遮蔽（main.py 同款约束）。"""
    from main import app

    flat = list(_flat_routes(app.routes))
    paths = [getattr(r, "path", "") for r in flat]
    names = [getattr(r, "name", "") for r in flat]
    assert "/screen" in paths
    assert names.index("static") > paths.index("/screen")


async def test_screen_route_serves_skeleton_over_http():
    import httpx

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/screen")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert 'class="screen-root"' in resp.text
