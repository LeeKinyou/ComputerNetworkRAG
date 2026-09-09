"""validate_http_url 安全校验测试（05 §3/§4，http_probe P1 备用）。"""

import pytest

from app.agent.tools.guards import validate_http_url


@pytest.mark.parametrize(
    "url", ["http://example.com", "https://example.com/path?q=1", "http://example.com:8080"]
)
def test_public_ok(url):
    assert validate_http_url(url) is None


def test_loopback_allowed_for_demo():
    assert validate_http_url("http://127.0.0.1:8000/api") is None


def test_non_http_scheme_rejected():
    assert "http" in validate_http_url("ftp://example.com")
    assert validate_http_url("file:///etc/passwd") is not None


def test_missing_host_rejected():
    assert validate_http_url("http:///path") is not None
    assert validate_http_url("") is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.1/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://169.254.1.1/",
        "http://100.64.0.1/",
    ],
)
def test_private_ranges_blocked(url):
    assert validate_http_url(url) is not None
