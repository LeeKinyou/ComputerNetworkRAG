import pytest

from app.tools import subnet


def test_slash_28_normalizes_host_bits():
    result = subnet("192.168.10.137", 28)
    assert result.status == "ok"
    data = result.data
    assert data["network_address"] == "192.168.10.128"
    assert data["broadcast_address"] == "192.168.10.143"
    assert data["first_host"] == "192.168.10.129"
    assert data["last_host"] == "192.168.10.142"
    assert data["usable_host_count"] == 14
    assert data["block_size"] == 16
    assert data["mask"] == "255.255.255.240"
    assert any("主机位" in item for item in data["warnings"])


def test_slash_26_from_network_address():
    data = subnet("10.0.0.0", 26).data
    assert data["network_address"] == "10.0.0.0"
    assert data["broadcast_address"] == "10.0.0.63"
    assert data["first_host"] == "10.0.0.1"
    assert data["last_host"] == "10.0.0.62"
    assert data["usable_host_count"] == 62
    assert data["block_size"] == 64


def test_slash_30_keeps_two_hosts():
    data = subnet("192.168.1.4", 30).data
    assert data["network_address"] == "192.168.1.4"
    assert data["broadcast_address"] == "192.168.1.7"
    assert data["usable_host_count"] == 2
    assert data["first_host"] == "192.168.1.5"
    assert data["last_host"] == "192.168.1.6"


def test_slash_31_requires_point_to_point_policy():
    result = subnet("10.0.0.0", 31)
    assert result.status == "invalid_input"
    assert result.error_code == "ADDRESS_POLICY_REQUIRED"

    result = subnet("10.0.0.0", 31, "point_to_point")
    assert result.status == "ok"
    assert result.data["usable_host_count"] == 2
    assert result.data["broadcast_address"] is None


def test_slash_32_requires_host_route_policy():
    result = subnet("10.0.0.5", 32)
    assert result.error_code == "ADDRESS_POLICY_REQUIRED"

    result = subnet("10.0.0.5", 32, "host_route")
    assert result.status == "ok"
    assert result.data["network_address"] == "10.0.0.5"
    assert result.data["usable_host_count"] == 1
    assert result.data["broadcast_address"] is None


@pytest.mark.parametrize(
    "ip, prefix, code",
    [
        ("192.168.1.256", 24, "INVALID_IPV4"),
        ("not-an-ip", 24, "INVALID_IPV4"),
        ("10.0.0.1", 33, "INVALID_PREFIX"),
        ("10.0.0.1", -1, "INVALID_PREFIX"),
    ],
)
def test_invalid_inputs_are_rejected(ip: str, prefix: int, code: str):
    result = subnet(ip, prefix)
    assert result.status == "invalid_input"
    assert result.error_code == code
