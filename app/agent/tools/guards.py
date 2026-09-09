"""P1 网络工具的安全校验（05 §3/§4）：http_probe / ping_host 建工具时直接复用。"""

import ipaddress
import re
import socket
from urllib.parse import urlparse

_BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10")
]

# 与 dns.py 的域名规则一致：点分标签，顶级标签为字母
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE
)


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_loopback: bool) -> str | None:
    if ip.is_loopback:
        return None if allow_loopback else "禁止访问回环地址"
    for net in _BLOCKED_NETS:
        if ip in net:
            return "禁止访问内网/保留地址（NFR-SEC-03）"
    if ip.is_reserved or ip.is_multicast:
        return "禁止访问保留/组播地址"
    return None


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
    return _check_ip(ip, allow_loopback)


def validate_host(host: str, allow_loopback: bool = True) -> str | None:
    """探测目标校验：字面 IP 直接查黑名单；域名解析后逐地址校验，防止绕道内网。"""
    text = str(host or "").strip().rstrip(".")
    if not text:
        return "主机不能为空"
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        pass
    else:
        return _check_ip(ip, allow_loopback)
    if not _HOSTNAME_RE.match(text):
        return "主机名格式非法：应为域名（如 www.example.com）或 IP 地址"
    try:
        infos = socket.getaddrinfo(text, None)
    except OSError:
        return f"无法解析主机 {text}"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        error = _check_ip(ip, allow_loopback)
        if error:
            return error
    return None
