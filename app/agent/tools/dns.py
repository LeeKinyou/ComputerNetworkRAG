"""dns_lookup：真实 DNS 解析（dnspython），仅查询、不做反向枚举（05 §2.3）。"""

import asyncio
import re

import dns.exception
import dns.resolver

from app.agent.registry import BaseTool, ToolResult
from app.config import get_settings

# 域名：1-253 位，点分标签（字母数字连字符，不以连字符开头/结尾），顶级标签为字母
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE
)


class DnsLookupTool(BaseTool):
    name = "dns_lookup"
    description = (
        "DNS 域名解析：查询域名的解析记录（A/IPv4、AAAA/IPv6、CNAME/别名、MX/邮件），"
        "返回记录列表与使用的解析服务器。示例：{\"domain\": \"www.example.com\", \"rtype\": \"A\"}"
    )
    args_schema = {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "合法域名，如 www.example.com"},
            "rtype": {"type": "string", "enum": ["A", "AAAA", "CNAME", "MX"], "description": "记录类型，默认 A"},
        },
        "required": ["domain"],
    }

    def __init__(self, resolver_factory=None):
        self._resolver_factory = resolver_factory
        self.timeout_s = float(get_settings().TOOL_TIMEOUT)

    def _make_resolver(self):
        if self._resolver_factory is not None:
            return self._resolver_factory()
        resolver = dns.resolver.Resolver()
        resolver.lifetime = self.timeout_s
        resolver.timeout = self.timeout_s
        return resolver

    async def _run(self, domain: str = "", rtype: str = "A") -> ToolResult:
        name = str(domain or "").strip().rstrip(".")
        if not _DOMAIN_RE.match(name):
            return ToolResult(
                status="failed",
                output="域名格式非法：应为如 www.example.com 的合法域名（总长 ≤253，仅字母数字连字符与点）",
            )
        resolver = self._make_resolver()
        try:
            answer = await asyncio.to_thread(resolver.resolve, name, rtype)
        except dns.resolver.NXDOMAIN:
            return ToolResult(status="failed", output=f"域名 {name} 不存在（NXDOMAIN）")
        except dns.exception.Timeout:
            return ToolResult(
                status="failed", output=f"解析 {name} 超时（超过 {self.timeout_s:g} 秒）"
            )
        except dns.resolver.NoAnswer:
            return ToolResult(
                status="failed", output=f"域名 {name} 存在，但没有 {rtype} 记录"
            )
        except dns.resolver.NoNameservers:
            return ToolResult(
                status="failed", output=f"解析 {name} 失败：解析服务器返回错误（SERVFAIL）"
            )
        records = [str(r).rstrip(".").strip() for r in answer]
        nameservers = [str(ns) for ns in getattr(resolver, "nameservers", [])]
        structured = {
            "domain": name,
            "rtype": rtype,
            "records": records,
            "resolver": nameservers,
        }
        server = "、".join(nameservers) if nameservers else "系统默认"
        output = f"{name} 的 {rtype} 记录：{'、'.join(records) or '（空）'}（解析服务器 {server}）"
        return ToolResult(status="success", output=output, structured=structured)
