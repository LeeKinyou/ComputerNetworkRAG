"""P1 网络工具的安全校验（05 §3/§4）：http_probe 建工具时直接复用。"""

import ipaddress
from urllib.parse import urlparse

_BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10")
]


def validate_http_url(url: str, allow_loopback: bool = True) -> str | None:
    """返回错误文案；None 表示允许。仅校验字面 IP，域名目标交由 DNS。"""
    text = str(url or "").strip()
    if not text:
        return "URL 不能为空"
    try:
        parsed = urlparse(text)
    except ValueError:
        return "URL 格式非法"
    if parsed.scheme not in ("http", "https"):
        return "仅允许 http/https 协议"
    host = parsed.hostname
    if not host:
        return "URL 缺少主机名"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    if ip.is_loopback:
        return None if allow_loopback else "禁止访问回环地址"
    for net in _BLOCKED_NETS:
        if ip in net:
            return "禁止访问内网/保留地址（NFR-SEC-03）"
    if ip.is_reserved or ip.is_multicast:
        return "禁止访问保留/组播地址"
    return None
