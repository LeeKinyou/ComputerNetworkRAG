"""拍照作业：上传落盘、类型与路径校验、无视觉模型时的待复核降级。"""

from __future__ import annotations

import base64

import pytest

from app.config import settings
from _support import api_harness, seed_course

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

ITEMS = [
    {
        "type": "short",
        "stem": "ARP 的作用是什么？",
        "reference": "把 IP 地址解析为 MAC 地址。",
        "rubric": [
            {"text": "IP 地址解析为 MAC 地址", "score": 6},
            {"text": "在同一广播域内请求与应答", "score": 4},
        ],
        "score": 10,
    }
]


@pytest.fixture
def no_vision(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_vision_model", "")
    monkeypatch.setattr(settings, "llm_vision_api_key", "")


async def _make_assignment(client) -> tuple[str, str]:
    created = await client.post(
        "/api/v2/assignments",
        json={"title": "拍照作业", "status": "published", "items": ITEMS},
    )
    assert created.status_code == 201
    detail = await client.get(f"/api/v2/assignments/{created.json()['id']}")
    return created.json()["id"], detail.json()["items"][0]["id"]


async def test_upload_rejects_non_image():
    async with api_harness() as (client, factory):
        await seed_course(factory)
        response = await client.post(
            "/api/v2/uploads/images",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE_TYPE"


async def test_upload_and_submit_photo_without_vision(no_vision):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        assignment_id, item_id = await _make_assignment(client)

        upload = await client.post(
            "/api/v2/uploads/images",
            files={"file": ("answer.png", PNG_1PX, "image/png")},
        )
        assert upload.status_code == 201
        path = upload.json()["path"]
        assert path.startswith("/media/uploads/") and path.endswith(".png")

        submit = await client.post(
            f"/api/v2/assignments/{assignment_id}/submissions",
            json={"items": [{"item_id": item_id, "image_paths": [path]}]},
        )
        assert submit.status_code == 201
        result = submit.json()
        assert result["status"] == "graded"
        item = result["items"][0]
        assert item["source"] == "pending"
        assert item["needs_review"] is True
        assert item["image_urls"] == [path]
        assert "待教师复核" in item["feedback"]


async def test_submit_photo_with_text_keeps_text_grading(no_vision):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        assignment_id, item_id = await _make_assignment(client)

        upload = await client.post(
            "/api/v2/uploads/images",
            files={"file": ("answer.png", PNG_1PX, "image/png")},
        )
        path = upload.json()["path"]

        submit = await client.post(
            f"/api/v2/assignments/{assignment_id}/submissions",
            json={
                "items": [
                    {
                        "item_id": item_id,
                        "answer": "ARP 把 IP 地址解析为 MAC 地址，在同一广播域内请求与应答。",
                        "image_paths": [path],
                    }
                ]
            },
        )
        item = submit.json()["items"][0]
        assert item["source"] == "rule"
        assert item["score"] == 10
        assert item["image_urls"] == [path]


async def test_submit_drops_path_traversal(no_vision):
    async with api_harness() as (client, factory):
        await seed_course(factory)
        assignment_id, item_id = await _make_assignment(client)

        submit = await client.post(
            f"/api/v2/assignments/{assignment_id}/submissions",
            json={
                "items": [
                    {
                        "item_id": item_id,
                        "answer": "ARP 把 IP 地址解析为 MAC 地址。",
                        "image_paths": ["/media/uploads/../../app/config.py"],
                    }
                ]
            },
        )
        assert submit.status_code == 201
        assert submit.json()["items"][0]["image_urls"] == []
