"""lpm_lookup 测试：最长前缀匹配 / 仅默认路由 / 无路由（05 §2.2）。"""

import pytest

from app.agent.tools import create_registry

DOC_ROUTES = [
    {"prefix": "0.0.0.0/0", "next_hop": "R1", "interface": "eth0"},
    {"prefix": "10.2.0.0/16", "next_hop": "R2", "interface": "eth1"},
    {"prefix": "10.2.3.0/24", "next_hop": "R3", "interface": "eth2"},
]


@pytest.fixture
def registry():
    return create_registry()


async def run(registry, **args):
    return await registry.run("lpm_lookup", args)


async def test_longest_prefix_wins(registry):
    result = await run(registry, destination_ip="10.2.3.4", routes=DOC_ROUTES)
    assert result.status == "success"
    assert result.structured["selected"] == {
        "prefix": "10.2.3.0/24",
        "next_hop": "R3",
        "interface": "eth2",
    }
    trace = result.structured["trace"]
    assert [t["prefix"] for t in trace] == ["10.2.3.0/24", "10.2.0.0/16", "0.0.0.0/0"]
    assert trace[0]["matched"] is True
    assert "更短" in trace[1]["note"]
    assert "默认路由" in trace[2]["note"]
    assert "R3" in result.output and "eth2" in result.output


async def test_route_order_irrelevant(registry):
    shuffled = [DOC_ROUTES[1], DOC_ROUTES[0], DOC_ROUTES[2]]
    result = await run(registry, destination_ip="10.2.3.4", routes=shuffled)
    assert result.status == "success"
    assert result.structured["selected"]["prefix"] == "10.2.3.0/24"
    assert [t["prefix"] for t in result.structured["trace"]] == [
        "10.2.3.0/24",
        "10.2.0.0/16",
        "0.0.0.0/0",
    ]


async def test_default_route_only(registry):
    routes = [{"prefix": "0.0.0.0/0", "next_hop": "R1", "interface": "eth0"}]
    result = await run(registry, destination_ip="8.8.8.8", routes=routes)
    assert result.status == "success"
    assert result.structured["selected"]["prefix"] == "0.0.0.0/0"
    assert "默认路由" in result.structured["trace"][0]["note"]


async def test_no_route_drop(registry):
    routes = [{"prefix": "10.0.0.0/8", "next_hop": "R2", "interface": "eth1"}]
    result = await run(registry, destination_ip="192.168.1.1", routes=routes)
    assert result.status == "success"
    assert result.structured["selected"] is None
    assert "无匹配路由" in result.output
    assert result.structured["trace"][0]["matched"] is False


async def test_builtin_table(registry):
    cases = {
        "10.2.3.7": ("10.2.3.7/32", "R5"),
        "10.2.5.1": ("10.2.0.0/16", "R3"),
        "10.9.9.9": ("10.0.0.0/8", "R2"),
        "8.8.8.8": ("0.0.0.0/0", "R1"),
        "192.168.1.100": ("192.168.1.0/24", "R6"),
    }
    for dst, (prefix, next_hop) in cases.items():
        result = await run(registry, destination_ip=dst)
        assert result.status == "success", dst
        assert result.structured["selected"]["prefix"] == prefix, dst
        assert result.structured["selected"]["next_hop"] == next_hop, dst


async def test_invalid_destination(registry):
    result = await run(registry, destination_ip="not-an-ip")
    assert result.status == "failed"
    assert "IPv4" in result.output


async def test_invalid_route_entry(registry):
    result = await run(
        registry,
        destination_ip="10.2.3.4",
        routes=[{"prefix": "10.0.0.0/33", "next_hop": "R1", "interface": "eth0"}],
    )
    assert result.status == "failed"
    assert result.output


async def test_route_missing_next_hop_rejected(registry):
    result = await run(
        registry,
        destination_ip="10.2.3.4",
        routes=[{"prefix": "10.0.0.0/8", "interface": "eth1"}],
    )
    assert result.status == "failed"
    assert "next_hop" in result.output
