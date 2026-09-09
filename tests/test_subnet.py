"""subnet_calculator 测试：与 ipaddress 标准库对拍（05 §2.1）。"""

import ipaddress

import pytest

from app.agent.tools import create_registry


@pytest.fixture
def registry():
    return create_registry()


async def run(registry, **args):
    return await registry.run("subnet_calculator", args)


DOC_EXAMPLE = {
    "input": "192.168.10.137/27",
    "network": "192.168.10.128",
    "prefix": 27,
    "netmask": "255.255.255.224",
    "broadcast": "192.168.10.159",
    "first_host": "192.168.10.129",
    "last_host": "192.168.10.158",
    "host_count": 30,
    "is_private": True,
}


def expected_hosts(net: ipaddress.IPv4Network):
    n = net.prefixlen
    if n == 31:
        return str(net.network_address), str(net.broadcast_address), 2
    if n == 32:
        return str(net.network_address), str(net.network_address), 1
    return (
        str(net.network_address + 1),
        str(net.broadcast_address - 1),
        2 ** (32 - n) - 2,
    )


@pytest.mark.parametrize(
    "cidr",
    [
        "192.168.1.15/24",
        "172.16.3.7/27",
        "10.0.5.9/16",
        "192.168.10.137/32",
        "10.1.2.3/31",
        "8.8.8.68/30",
        "1.2.3.4/12",
    ],
)
async def test_matches_ipaddress_stdlib(registry, cidr):
    result = await run(registry, ip_cidr=cidr)
    assert result.status == "success"
    s = result.structured
    net = ipaddress.ip_network(cidr, strict=False)
    first, last, count = expected_hosts(net)
    assert s["input"] == cidr
    assert s["network"] == str(net.network_address)
    assert s["prefix"] == net.prefixlen
    assert s["netmask"] == str(net.netmask)
    assert s["broadcast"] == str(net.broadcast_address)
    assert s["first_host"] == first
    assert s["last_host"] == last
    assert s["host_count"] == count
    assert s["is_private"] == net.is_private
    assert result.elapsed_ms >= 0


async def test_doc_example_exact_fields(registry):
    result = await run(registry, ip_cidr="192.168.10.137/27")
    assert result.status == "success"
    assert result.structured == DOC_EXAMPLE
    assert "192.168.10.128/27" in result.output
    assert "255.255.255.224" in result.output
    assert "192.168.10.159" in result.output
    assert "30 台" in result.output
    assert "私网" in result.output


async def test_rfc31_32_annotated(registry):
    r31 = await run(registry, ip_cidr="10.1.2.3/31")
    assert r31.status == "success"
    assert r31.structured["host_count"] == 2
    assert "RFC 3021" in r31.structured.get("note", "")
    assert "点对点" in r31.output

    r32 = await run(registry, ip_cidr="192.168.10.137/32")
    assert r32.status == "success"
    assert r32.structured["host_count"] == 1
    assert r32.structured["first_host"] == "192.168.10.137"
    assert "单主机" in r32.output


async def test_public_ip_flag(registry):
    result = await run(registry, ip_cidr="8.8.8.0/24")
    assert result.status == "success"
    assert result.structured["is_private"] is False
    assert "公网" in result.output


@pytest.mark.parametrize(
    "text",
    [
        "192.168.10.137 255.255.255.224",
        "192.168.10.137/255.255.255.224",
    ],
)
async def test_netmask_second_form(registry, text):
    result = await run(registry, ip_cidr=text)
    assert result.status == "success"
    s = result.structured
    assert s["network"] == "192.168.10.128"
    assert s["prefix"] == 27
    assert s["netmask"] == "255.255.255.224"


@pytest.mark.parametrize(
    "bad",
    [
        "abc",
        "192.168.1.1",
        "192.168.1.1/33",
        "192.168.1.1/-1",
        "192.168.1.1/x",
        "300.1.1.1/24",
        "192.168.1.1/24/8",
        "",
    ],
)
async def test_invalid_inputs_fail(registry, bad):
    result = await run(registry, ip_cidr=bad)
    assert result.status == "failed"
    assert result.output
    assert "Traceback" not in result.output


async def test_prefix_out_of_range_message(registry):
    result = await run(registry, ip_cidr="192.168.1.1/33")
    assert result.status == "failed"
    assert "0-32" in result.output


async def test_octet_overflow_message_is_chinese(registry):
    # 07 Task4.2：非法 CIDR 演练要求界面明确提示，不能透传 ipaddress 英文异常
    result = await run(registry, ip_cidr="999.999.1.1/99")
    assert result.status == "failed"
    assert "非法" in result.output
    assert "Octet" not in result.output


async def test_registry_envelope(registry):
    missing = await registry.run("subnet_calculator", {})
    assert missing.status == "failed"
    assert "缺少必填参数" in missing.output

    wrong_type = await registry.run("subnet_calculator", {"ip_cidr": 123})
    assert wrong_type.status == "failed"
    assert "ip_cidr" in wrong_type.output

    unknown = await registry.run("no_such_tool", {})
    assert unknown.status == "failed"
    assert "未知工具" in unknown.output
