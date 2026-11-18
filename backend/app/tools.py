"""纯计算与查询工具：子网计算、知识点读取、图谱邻接。均不访问网络与数据库之外的状态。"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, ConceptEdge


@dataclass
class ToolResult:
    status: str  # ok / empty / invalid_input / unavailable / denied
    data: dict
    elapsed_ms: int
    error_code: str | None = None

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "data": self.data,
            "error_code": self.error_code,
            "elapsed_ms": self.elapsed_ms,
        }


def subnet(ip: str, prefix: int, address_policy: str = "traditional_lan") -> ToolResult:
    started = time.perf_counter()
    try:
        address = ipaddress.IPv4Address(ip.strip())
    except ValueError:
        return ToolResult(
            "invalid_input", {}, int((time.perf_counter() - started) * 1000), "INVALID_IPV4"
        )
    if not 0 <= prefix <= 32:
        return ToolResult(
            "invalid_input", {}, int((time.perf_counter() - started) * 1000), "INVALID_PREFIX"
        )

    if prefix in (31, 32) and address_policy == "traditional_lan":
        return ToolResult(
            "invalid_input",
            {"hint": "/31 与 /32 不能套用常规主机公式，请选择 point_to_point 或 host_route"},
            int((time.perf_counter() - started) * 1000),
            "ADDRESS_POLICY_REQUIRED",
        )

    network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    network_address = str(network.network_address)
    mask = str(network.netmask)
    warnings: list[str] = []

    if prefix <= 30:
        broadcast_address: str | None = str(network.broadcast_address)
        first_host: str | None = str(network.network_address + 1)
        last_host: str | None = str(network.broadcast_address - 1)
        usable = network.num_addresses - 2
    elif prefix == 31:
        if address_policy != "point_to_point":
            return ToolResult(
                "invalid_input", {}, int((time.perf_counter() - started) * 1000), "ADDRESS_POLICY_MISMATCH"
            )
        broadcast_address = None
        first_host = str(network.network_address)
        last_host = str(network.broadcast_address)
        usable = 2
        warnings.append("/31 为点对点链路，两个地址均可用，没有广播地址")
    else:
        if address_policy != "host_route":
            return ToolResult(
                "invalid_input", {}, int((time.perf_counter() - started) * 1000), "ADDRESS_POLICY_MISMATCH"
            )
        broadcast_address = None
        first_host = last_host = str(network.network_address)
        usable = 1
        warnings.append("/32 为主机路由，仅一个地址")

    if prefix <= 30 and address != network.network_address:
        warnings.append("输入地址含主机位，已按掩码归一化为网络地址")

    return ToolResult(
        "ok",
        {
            "ip": str(address),
            "prefix": prefix,
            "mask": mask,
            "network_address": network_address,
            "broadcast_address": broadcast_address,
            "first_host": first_host,
            "last_host": last_host,
            "usable_host_count": usable,
            "block_size": network.num_addresses,
            "address_policy": address_policy,
            "gateway": None,
            "warnings": warnings,
        },
        int((time.perf_counter() - started) * 1000),
    )


async def get_concept(session: AsyncSession, concept_id: str) -> ToolResult:
    started = time.perf_counter()
    concept = await session.scalar(select(Concept).where(Concept.id == concept_id))
    if not concept:
        return ToolResult("empty", {}, int((time.perf_counter() - started) * 1000), "CONCEPT_NOT_FOUND")
    edges = (
        await session.execute(
            select(ConceptEdge).where(
                (ConceptEdge.source_id == concept_id) | (ConceptEdge.target_id == concept_id)
            )
        )
    ).scalars().all()
    return ToolResult(
        "ok",
        {
            "id": concept.id,
            "title": concept.title,
            "description": concept.description,
            "chapter_id": concept.chapter_id,
            "edges": [
                {"source": e.source_id, "target": e.target_id, "kind": e.kind} for e in edges
            ],
        },
        int((time.perf_counter() - started) * 1000),
    )
