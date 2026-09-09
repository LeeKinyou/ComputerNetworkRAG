"""lpm_lookup：路由表最长前缀匹配，输出逐条比对过程（05 §2.2）。"""

import ipaddress

from app.agent.registry import BaseTool, ToolResult

DEFAULT_ROUTES = [
    {"prefix": "0.0.0.0/0", "next_hop": "R1", "interface": "eth0"},
    {"prefix": "10.0.0.0/8", "next_hop": "R2", "interface": "eth1"},
    {"prefix": "10.2.0.0/16", "next_hop": "R3", "interface": "eth2"},
    {"prefix": "10.2.3.0/24", "next_hop": "R4", "interface": "eth3"},
    {"prefix": "10.2.3.7/32", "next_hop": "R5", "interface": "eth4"},
    {"prefix": "192.168.1.0/24", "next_hop": "R6", "interface": "wlan0"},
]

_ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "prefix": {"type": "string"},
        "next_hop": {"type": "string"},
        "interface": {"type": "string"},
    },
    "required": ["prefix", "next_hop"],
}


class LpmLookupTool(BaseTool):
    name = "lpm_lookup"
    description = (
        "路由器最长前缀匹配查表：给定目的 IP 与可选路由表，逐条比对并输出选中路由"
        "（最长前缀优先），可展示查表过程。routes 缺省时使用内置演示路由表。"
        '示例：{"destination_ip": "10.2.3.4"}'
    )
    args_schema = {
        "type": "object",
        "properties": {
            "destination_ip": {"type": "string", "description": "目的 IPv4 地址"},
            "routes": {
                "type": "array",
                "description": "路由表，缺省用内置演示表",
                "items": _ROUTE_SCHEMA,
            },
        },
        "required": ["destination_ip"],
    }

    async def _run(self, destination_ip: str = "", routes: list | None = None) -> ToolResult:
        try:
            dst = ipaddress.IPv4Address(str(destination_ip).strip())
        except ValueError:
            return ToolResult(
                status="failed", output="destination_ip 应为合法 IPv4 地址"
            )

        entries = []
        for route in routes if routes is not None else DEFAULT_ROUTES:
            try:
                net = ipaddress.ip_network(str(route["prefix"]), strict=False)
            except (ValueError, KeyError):
                return ToolResult(
                    status="failed",
                    output=f"路由前缀格式非法：{route.get('prefix', '（缺失）')}",
                )
            entries.append(
                {"net": net, "next_hop": str(route["next_hop"]), "interface": str(route.get("interface", ""))}
            )

        entries.sort(key=lambda e: e["net"].prefixlen, reverse=True)

        trace = []
        selected = None
        for entry in entries:
            net = entry["net"]
            matched = (int(dst) & int(net.netmask)) == int(net.network_address)
            item = {"prefix": str(net), "matched": matched}
            if matched and selected is None:
                selected = entry
            if matched and net.prefixlen == 0:
                item["note"] = "默认路由，最后兜底"
            elif matched and entry is not selected:
                item["note"] = "命中但前缀更短，不选"
            trace.append(item)

        if selected is None:
            return ToolResult(
                status="success",
                output=f"目的地 {dst} 无匹配路由，数据包丢弃（路由表缺少可用条目或默认路由）",
                structured={"selected": None, "trace": trace},
            )

        structured = {
            "selected": {
                "prefix": str(selected["net"]),
                "next_hop": selected["next_hop"],
                "interface": selected["interface"],
            },
            "trace": trace,
        }
        output = (
            f"目的地 {dst} 按最长前缀匹配选中 {structured['selected']['prefix']}，"
            f"下一跳 {selected['next_hop']}，接口 {selected['interface'] or '无'}；"
            f"共比对 {len(trace)} 条路由。"
        )
        return ToolResult(status="success", output=output, structured=structured)
