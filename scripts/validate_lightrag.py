"""Task 1.2 验收脚本：插入两段课程文本 → hybrid 查询 → 检查存储文件。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.rag import lightrag_factory as factory

TEXT_1 = """# 第5章 传输层

传输层为运行在不同主机上的应用进程提供逻辑通信，是端到端的层次。

## 5.1 UDP

UDP（用户数据报协议）是无连接的传输层协议，仅提供复用、分用与差错检测。
UDP 首部只有 8 字节，包含源端口、目的端口、长度和校验和四个字段。
UDP 不保证可靠交付，也不使用拥塞控制，适合实时音视频等应用。

## 5.2 TCP

TCP（传输控制协议）是面向连接的、可靠的传输层协议。
TCP 通过三次握手建立连接：客户端发送 SYN，服务器回复 SYN+ACK，客户端再发送 ACK。
TCP 使用滑动窗口机制实现流量控制，通过拥塞控制算法（慢开始、拥塞避免、快重传、快恢复）防止网络过载。
TCP 通过序号、确认和重传保证可靠传输，四次挥手释放连接。
"""

TEXT_2 = """# 4.3 网络层编址

IPv4 地址长度 32 位，采用点分十进制表示。
子网掩码用于区分网络部分与主机部分，CIDR 记法如 192.168.1.0/24 表示前 24 位是网络前缀。
可用主机数等于 2 的主机位数次方减 2，其中全 0 是网络地址、全 1 是广播地址。
路由器转发分组时使用最长前缀匹配原则：在路由表中选择前缀最长的匹配表项。
默认路由 0.0.0.0/0 在没有任何匹配时兜底。
私网地址段包括 10.0.0.0/8、172.16.0.0/12 和 192.168.0.0/16，不会在公网路由。
"""


async def main() -> None:
    settings = get_settings()
    print(f"LLM={settings.LLM_MODEL} EMBEDDING={settings.EMBEDDING_MODEL}")

    await factory.init_lightrag()
    print("-- ainsert 文本1（传输层）")
    await factory.ainsert_text(TEXT_1, "doc_test1", "第5章-传输层.md")
    print("-- ainsert 文本2（网络层编址）")
    await factory.ainsert_text(TEXT_2, "doc_test2", "4.3-网络层编址.md")

    print("-- hybrid 查询")
    answer = await factory.aquery("TCP 和 UDP 的主要区别是什么？", mode="hybrid")
    print("=== 回答 ===")
    print(answer[:600])

    ctx = await factory.aquery_context("子网掩码的作用", mode="local")
    chunks = ctx.get("chunks", []) if isinstance(ctx, dict) else []
    print(f"=== 结构化检索 chunks={len(chunks)} ===")

    nodes, edges = await factory.get_graph_snapshot()
    print(f"=== 图谱 nodes={len(nodes)} edges={len(edges)} ===")

    wd = Path(settings.LIGHTRAG_WORKING_DIR)
    files = sorted(p.name for p in wd.glob("*"))
    print("=== 存储文件 ===")
    for name in files:
        print("  ", name)

    await factory.close_lightrag()
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
