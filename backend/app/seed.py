"""预置演示数据：一门计算机网络课、6 章、18 个知识点、21 条关系、3 份课件。

图谱由"课程大纲 + 概念表"确定性构建，不依赖模型自动抽取，保证演示效果稳定。
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import SessionFactory
from app.models import Chapter, Chunk, Concept, ConceptEdge, Course, Document
from app.util import new_id

COURSE_ID = "course_cn"
COURSE_TITLE = "计算机网络"

CHAPTERS = [
    ("ch_01", "分层模型", 0),
    ("ch_02", "数据链路层", 1),
    ("ch_03", "网络层", 2),
    ("ch_04", "传输层", 3),
    ("ch_05", "应用层", 4),
    ("ch_06", "网络安全", 5),
]

# id, chapter, title, description
CONCEPTS = [
    ("osi", "ch_01", "OSI 七层模型", "将网络通信划分为物理层、数据链路层、网络层、传输层、会话层、表示层和应用层，是分析协议栈的通用框架。"),
    ("ethernet", "ch_02", "以太网", "IEEE 802.3 定义的局域网技术，使用 CSMA/CD（半双工）或全双工交换，帧格式含前导码、目的/源 MAC 与 FCS。"),
    ("csma", "ch_02", "CSMA/CD", "载波监听多路访问/冲突检测。发送前监听信道，冲突时停止并退避重发；全双工交换网络中不再需要。"),
    ("mac", "ch_02", "MAC 地址", "48 位链路层地址，前 24 位为厂商 OUI。用于同一广播域内的帧交付。"),
    ("arp", "ch_02", "ARP", "在同一局域网内把 IPv4 地址解析为 MAC 地址，通过广播请求、单播应答维护 ARP 缓存。"),
    ("ipv4", "ch_03", "IPv4", "32 位地址的网络层协议，提供无连接、尽力而为的分组交付。地址由网络位与主机位组成。"),
    ("mask", "ch_03", "子网掩码", "与 IPv4 地址按位与，得到网络地址。掩码中 1 的个数即前缀长度。"),
    ("cidr", "ch_03", "CIDR", "无类别域间路由，用 /n 前缀表示网络范围，支持路由聚合，替代传统的 A/B/C 类划分。"),
    ("route", "ch_03", "路由表", "目的网络、下一跳、出接口与度量值组成；转发时按最长前缀匹配选择条目。"),
    ("nat", "ch_03", "NAT", "在私有地址与公网地址之间转换，缓解 IPv4 地址枯竭；破坏端到端语义，需要穿透机制。"),
    ("icmp", "ch_03", "ICMP", "承载网络层差错与控制报文，ping 使用 Echo Request/Reply，traceroute 依赖 TTL 超时报文。"),
    ("tcp", "ch_04", "TCP", "面向连接的传输层协议，提供可靠、有序、流量控制与拥塞控制的字节流服务。"),
    ("handshake", "ch_04", "三次握手", "SYN → SYN+ACK → ACK，双方同步初始序号并确认彼此可达，避免历史重复连接被误接受。"),
    ("congestion", "ch_04", "拥塞控制", "慢启动、拥塞避免、快重传与快恢复；通过 cwnd 调节发送速率，避免网络进入拥塞崩溃。"),
    ("udp", "ch_04", "UDP", "无连接传输协议，只有端口与校验和，适合实时音视频与 DNS 等可容忍丢包的场景。"),
    ("dns", "ch_05", "DNS", "把域名解析为地址，采用分布式层级命名系统，递归查询与迭代查询配合使用。"),
    ("http", "ch_05", "HTTP", "应用层请求/响应协议，HTTP/1.1 持久连接、HTTP/2 多路复用、HTTP/3 基于 QUIC。"),
    ("tls", "ch_05", "TLS", "在传输层之上提供加密、身份认证与完整性保护，HTTPS 即 HTTP over TLS。"),
]

EDGES = [
    ("osi", "ethernet", "contains"),
    ("osi", "ipv4", "contains"),
    ("osi", "tcp", "contains"),
    ("osi", "http", "contains"),
    ("ethernet", "csma", "related"),
    ("ethernet", "mac", "related"),
    ("mac", "arp", "prerequisite"),
    ("arp", "ipv4", "prerequisite"),
    ("ipv4", "mask", "contains"),
    ("mask", "cidr", "prerequisite"),
    ("ipv4", "route", "prerequisite"),
    ("route", "nat", "related"),
    ("route", "icmp", "related"),
    ("ipv4", "tcp", "prerequisite"),
    ("ipv4", "udp", "prerequisite"),
    ("tcp", "handshake", "contains"),
    ("tcp", "congestion", "contains"),
    ("tcp", "http", "prerequisite"),
    ("http", "tls", "related"),
    ("dns", "http", "prerequisite"),
    ("udp", "dns", "related"),
]

# 文档：标题、文件名、mime、章节、分块（section_path, page, text）
SEED_DOCUMENTS = [
    {
        "id": "doc_seed_01",
        "title": "计算机网络（第 8 版）第 4 章：网络层",
        "filename": "chapter4-network-layer.md",
        "mime": "text/markdown",
        "chapter_id": "ch_03",
        "chunks": [
            (
                ["4.3 IPv4"],
                None,
                "IPv4 地址长度为 32 位，通常写成四个十进制数，以点分隔。地址结构由网络位与主机位组成，"
                "网络位标识所属网络，主机位标识网络内的主机。IPv4 提供无连接、尽力而为的交付服务，"
                "不保证顺序、不保证到达，可靠性由上层协议负责。",
            ),
            (
                ["4.4 子网划分"],
                None,
                "子网掩码与地址按位与运算得到网络地址。若掩码为 /27，则块大小为 2^(32-27)=32 个地址，"
                "其中第一个是网络地址、最后一个是广播地址，可用主机数为 30。计算时应先确定块大小，"
                "再判断给定地址落在哪个块内，而不是凭感觉取整。",
            ),
            (
                ["4.5 CIDR"],
                None,
                "CIDR 用 /n 前缀表示网络范围，不再依赖 A/B/C 类地址。路由聚合把多个连续网段合并成更短前缀，"
                "例如 192.168.0.0/24 到 192.168.3.0/24 可以聚合为 192.168.0.0/22。聚合要求网段连续且起始地址对齐。",
            ),
            (
                ["4.6 路由与转发"],
                None,
                "路由表条目包含目的网络、下一跳、出接口和度量值。收到分组后按最长前缀匹配选择条目："
                "前缀越长越具体，优先级越高。默认路由 0.0.0.0/0 作为兜底。NAT 在私有地址与公网地址之间转换，"
                "破坏了端到端语义，因此需要 STUN、TURN 等穿透机制配合。",
            ),
        ],
    },
    {
        "id": "doc_seed_02",
        "title": "RFC 950：Internet 子网划分流程",
        "filename": "rfc950-subnet.md",
        "mime": "text/markdown",
        "chapter_id": "ch_03",
        "chunks": [
            (
                ["RFC 950", "子网划分"],
                None,
                "子网划分把一个大网络拆成若干更小的网络。路由器需要知道每个子网的网络地址与掩码，"
                "主机需要配置正确的掩码才能判断目的地址是否在同一子网。划分子网后，广播域随之缩小，"
                "ARP 广播只在本子网内传播。",
            ),
            (
                ["RFC 950", "边界情况"],
                None,
                "/31 用于点对点链路，两个地址都可以作为主机地址，没有广播地址；/32 表示单个主机路由。"
                "这两种情况不能套用常规的“排除网络地址与广播地址”公式，计算工具必须显式声明地址约定。",
            ),
            (
                ["RFC 950", "常见错误"],
                None,
                "常见错误包括：把网络地址当成可用主机、把广播地址算成最后一个可用地址、忘记块大小必须整除，"
                "以及在前缀变化后仍沿用旧的网络地址。验证方法是用网络地址加上块大小减一得到广播地址，"
                "再检查给定地址是否落在区间 [网络地址, 广播地址] 内。",
            ),
        ],
    },
    {
        "id": "doc_seed_03",
        "title": "子网划分实验手册（含 12 组练习）",
        "filename": "subnet-lab.md",
        "mime": "text/markdown",
        "chapter_id": "ch_03",
        "chunks": [
            (
                ["实验一", "给定地址求网络信息"],
                None,
                "题目：计算 192.168.10.137/27 的网络地址、广播地址、首个与最后一个可用主机地址、可用主机数。"
                "步骤：块大小 32；137 除以 32 得 4 余 9，因此网络地址为 192.168.10.128；广播地址为 192.168.10.159；"
                "可用范围 192.168.10.129 到 192.168.10.158，共 30 个地址。",
            ),
            (
                ["实验二", "前缀追问"],
                None,
                "把上题前缀改为 /28：块大小 16，137 落在 128 到 143 之间，网络地址 192.168.10.128，"
                "广播地址 192.168.10.143，可用主机 14 个。可以看到前缀每增加 1 位，块大小减半、可用主机数约减半。",
            ),
            (
                ["实验三", "路由聚合"],
                None,
                "给定 192.168.4.0/24、192.168.5.0/24、192.168.6.0/24、192.168.7.0/24，"
                "它们连续且从 4 的倍数开始，可聚合为 192.168.4.0/22。若只聚合前两个，则得到 192.168.4.0/23。"
                "聚合前必须检查起始地址是否对齐到聚合后的块大小。",
            ),
        ],
    },
]


async def seed_if_empty() -> None:
    async with SessionFactory() as session:
        existing = await session.scalar(select(Course).where(Course.id == COURSE_ID))
        if existing:
            return

        session.add(
            Course(
                id=COURSE_ID,
                title=COURSE_TITLE,
                description="从分层模型到应用层，围绕协议、地址与转发组织的一门课程。",
            )
        )
        for chapter_id, title, order in CHAPTERS:
            session.add(
                Chapter(
                    id=chapter_id,
                    course_id=COURSE_ID,
                    parent_id=None,
                    title=title,
                    sort_order=order,
                )
            )
        for index, (cid, chapter_id, title, description) in enumerate(CONCEPTS):
            session.add(
                Concept(
                    id=cid,
                    course_id=COURSE_ID,
                    chapter_id=chapter_id,
                    code=cid,
                    title=title,
                    description=description,
                    sort_order=index,
                )
            )
        for source, target, kind in EDGES:
            session.add(
                ConceptEdge(
                    id=new_id(),
                    course_id=COURSE_ID,
                    source_id=source,
                    target_id=target,
                    kind=kind,
                )
            )

        for doc in SEED_DOCUMENTS:
            document = Document(
                id=doc["id"],
                course_id=COURSE_ID,
                chapter_id=doc["chapter_id"],
                title=doc["title"],
                filename=doc["filename"],
                mime=doc["mime"],
                size=sum(len(c[2].encode("utf-8")) for c in doc["chunks"]),
                status="ready",
                chunk_count=len(doc["chunks"]),
            )
            session.add(document)
            for ordinal, (section_path, page, text) in enumerate(doc["chunks"]):
                session.add(
                    Chunk(
                        id=new_id(),
                        document_id=document.id,
                        ordinal=ordinal,
                        section_path=section_path,
                        page=page,
                        text=text,
                    )
                )

        await session.commit()
