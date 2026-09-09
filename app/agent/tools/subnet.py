"""subnet_calculator：IPv4 子网计算，纯本地确定性（05 §2.1）。"""

import ipaddress

from app.agent.registry import BaseTool, ToolResult


def _dotted_mask_to_prefix(mask_text: str) -> int:
    try:
        mask = ipaddress.IPv4Address(mask_text)
    except ValueError:
        raise ValueError(f"子网掩码格式非法：{mask_text}")
    mask_int = int(mask)
    all_ones = 0xFFFFFFFF
    suffix = (mask_int ^ all_ones) + 1  # 主机位取反加一应为 2 的幂
    if suffix & (suffix - 1) or mask_int == 0:
        raise ValueError(f"子网掩码不是连续 1 前缀：{mask_text}")
    return 32 - suffix.bit_length() + 1


class SubnetCalculatorTool(BaseTool):
    name = "subnet_calculator"
    description = (
        "IPv4 子网计算器：给定形如 192.168.10.137/27 的 CIDR 地址"
        "（也支持 '192.168.10.137 255.255.255.224' 掩码写法），"
        "返回网络地址、掩码、广播地址、可用主机范围与数量。"
        '示例：{"ip_cidr": "192.168.10.137/27"}'
    )
    args_schema = {
        "type": "object",
        "properties": {
            "ip_cidr": {
                "type": "string",
                "description": "IPv4 CIDR（如 192.168.10.137/27）或 'IP 掩码' 空格分隔",
            }
        },
        "required": ["ip_cidr"],
    }

    async def _run(self, ip_cidr: str = "") -> ToolResult:
        text = str(ip_cidr or "").strip()
        try:
            if " " in text:
                ip_part, mask_part = text.split(None, 1)
                ip = ipaddress.IPv4Address(ip_part.strip())
                n = _dotted_mask_to_prefix(mask_part.strip())
            else:
                ip_part, sep, tail = text.partition("/")
                if not sep:
                    return ToolResult(
                        status="failed",
                        output="输入格式应为 IP/前缀长度（如 192.168.10.137/27），"
                        "或 'IP 掩码'（如 192.168.10.137 255.255.255.224）",
                    )
                ip = ipaddress.IPv4Address(ip_part.strip())
                n_text = tail.strip()
                if "." in n_text:
                    n = _dotted_mask_to_prefix(n_text)
                elif not n_text.isdigit():
                    return ToolResult(status="failed", output="CIDR 前缀应为 0-32 的整数")
                else:
                    n = int(n_text)
            if not 0 <= n <= 32:
                return ToolResult(status="failed", output="CIDR 前缀应为 0-32 的整数")
        except ValueError as exc:
            return ToolResult(status="failed", output=str(exc))

        mask = (0xFFFFFFFF << (32 - n)) & 0xFFFFFFFF if n else 0
        ip_int = int(ip)
        network_int = ip_int & mask
        broadcast_int = network_int | (~mask & 0xFFFFFFFF)
        if n == 31:
            host_count, first_int, last_int = 2, network_int, broadcast_int
            note = "/31 点对点链路（RFC 3021）：两个地址均可直接使用"
        elif n == 32:
            host_count, first_int, last_int = 1, network_int, network_int
            note = "/32 单主机地址，无广播概念"
        else:
            host_count = 2 ** (32 - n) - 2
            first_int, last_int = network_int + 1, broadcast_int - 1
            note = ""

        # 与 ipaddress 标准库交叉校验，防手写位运算出错
        net = ipaddress.ip_network(f"{ip}/{n}", strict=False)
        if (
            int(net.network_address) != network_int
            or int(net.broadcast_address) != broadcast_int
        ):
            network_int = int(net.network_address)
            broadcast_int = int(net.broadcast_address)

        addr = ipaddress.IPv4Address
        structured = {
            "input": text,
            "network": str(addr(network_int)),
            "prefix": n,
            "netmask": str(net.netmask),
            "broadcast": str(addr(broadcast_int)),
            "first_host": str(addr(first_int)),
            "last_host": str(addr(last_int)),
            "host_count": host_count,
            "is_private": net.is_private,
        }
        if note:
            structured["note"] = note

        scope = "私网" if net.is_private else "公网"
        output = (
            f"网络地址 {structured['network']}/{n}；掩码 {structured['netmask']}；"
            f"广播地址 {structured['broadcast']}；"
            f"可用主机 {structured['first_host']}-{structured['last_host']}，"
            f"共 {host_count} 台；属于{scope}地址"
        )
        if note:
            output += f"。注意：{note}"
        return ToolResult(status="success", output=output + "。", structured=structured)
