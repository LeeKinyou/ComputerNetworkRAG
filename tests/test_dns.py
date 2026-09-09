"""dns_lookup 测试：可重放的 mock resolver（05 §2.3）。"""

import dns.exception
import dns.resolver
import pytest

from app.agent.tools import create_registry
from app.agent.tools.dns import DnsLookupTool


class FakeResolver:
    def __init__(self, answer=None, error=None):
        self.answer = answer or []
        self.error = error
        self.nameservers = ["114.114.114.114"]
        self.calls = []

    def resolve(self, domain, rtype):
        self.calls.append((domain, rtype))
        if self.error is not None:
            raise self.error
        return self.answer


class FakeRdata:
    def __init__(self, text):
        self._text = text

    def __str__(self):
        return self._text


@pytest.fixture
def registry():
    return create_registry()


async def run(registry, **args):
    return await registry.run("dns_lookup", args)


async def test_success_a_record():
    fake = FakeResolver(answer=[FakeRdata("93.184.216.34")])
    result = await DnsLookupTool(resolver_factory=lambda: fake)._run(
        domain="www.example.com", rtype="A"
    )
    assert result.status == "success"
    assert result.structured["domain"] == "www.example.com"
    assert result.structured["rtype"] == "A"
    assert result.structured["records"] == ["93.184.216.34"]
    assert result.structured["resolver"] == ["114.114.114.114"]
    assert "93.184.216.34" in result.output
    assert fake.calls == [("www.example.com", "A")]


async def test_success_mx_record_trailing_dot_stripped():
    fake = FakeResolver(answer=[FakeRdata("10 mail.example.com.")])
    result = await DnsLookupTool(resolver_factory=lambda: fake)._run(
        domain="example.com", rtype="MX"
    )
    assert result.status == "success"
    assert result.structured["records"] == ["10 mail.example.com"]


async def test_trailing_dot_tolerated():
    fake = FakeResolver(answer=[FakeRdata("93.184.216.34")])
    result = await DnsLookupTool(resolver_factory=lambda: fake)._run(
        domain="www.example.com.", rtype="A"
    )
    assert result.status == "success"
    assert fake.calls[0][0] == "www.example.com"


async def test_rtype_enum_rejected(registry):
    result = await run(registry, domain="www.example.com", rtype="TXT")
    assert result.status == "failed"
    assert "仅允许" in result.output


@pytest.mark.parametrize(
    "bad", ["", "not a domain", "-abc.com", "a..b.com", "a" * 250 + ".com", "http://x.com"]
)
async def test_invalid_domain_failed(registry, bad):
    result = await run(registry, domain=bad)
    assert result.status == "failed"
    assert "域名" in result.output


async def test_nxdomain_failed():
    fake = FakeResolver(error=dns.resolver.NXDOMAIN())
    result = await DnsLookupTool(resolver_factory=lambda: fake)._run(
        domain="no-such.example.com", rtype="A"
    )
    assert result.status == "failed"
    assert "不存在" in result.output


async def test_timeout_failed():
    fake = FakeResolver(error=dns.exception.Timeout())
    result = await DnsLookupTool(resolver_factory=lambda: fake)._run(
        domain="slow.example.com", rtype="A"
    )
    assert result.status == "failed"
    assert "超时" in result.output


async def test_no_answer_failed():
    fake = FakeResolver(error=dns.resolver.NoAnswer())
    result = await DnsLookupTool(resolver_factory=lambda: fake)._run(
        domain="example.com", rtype="AAAA"
    )
    assert result.status == "failed"
    assert "AAAA" in result.output


async def test_dns_registered_without_rag_service():
    registry = create_registry()
    assert "dns_lookup" in registry.names()
