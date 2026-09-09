"""ping_host：主机连通性探测（05 §3）。

Windows ICMP 需管理员权限（08 §已知限制），按规范采用备选方案 TCP connect：
对目标 443 端口做 count 次连接测延迟与丢包。目标经 guards.validate_host
白名单校验（禁内网/保留段，127.0.0.1 例外），全局限速 1 次/秒（05 §4）。
"""

import asyncio
import time

from app.agent.registry import BaseTool, ToolResult
from app.agent.tools.guards import validate_host

_PORT = 443
_CONNECT_TIMEOUT = 3.0
_MIN_INTERVAL = 1.0


class PingHostTool(BaseTool):
    name = "ping_host"
    description = (
        "探测主机连通性（TCP connect 方式，等价 ping）：返回延迟与丢包率，"
        "仅探测目标 443 端口。示例：{\"host\": \"www.example.com\"}"
    )
    args_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "域名或 IP，如 www.example.com"},
            "count": {"type": "integer", "description": "探测次数，1-4，默认 3"},
        },
        "required": ["host"],
    }
    requires_approval = True
    timeout_s = 15.0

    def __init__(self):
        self._last_start = 0.0

    async def _run(self, host: str = "", count: int = 3) -> ToolResult:
        host = str(host or "").strip().rstrip(".")
        error = validate_host(host)
        if error:
            return ToolResult(status="failed", output=error)
        if isinstance(count, bool) or not isinstance(count, int) or not (1 <= count <= 4):
            return ToolResult(status="failed", output="探测次数应为 1-4 的整数")
        now = time.monotonic()
        if now - self._last_start < _MIN_INTERVAL:
            return ToolResult(status="failed", output="探测过于频繁（限速 1 次/秒），请稍后重试")
        self._last_start = now

        latencies: list[float] = []
        for i in range(count):
            start = time.perf_counter()
            try:
                _reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, _PORT), timeout=_CONNECT_TIMEOUT
                )
                elapsed = (time.perf_counter() - start) * 1000
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
                latencies.append(elapsed)
            except (asyncio.TimeoutError, OSError):
                pass
            if i < count - 1:
                await asyncio.sleep(0.2)

        received = len(latencies)
        loss_pct = round((count - received) / count * 100, 1)
        structured = {
            "host": host,
            "port": _PORT,
            "mode": "tcp_connect",
            "sent": count,
            "received": received,
            "loss_pct": loss_pct,
        }
        if not latencies:
            return ToolResult(
                status="failed",
                output=f"{host} 探测失败：{_PORT} 端口 {_CONNECT_TIMEOUT:g} 秒内均未连通（丢包率 100%）",
                structured=structured,
            )
        avg_ms = sum(latencies) / received
        structured["min_ms"] = round(min(latencies), 1)
        structured["avg_ms"] = round(avg_ms, 1)
        structured["max_ms"] = round(max(latencies), 1)
        output = (
            f"{host} 探测成功：{received}/{count} 次连通，"
            f"平均延迟 {avg_ms:.1f} ms（最小 {min(latencies):.1f}，最大 {max(latencies):.1f}），"
            f"丢包率 {loss_pct:.0f}%"
        )
        return ToolResult(status="success", output=output, structured=structured)
