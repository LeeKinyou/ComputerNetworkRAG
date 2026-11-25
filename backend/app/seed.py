"""预置演示数据：一门计算机网络课、6 章、20 个知识点、23 条关系、3 份课件。

图谱由"课程大纲 + 概念表"确定性构建，不依赖模型自动抽取，保证演示效果稳定。
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update

from app.db import SessionFactory
from app.models import (
    Assignment,
    AssignmentItem,
    Chapter,
    Chunk,
    Concept,
    ConceptEdge,
    Course,
    Document,
    Question,
    User,
)
from app.util import new_id, utcnow

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
    ("crypto", "ch_06", "对称与非对称加密", "对称加密用同一密钥、速度快，适合批量数据；非对称加密公私钥分离，便于密钥分发与数字签名，但运算开销大。"),
    ("firewall", "ch_06", "防火墙", "位于内外网边界实施访问控制：包过滤按源/目的地址、端口与协议在网络层与传输层筛选，应用层代理则深入到内容。"),
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
    ("crypto", "tls", "prerequisite"),
    ("firewall", "tls", "related"),
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


# 题库：单选与判断，覆盖 6 章。answer 只存选项 key（单选 A-D、判断 T/F）。
QUESTIONS = [
    {
        "id": "q_ch1_01",
        "chapter_id": "ch_01",
        "concept_id": "osi",
        "type": "single",
        "stem": "OSI 七层模型中，负责为主机之间提供端到端可靠传输的是哪一层？",
        "options": [
            {"key": "A", "text": "网络层"},
            {"key": "B", "text": "传输层"},
            {"key": "C", "text": "数据链路层"},
            {"key": "D", "text": "会话层"},
        ],
        "answer": "B",
        "explanation": "传输层通过 TCP 提供端到端的可靠传输；网络层负责分组转发与路由选择，不保证可靠交付。",
        "source": "教材 §1.2 分层模型",
        "difficulty": "easy",
    },
    {
        "id": "q_ch1_02",
        "chapter_id": "ch_01",
        "concept_id": "osi",
        "type": "judge",
        "stem": "在 OSI 模型中，路由选择发生在数据链路层。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "F",
        "explanation": "路由选择属于网络层的职责；数据链路层只负责相邻节点之间的帧传输与差错检测。",
        "source": "教材 §1.2 分层模型",
        "difficulty": "easy",
    },
    {
        "id": "q_ch1_03",
        "chapter_id": "ch_01",
        "concept_id": "osi",
        "type": "single",
        "stem": "TCP/IP 四层模型中不包含下列哪一层？",
        "options": [
            {"key": "A", "text": "应用层"},
            {"key": "B", "text": "传输层"},
            {"key": "C", "text": "网际层"},
            {"key": "D", "text": "表示层"},
        ],
        "answer": "D",
        "explanation": "TCP/IP 四层为应用层、传输层、网际层和网络接口层；表示层与会话层只存在于 OSI 七层模型。",
        "source": "教材 §1.3 TCP/IP 体系",
        "difficulty": "medium",
    },
    {
        "id": "q_ch1_04",
        "chapter_id": "ch_01",
        "concept_id": "osi",
        "type": "judge",
        "stem": "数据从应用层向下发送时，会依次封装为 TCP 段、IP 包和以太网帧。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "每层在数据前加上本层首部：传输层加 TCP 首部形成段，网络层加 IP 首部形成包，链路层加帧首尾形成帧。",
        "source": "教材 §1.4 封装与解封装",
        "difficulty": "easy",
    },
    {
        "id": "q_ch2_01",
        "chapter_id": "ch_02",
        "concept_id": "mac",
        "type": "single",
        "stem": "MAC 地址的长度是多少位？",
        "options": [
            {"key": "A", "text": "32 位"},
            {"key": "B", "text": "48 位"},
            {"key": "C", "text": "64 位"},
            {"key": "D", "text": "128 位"},
        ],
        "answer": "B",
        "explanation": "MAC 地址为 48 位，前 24 位是厂商 OUI，后 24 位由厂商分配；它只在同一广播域内用于帧的交付。",
        "source": "教材 §2.3 MAC 地址",
        "difficulty": "easy",
    },
    {
        "id": "q_ch2_02",
        "chapter_id": "ch_02",
        "concept_id": "csma",
        "type": "single",
        "stem": "CSMA/CD 主要用于下列哪种场景？",
        "options": [
            {"key": "A", "text": "全双工交换式以太网"},
            {"key": "B", "text": "半双工共享介质以太网"},
            {"key": "C", "text": "无线局域网"},
            {"key": "D", "text": "点对点光纤链路"},
        ],
        "answer": "B",
        "explanation": "CSMA/CD 依赖共享介质上的冲突检测；全双工交换网络中每条链路独立，不再需要冲突检测。",
        "source": "教材 §2.4 CSMA/CD",
        "difficulty": "medium",
    },
    {
        "id": "q_ch2_03",
        "chapter_id": "ch_02",
        "concept_id": "arp",
        "type": "single",
        "stem": "ARP 协议的作用是什么？",
        "options": [
            {"key": "A", "text": "把域名解析为 IP 地址"},
            {"key": "B", "text": "把 IP 地址解析为 MAC 地址"},
            {"key": "C", "text": "动态分配 IP 地址"},
            {"key": "D", "text": "计算子网掩码"},
        ],
        "answer": "B",
        "explanation": "ARP 在同一局域网内广播请求，把 IPv4 地址解析为 MAC 地址；域名解析由 DNS 完成，地址分配由 DHCP 完成。",
        "source": "教材 §2.5 ARP",
        "difficulty": "easy",
    },
    {
        "id": "q_ch2_04",
        "chapter_id": "ch_02",
        "concept_id": "arp",
        "type": "judge",
        "stem": "在同一个广播域内，ARP 请求通常以广播方式发送。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "请求方不知道目标的 MAC 地址，只能广播询问；收到请求的目标主机再以单播方式应答。",
        "source": "教材 §2.5 ARP",
        "difficulty": "easy",
    },
    {
        "id": "q_ch3_01",
        "chapter_id": "ch_03",
        "concept_id": "mask",
        "type": "single",
        "stem": "192.168.10.137/27 的网络地址是下列哪一个？",
        "options": [
            {"key": "A", "text": "192.168.10.0"},
            {"key": "B", "text": "192.168.10.128"},
            {"key": "C", "text": "192.168.10.136"},
            {"key": "D", "text": "192.168.10.160"},
        ],
        "answer": "B",
        "explanation": "/27 的块大小为 32，137 落在 128–159 这一块，因此网络地址是 192.168.10.128，广播地址是 192.168.10.159。",
        "source": "实验手册 实验一",
        "difficulty": "medium",
    },
    {
        "id": "q_ch3_02",
        "chapter_id": "ch_03",
        "concept_id": "mask",
        "type": "single",
        "stem": "一个 /28 子网可用的主机地址数量是多少？",
        "options": [
            {"key": "A", "text": "14 个"},
            {"key": "B", "text": "15 个"},
            {"key": "C", "text": "16 个"},
            {"key": "D", "text": "30 个"},
        ],
        "answer": "A",
        "explanation": "/28 共 16 个地址，去掉网络地址与广播地址后剩 14 个可用主机地址。",
        "source": "实验手册 实验二",
        "difficulty": "medium",
    },
    {
        "id": "q_ch3_03",
        "chapter_id": "ch_03",
        "concept_id": "route",
        "type": "judge",
        "stem": "最长前缀匹配时，前缀越长表示条目越具体，优先级越高。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "路由器在多个匹配条目中选择前缀最长的一条；默认路由 0.0.0.0/0 前缀最短，只作兜底。",
        "source": "教材 §4.6 路由与转发",
        "difficulty": "easy",
    },
    {
        "id": "q_ch3_04",
        "chapter_id": "ch_03",
        "concept_id": "nat",
        "type": "single",
        "stem": "下列哪一个是 IPv4 的私有地址段？",
        "options": [
            {"key": "A", "text": "8.8.8.0/24"},
            {"key": "B", "text": "10.0.0.0/8"},
            {"key": "C", "text": "203.0.113.0/24"},
            {"key": "D", "text": "192.0.2.0/24"},
        ],
        "answer": "B",
        "explanation": "私有地址段包括 10.0.0.0/8、172.16.0.0/12 和 192.168.0.0/16；其余选项是公网地址或文档示例段。",
        "source": "教材 §4.7 NAT 与私有地址",
        "difficulty": "medium",
    },
    {
        "id": "q_ch4_01",
        "chapter_id": "ch_04",
        "concept_id": "handshake",
        "type": "single",
        "stem": "TCP 三次握手的第二个报文是什么？",
        "options": [
            {"key": "A", "text": "SYN"},
            {"key": "B", "text": "SYN + ACK"},
            {"key": "C", "text": "ACK"},
            {"key": "D", "text": "FIN"},
        ],
        "answer": "B",
        "explanation": "握手顺序为 SYN → SYN+ACK → ACK：服务端在第二个报文中同时确认客户端序号并同步自己的初始序号。",
        "source": "教材 §5.3 三次握手",
        "difficulty": "easy",
    },
    {
        "id": "q_ch4_02",
        "chapter_id": "ch_04",
        "concept_id": "udp",
        "type": "judge",
        "stem": "UDP 提供可靠传输与丢包重传机制。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "F",
        "explanation": "UDP 只提供端口复用与校验和，不保证到达、顺序或重传；可靠性需要应用层自行实现。",
        "source": "教材 §5.4 UDP",
        "difficulty": "easy",
    },
    {
        "id": "q_ch4_03",
        "chapter_id": "ch_04",
        "concept_id": "congestion",
        "type": "single",
        "stem": "TCP 慢启动阶段，拥塞窗口 cwnd 的变化趋势是什么？",
        "options": [
            {"key": "A", "text": "线性增长"},
            {"key": "B", "text": "指数增长"},
            {"key": "C", "text": "保持不变"},
            {"key": "D", "text": "立即减半"},
        ],
        "answer": "B",
        "explanation": "慢启动阶段每收到一个 ACK 就把 cwnd 加一，实际效果是每个 RTT 翻倍，呈指数增长；达到阈值后进入拥塞避免的线性增长。",
        "source": "教材 §5.5 拥塞控制",
        "difficulty": "medium",
    },
    {
        "id": "q_ch4_04",
        "chapter_id": "ch_04",
        "concept_id": "tcp",
        "type": "judge",
        "stem": "TCP 是面向字节流的协议，不保留应用层的消息边界。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "TCP 按字节编号与确认，多个发送可能被合并或拆分，应用层需要自己约定消息边界。",
        "source": "教材 §5.2 TCP 服务模型",
        "difficulty": "medium",
    },
    {
        "id": "q_ch5_01",
        "chapter_id": "ch_05",
        "concept_id": "http",
        "type": "single",
        "stem": "HTTP/2 相对 HTTP/1.1 的主要改进是什么？",
        "options": [
            {"key": "A", "text": "强制使用加密"},
            {"key": "B", "text": "在一条连接上多路复用多个请求"},
            {"key": "C", "text": "取消请求头"},
            {"key": "D", "text": "每次请求都新建连接"},
        ],
        "answer": "B",
        "explanation": "HTTP/2 引入二进制分帧与多路复用，多个请求共享一条连接，避免队头阻塞；加密并非协议强制。",
        "source": "教材 §6.2 HTTP 演进",
        "difficulty": "medium",
    },
    {
        "id": "q_ch5_02",
        "chapter_id": "ch_05",
        "concept_id": "dns",
        "type": "single",
        "stem": "DNS 服务默认使用的端口是多少？",
        "options": [
            {"key": "A", "text": "21"},
            {"key": "B", "text": "53"},
            {"key": "C", "text": "80"},
            {"key": "D", "text": "443"},
        ],
        "answer": "B",
        "explanation": "DNS 默认使用 53 端口，通常基于 UDP，响应过大时切换到 TCP。",
        "source": "教材 §6.1 DNS",
        "difficulty": "easy",
    },
    {
        "id": "q_ch5_03",
        "chapter_id": "ch_05",
        "concept_id": "tls",
        "type": "judge",
        "stem": "HTTPS 是 HTTP over TLS，由 TLS 提供加密、完整性校验与身份认证。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "HTTPS 在 HTTP 与 TCP 之间加入 TLS，证书用于身份认证，握手协商出会话密钥用于加密与完整性保护。",
        "source": "教材 §6.4 HTTPS",
        "difficulty": "easy",
    },
    {
        "id": "q_ch5_04",
        "chapter_id": "ch_05",
        "concept_id": "http",
        "type": "single",
        "stem": "HTTP 状态码 404 表示什么？",
        "options": [
            {"key": "A", "text": "请求成功"},
            {"key": "B", "text": "需要身份认证"},
            {"key": "C", "text": "请求的资源不存在"},
            {"key": "D", "text": "服务器内部错误"},
        ],
        "answer": "C",
        "explanation": "404 Not Found 表示服务器找不到请求的资源；401 表示未认证，500 表示服务器内部错误。",
        "source": "教材 §6.2 HTTP 状态码",
        "difficulty": "easy",
    },
    {
        "id": "q_ch6_01",
        "chapter_id": "ch_06",
        "concept_id": "tls",
        "type": "single",
        "stem": "TLS 不提供下列哪项能力？",
        "options": [
            {"key": "A", "text": "加密传输内容"},
            {"key": "B", "text": "校验数据完整性"},
            {"key": "C", "text": "认证服务器身份"},
            {"key": "D", "text": "选择数据包的路由路径"},
        ],
        "answer": "D",
        "explanation": "TLS 提供机密性、完整性与身份认证；路由选择属于网络层，与 TLS 无关。",
        "source": "教材 §7.3 TLS",
        "difficulty": "easy",
    },
    {
        "id": "q_ch6_02",
        "chapter_id": "ch_06",
        "concept_id": "tls",
        "type": "judge",
        "stem": "数字证书的作用是把公钥与身份绑定，并由可信 CA 签名。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "证书把主体身份与公钥绑定，CA 用私钥签名；客户端用内置的 CA 公钥验证签名，从而确认公钥归属。",
        "source": "教材 §7.4 证书体系",
        "difficulty": "medium",
    },
    {
        "id": "q_ch6_03",
        "chapter_id": "ch_06",
        "concept_id": "crypto",
        "type": "single",
        "stem": "对称加密相比非对称加密的主要优势是什么？",
        "options": [
            {"key": "A", "text": "密钥分发更容易"},
            {"key": "B", "text": "加解密速度更快"},
            {"key": "C", "text": "完全不需要密钥"},
            {"key": "D", "text": "可以直接提供数字签名"},
        ],
        "answer": "B",
        "explanation": "对称算法运算量小、速度快，适合大量数据；但密钥分发困难，实际协议通常用非对称算法协商会话密钥。",
        "source": "教材 §7.2 对称与非对称",
        "difficulty": "medium",
    },
    {
        "id": "q_ch6_04",
        "chapter_id": "ch_06",
        "concept_id": "firewall",
        "type": "judge",
        "stem": "防火墙只能部署在应用层，无法在网络层过滤流量。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "F",
        "explanation": "包过滤防火墙工作在网络层与传输层，按源/目的地址、端口和协议过滤；应用层防火墙则是另一类实现。",
        "source": "教材 §7.5 防火墙",
        "difficulty": "hard",
    },
    {
        "id": "q_ch1_05",
        "chapter_id": "ch_01",
        "concept_id": "ethernet",
        "type": "single",
        "stem": "下图是以太网 V2 帧的字段结构。数据字段最小为 46 字节，主要是为了保证什么？",
        "image_url": "/media/questions/ethernet-frame.svg",
        "options": [
            {"key": "A", "text": "接收方能正确校验 FCS"},
            {"key": "B", "text": "发送方在帧发送完毕前能检测到冲突"},
            {"key": "C", "text": "兼容 IPv6 的扩展首部"},
            {"key": "D", "text": "给前导码留出同步时间"},
        ],
        "answer": "B",
        "explanation": "最小帧长 64 字节 = 6+6+2+46+4。共享式以太网最远两端往返传播时延 51.2 μs，发送方必须持续发送至少 512 bit，才能在自己仍在发送时感知冲突。",
        "source": "教材 §3.2 以太网帧",
        "difficulty": "medium",
    },
    {
        "id": "q_ch1_06",
        "chapter_id": "ch_01",
        "concept_id": "osi",
        "type": "single",
        "stem": "交换机主要工作在 OSI 七层模型的哪一层？",
        "options": [
            {"key": "A", "text": "物理层"},
            {"key": "B", "text": "数据链路层"},
            {"key": "C", "text": "网络层"},
            {"key": "D", "text": "传输层"},
        ],
        "answer": "B",
        "explanation": "交换机根据 MAC 地址表转发帧，工作在数据链路层；集线器工作在物理层，路由器在网络层。",
        "source": "教材 §1.2 分层模型",
        "difficulty": "easy",
    },
    {
        "id": "q_ch1_07",
        "chapter_id": "ch_01",
        "concept_id": "ethernet",
        "type": "judge",
        "stem": "CSMA/CD 可以用于全双工交换式以太网。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "F",
        "explanation": "全双工链路的收发通道分离，不存在冲突，不需要载波监听与冲突检测；CSMA/CD 只用于半双工共享介质。",
        "source": "教材 §3.3 CSMA/CD",
        "difficulty": "medium",
    },
    {
        "id": "q_ch2_05",
        "chapter_id": "ch_02",
        "concept_id": "mac",
        "type": "single",
        "stem": "48 位 MAC 地址的前 24 位通常表示什么？",
        "options": [
            {"key": "A", "text": "主机序号"},
            {"key": "B", "text": "厂商 OUI"},
            {"key": "C", "text": "子网号"},
            {"key": "D", "text": "VLAN ID"},
        ],
        "answer": "B",
        "explanation": "前 24 位是组织唯一标识符（OUI），由 IEEE 分配给厂商；后 24 位由厂商自行分配。",
        "source": "教材 §2.2 MAC 地址",
        "difficulty": "easy",
    },
    {
        "id": "q_ch2_06",
        "chapter_id": "ch_02",
        "concept_id": "csma",
        "type": "single",
        "stem": "以太网发生第 3 次冲突后，站点从多少个时隙中随机选择退避时间？",
        "options": [
            {"key": "A", "text": "2"},
            {"key": "B", "text": "4"},
            {"key": "C", "text": "8"},
            {"key": "D", "text": "16"},
        ],
        "answer": "C",
        "explanation": "二进制指数退避第 i 次冲突从 0 ~ 2^i-1 中取值（k 最大取 10）。第 3 次冲突即 0~7，共 8 个时隙。",
        "source": "教材 §3.3 退避算法",
        "difficulty": "medium",
    },
    {
        "id": "q_ch2_07",
        "chapter_id": "ch_02",
        "concept_id": "arp",
        "type": "single",
        "stem": "主机 A 与主机 B 在同一局域网，A 的 ARP 缓存中没有 B 的 MAC 地址。下图中哪一步的描述是正确的？",
        "image_url": "/media/questions/arp-flow.svg",
        "options": [
            {"key": "A", "text": "请求是广播，响应是单播"},
            {"key": "B", "text": "请求和响应都是广播"},
            {"key": "C", "text": "请求是单播，响应是广播"},
            {"key": "D", "text": "请求和响应都是单播"},
        ],
        "answer": "A",
        "explanation": "ARP 请求以广播发送（目的 MAC 全 F），同网段主机都会收到；目标主机确认自己是被查询方后，以单播回送 MAC 地址。",
        "source": "教材 §2.5 ARP",
        "difficulty": "easy",
    },
    {
        "id": "q_ch2_08",
        "chapter_id": "ch_02",
        "concept_id": "ethernet",
        "type": "single",
        "stem": "IEEE 802.1Q VLAN 标签的长度是多少字节？",
        "options": [
            {"key": "A", "text": "2"},
            {"key": "B", "text": "4"},
            {"key": "C", "text": "6"},
            {"key": "D", "text": "8"},
        ],
        "answer": "B",
        "explanation": "802.1Q 在源 MAC 后插入 4 字节标签：2 字节 TPID（0x8100）+ 2 字节 TCI，其中包含 12 位 VLAN ID。",
        "source": "教材 §3.5 VLAN",
        "difficulty": "medium",
    },
    {
        "id": "q_ch3_05",
        "chapter_id": "ch_03",
        "concept_id": "ipv4",
        "type": "single",
        "stem": "下列哪个地址属于 IPv4 回环地址范围？",
        "options": [
            {"key": "A", "text": "10.0.0.1"},
            {"key": "B", "text": "172.16.0.1"},
            {"key": "C", "text": "127.0.0.1"},
            {"key": "D", "text": "192.168.1.1"},
        ],
        "answer": "C",
        "explanation": "127.0.0.0/8 保留给回环，本机访问自己时使用；其余三项都属于 RFC 1918 私有地址。",
        "source": "教材 §4.1 IPv4 地址",
        "difficulty": "easy",
    },
    {
        "id": "q_ch3_06",
        "chapter_id": "ch_03",
        "concept_id": "ipv4",
        "type": "single",
        "stem": "IPv4 首部中的 TTL 字段每经过一台路由器会如何处理？",
        "options": [
            {"key": "A", "text": "保持不变"},
            {"key": "B", "text": "加 1"},
            {"key": "C", "text": "减 1，减到 0 时丢弃并回 ICMP 超时"},
            {"key": "D", "text": "由目的主机统一设置"},
        ],
        "answer": "C",
        "explanation": "TTL 防止分组在网络中无限循环，每跳减 1；耗尽时路由器丢弃该分组并返回 ICMP Time Exceeded。",
        "source": "教材 §4.1 IP 首部",
        "difficulty": "medium",
    },
    {
        "id": "q_ch3_07",
        "chapter_id": "ch_03",
        "concept_id": "cidr",
        "type": "single",
        "stem": "下图中 192.168.1.4/30 网段的可用主机地址是哪些？",
        "image_url": "/media/questions/subnet-30.svg",
        "options": [
            {"key": "A", "text": "192.168.1.4 和 192.168.1.7"},
            {"key": "B", "text": "192.168.1.5 和 192.168.1.6"},
            {"key": "C", "text": "192.168.1.4 ~ 192.168.1.7"},
            {"key": "D", "text": "192.168.1.5 ~ 192.168.1.7"},
        ],
        "answer": "B",
        "explanation": "/30 掩码 255.255.255.252，块大小 4；.4 是网络地址、.7 是广播地址，只剩 .5 与 .6 可分配给主机。",
        "source": "教材 §4.3 子网划分",
        "difficulty": "medium",
    },
    {
        "id": "q_ch3_08",
        "chapter_id": "ch_03",
        "concept_id": "cidr",
        "type": "single",
        "stem": "图中四个连续 /24 网段聚合后的最简路由是哪一条？",
        "image_url": "/media/questions/route-aggregation.svg",
        "options": [
            {"key": "A", "text": "192.168.4.0/22"},
            {"key": "B", "text": "192.168.4.0/23"},
            {"key": "C", "text": "192.168.0.0/21"},
            {"key": "D", "text": "192.168.4.0/24"},
        ],
        "answer": "A",
        "explanation": "第三字节 4~7 的二进制公共前缀为 0000 01，共 22 位，因此聚合结果为 192.168.4.0/22。",
        "source": "教材 §4.4 路由聚合",
        "difficulty": "hard",
    },
    {
        "id": "q_ch3_09",
        "chapter_id": "ch_03",
        "concept_id": "icmp",
        "type": "single",
        "stem": "图中 ping 使用的 ICMP 报文类型是哪一组？",
        "image_url": "/media/questions/ping-icmp.svg",
        "options": [
            {"key": "A", "text": "Type 3 目的不可达"},
            {"key": "B", "text": "Type 8 回显请求 / Type 0 回显应答"},
            {"key": "C", "text": "Type 11 超时"},
            {"key": "D", "text": "Type 5 重定向"},
        ],
        "answer": "B",
        "explanation": "ping 发送 Echo Request（Type 8），对端返回 Echo Reply（Type 0）；Type 3/11 用于差错报告。",
        "source": "教材 §4.5 ICMP",
        "difficulty": "easy",
    },
    {
        "id": "q_ch4_05",
        "chapter_id": "ch_04",
        "concept_id": "handshake",
        "type": "single",
        "stem": "关于图中 TCP 三次握手，下列说法正确的是？",
        "image_url": "/media/questions/tcp-handshake.svg",
        "options": [
            {"key": "A", "text": "SYN 报文不占用序号"},
            {"key": "B", "text": "SYN 与 FIN 各消耗一个序号"},
            {"key": "C", "text": "第三次握手的 ACK 也消耗一个序号"},
            {"key": "D", "text": "SYN 只能由客户端发起"},
        ],
        "answer": "B",
        "explanation": "SYN 与 FIN 即使不携带数据也各消耗一个序号；纯 ACK 不消耗序号。SYN 可由任一端发起，主动打开方进入 SYN_SENT。",
        "source": "教材 §5.3 TCP 连接管理",
        "difficulty": "medium",
    },
    {
        "id": "q_ch4_06",
        "chapter_id": "ch_04",
        "concept_id": "handshake",
        "type": "judge",
        "stem": "TCP 第三次握手的 ACK 报文可以携带应用数据。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "第三次握手时连接已经建立，ACK 可以携带数据；前两次握手阶段连接尚未建立，不能携带应用数据。",
        "source": "教材 §5.3 TCP 连接管理",
        "difficulty": "medium",
    },
    {
        "id": "q_ch4_07",
        "chapter_id": "ch_04",
        "concept_id": "congestion",
        "type": "single",
        "stem": "图中慢启动阶段，拥塞窗口 cwnd 如何增长？",
        "image_url": "/media/questions/congestion-window.svg",
        "options": [
            {"key": "A", "text": "每个 RTT 加 1"},
            {"key": "B", "text": "每收到一个 ACK 加 1，约每个 RTT 翻倍"},
            {"key": "C", "text": "保持不变，直到超时"},
            {"key": "D", "text": "每个 RTT 减半"},
        ],
        "answer": "B",
        "explanation": "慢启动每收到一个 ACK 将 cwnd 加 1 个 MSS，因此约每个 RTT 翻倍；达到 ssthresh 后进入拥塞避免，改为每 RTT 线性加 1。",
        "source": "教材 §5.6 拥塞控制",
        "difficulty": "medium",
    },
    {
        "id": "q_ch4_08",
        "chapter_id": "ch_04",
        "concept_id": "tcp",
        "type": "single",
        "stem": "TCP 主动关闭方进入 TIME_WAIT 状态后通常等待多长时间？",
        "options": [
            {"key": "A", "text": "1 个 RTT"},
            {"key": "B", "text": "2MSL"},
            {"key": "C", "text": "固定 30 秒"},
            {"key": "D", "text": "由内核随机决定"},
        ],
        "answer": "B",
        "explanation": "TIME_WAIT 等待 2MSL，确保最后一个 ACK 丢失时可以重传，并让本次连接的旧报文在网络中消散，避免影响新连接。",
        "source": "教材 §5.3 连接释放",
        "difficulty": "medium",
    },
    {
        "id": "q_ch4_09",
        "chapter_id": "ch_04",
        "concept_id": "udp",
        "type": "single",
        "stem": "UDP 首部的固定长度是多少字节？",
        "options": [
            {"key": "A", "text": "4"},
            {"key": "B", "text": "8"},
            {"key": "C", "text": "12"},
            {"key": "D", "text": "20"},
        ],
        "answer": "B",
        "explanation": "UDP 首部 8 字节：源端口、目的端口、长度、校验和各 2 字节，开销远小于 TCP 的 20 字节固定首部。",
        "source": "教材 §5.2 UDP",
        "difficulty": "easy",
    },
    {
        "id": "q_ch5_05",
        "chapter_id": "ch_05",
        "concept_id": "http",
        "type": "single",
        "stem": "HTTP 响应状态码 301 表示什么含义？",
        "options": [
            {"key": "A", "text": "临时重定向"},
            {"key": "B", "text": "永久重定向"},
            {"key": "C", "text": "资源未修改"},
            {"key": "D", "text": "请求超时"},
        ],
        "answer": "B",
        "explanation": "301 Moved Permanently 表示资源永久迁移，客户端与搜索引擎应更新地址；302/307 为临时重定向，304 表示协商缓存命中。",
        "source": "教材 §6.2 HTTP 状态码",
        "difficulty": "easy",
    },
    {
        "id": "q_ch5_06",
        "chapter_id": "ch_05",
        "concept_id": "http",
        "type": "judge",
        "stem": "HTTP/2 通过二进制分帧与多路复用，可以在一条 TCP 连接上并发处理多个请求。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "HTTP/2 引入二进制分帧层、流与多路复用，多个请求的帧可以交错发送；这缓解了 HTTP/1.1 的应用层队头阻塞。",
        "source": "教材 §6.6 HTTP/2",
        "difficulty": "medium",
    },
    {
        "id": "q_ch5_07",
        "chapter_id": "ch_05",
        "concept_id": "dns",
        "type": "single",
        "stem": "图中主机向本地 DNS 服务器发起的属于哪种查询？",
        "image_url": "/media/questions/dns-query.svg",
        "options": [
            {"key": "A", "text": "迭代查询"},
            {"key": "B", "text": "递归查询"},
            {"key": "C", "text": "反向查询"},
            {"key": "D", "text": "区域传送"},
        ],
        "answer": "B",
        "explanation": "主机通常把“帮我查到底”交给本地 DNS，属于递归查询；本地 DNS 再去问根、顶级域和权威服务器时通常使用迭代查询。",
        "source": "教材 §6.4 DNS 查询方式",
        "difficulty": "medium",
    },
    {
        "id": "q_ch5_08",
        "chapter_id": "ch_05",
        "concept_id": "tls",
        "type": "judge",
        "stem": "客户端校验证书时，只要证书链能追溯到受信任的根 CA，就说明服务器身份一定可信。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "F",
        "explanation": "还需校验域名匹配、有效期、密钥用途与吊销状态。证书链可信只是必要条件；若中间 CA 签发过宽或私钥泄露，仍可能被冒充。",
        "source": "教材 §7.4 证书校验",
        "difficulty": "hard",
    },
    {
        "id": "q_ch6_05",
        "chapter_id": "ch_06",
        "concept_id": "nat",
        "type": "single",
        "stem": "图中多台内网主机共享一个公网 IP，NAT 设备主要靠什么区分不同会话？",
        "image_url": "/media/questions/nat-napt.svg",
        "options": [
            {"key": "A", "text": "MAC 地址"},
            {"key": "B", "text": "源端口号"},
            {"key": "C", "text": "IP 首部 TTL"},
            {"key": "D", "text": "目的 IP 地址"},
        ],
        "answer": "B",
        "explanation": "NAPT 把「内网 IP:端口」映射为「公网 IP:端口」，用改写后的端口区分不同内网主机的连接；这也是端口转发要指定内网地址与端口的原因。",
        "source": "教材 §4.6 NAT",
        "difficulty": "medium",
    },
    {
        "id": "q_ch6_06",
        "chapter_id": "ch_06",
        "concept_id": "route",
        "type": "judge",
        "stem": "默认路由 0.0.0.0/0 的掩码长度为 0，可以匹配任意目的地址。",
        "options": [
            {"key": "T", "text": "正确"},
            {"key": "F", "text": "错误"},
        ],
        "answer": "T",
        "explanation": "/0 表示没有网络位参与匹配，任何目的地址都能命中；默认路由通常指向出口网关，作为路由表的兜底项。",
        "source": "教材 §4.4 路由表",
        "difficulty": "easy",
    },
    {
        "id": "q_ch6_07",
        "chapter_id": "ch_06",
        "concept_id": "icmp",
        "type": "single",
        "stem": "traceroute 主要利用 ICMP 的哪种机制逐跳发现路径？",
        "options": [
            {"key": "A", "text": "ARP 广播"},
            {"key": "B", "text": "TTL 逐跳递减到 0 触发超时"},
            {"key": "C", "text": "DNS 反向解析"},
            {"key": "D", "text": "TCP 重传"},
        ],
        "answer": "B",
        "explanation": "探测包从 TTL=1 开始递增，每经过一跳 TTL 减为 0，路由器回 ICMP Time Exceeded，据此得到逐跳路径。",
        "source": "教材 §4.5 ICMP 应用",
        "difficulty": "medium",
    },
]


# 第二批知识点：在第一版 20 个核心概念上补齐每章的关键协议与机制，
# 保证图谱里每个节点都有出边或入边，不再是零散的点。
CONCEPTS += [
    ("tcpip", "ch_01", "TCP/IP 四层模型", "把协议栈划分为网络接口层、网际层、传输层与应用层，是互联网实际采用的体系结构，与 OSI 七层一一对应但更精简。"),
    ("encapsulation", "ch_01", "封装与解封装", "数据自上而下逐层加首部，接收端自下而上逐层剥离；每层只处理本层首部，实现层间解耦。"),
    ("pdu", "ch_01", "协议数据单元", "各层数据单元的统称：应用层报文、传输层段、网络层分组、链路层帧、物理层比特。"),
    ("service_mode", "ch_01", "面向连接与无连接", "面向连接先建立通路再传输并保证顺序，无连接直接发送、不维护状态，是可靠性与开销的取舍。"),
    ("rfc", "ch_01", "RFC 与标准化", "IETF 以 RFC 文档发布互联网标准，编号发布后不再改变，是协议实现与排错的权威依据。"),
    ("switch", "ch_02", "以太网交换机", "基于 MAC 地址表在端口间转发帧，冲突域隔离到每个端口，支持全双工，是现代局域网的核心设备。"),
    ("vlan", "ch_02", "VLAN", "在二层用 802.1Q 标签划分广播域，同一台物理交换机可承载多个逻辑网络，减少广播并便于隔离。"),
    ("ppp", "ch_02", "PPP", "点对点链路协议，提供帧定界、差错检测与链路建立（LCP），常用于拨号与广域网点到点连接。"),
    ("crc", "ch_02", "CRC 差错检测", "用生成多项式对帧做模 2 除法，接收端校验余数；能检出突发错误，但不能纠错。"),
    ("mtu", "ch_02", "MTU 与分片", "链路层单帧可承载的最大字节数；超过 MTU 的 IP 分组需要分片，分片增加开销且易被中间设备丢弃。"),
    ("ipv6", "ch_03", "IPv6", "128 位地址，取消首部校验和与分片字段，用扩展首部表达选项，地址空间与转发效率显著提升。"),
    ("fragment", "ch_03", "IP 分片", "按 MTU 把分组拆成片，靠标识、偏移与 MF 标志重组；任一片丢失即整包失败。"),
    ("ospf", "ch_03", "OSPF", "链路状态路由协议，泛洪拓扑后运行 Dijkstra 计算最短路径，适合大型自治系统内部。"),
    ("bgp", "ch_03", "BGP", "自治系统之间的路径向量协议，用 AS_PATH 选路并支持策略控制，是互联网骨干路由的基础。"),
    ("rip", "ch_03", "RIP", "距离向量路由协议，以跳数为度量、最大 15 跳，收敛慢，适合小型网络。"),
    ("dhcp", "ch_03", "DHCP", "自动分配 IP、掩码、网关与 DNS，基于 UDP 67/68，用租约机制回收地址。"),
    ("forwarding", "ch_03", "最长前缀匹配", "路由器按目的地址查表，选择前缀最长的条目转发；默认路由 0.0.0.0/0 作为兜底。"),
    ("flow_control", "ch_04", "流量控制", "用滑动窗口约束发送速率，避免接收端缓冲区溢出；与拥塞控制分别保护接收方和网络。"),
    ("retransmit", "ch_04", "超时重传", "发送端为报文设置定时器，超时未确认即重发；RTO 依据往返时延动态估算。"),
    ("socket", "ch_04", "端口与套接字", "端口标识主机内的进程，套接字由 IP 与端口组成，四元组唯一确定一条连接。"),
    ("quic", "ch_04", "QUIC", "基于 UDP 的传输协议，在用户态实现握手、拥塞控制与多路复用，是 HTTP/3 的底座。"),
    ("https", "ch_05", "HTTPS", "HTTP over TLS，默认 443；握手阶段协商密钥并校验证书，之后用对称加密传输。"),
    ("ftp", "ch_05", "FTP", "文件传输协议，控制连接 21 端口、数据连接另开；主动与被动模式的区别在于谁发起数据连接。"),
    ("smtp", "ch_05", "SMTP", "邮件发送协议，默认 25/587，与 POP3/IMAP 配合完成投递与读取。"),
    ("websocket", "ch_05", "WebSocket", "用 HTTP 升级握手建立全双工长连接，适合实时推送与协同编辑。"),
    ("cdn", "ch_05", "CDN", "把内容缓存到离用户更近的边缘节点，靠 DNS 调度与缓存策略降低时延和回源压力。"),
    ("proxy", "ch_05", "正向与反向代理", "正向代理代表客户端出网，反向代理代表服务端接流量，可做缓存、限流与 TLS 终止。"),
    ("http2", "ch_05", "HTTP/2", "二进制分帧、单连接多路复用、首部压缩，解决 HTTP/1.1 队头阻塞与连接数过多的问题。"),
    ("acl", "ch_06", "访问控制列表", "按五元组匹配放行或拒绝，是包过滤防火墙的核心规则集，顺序匹配、命中即停。"),
    ("ids", "ch_06", "IDS 与 IPS", "通过特征或异常检测发现入侵；IDS 只告警，IPS 串联在链路中可直接阻断。"),
    ("vpn", "ch_06", "VPN 与 IPsec", "在公网上用隧道与加密构建逻辑专网，IPsec 提供认证、加密与完整性保护。"),
    ("ddos", "ch_06", "DDoS", "用大量分布式主机耗尽带宽或连接资源；防御靠流量清洗、限速与任播分散。"),
    ("pki", "ch_06", "PKI 与数字证书", "CA 签发证书把公钥与身份绑定，靠信任链校验；证书吊销依赖 CRL 或 OCSP。"),
]

EDGES += [
    ("osi", "tcpip", "related"),
    ("osi", "encapsulation", "contains"),
    ("encapsulation", "pdu", "related"),
    ("osi", "service_mode", "contains"),
    ("tcpip", "rfc", "related"),
    ("ethernet", "switch", "prerequisite"),
    ("ethernet", "vlan", "related"),
    ("ethernet", "crc", "contains"),
    ("ethernet", "mtu", "related"),
    ("mac", "switch", "prerequisite"),
    ("switch", "vlan", "related"),
    ("switch", "mtu", "related"),
    ("ppp", "mtu", "related"),
    ("ipv4", "ipv6", "related"),
    ("ipv4", "fragment", "contains"),
    ("mask", "route", "prerequisite"),
    ("cidr", "route", "prerequisite"),
    ("route", "ospf", "contains"),
    ("route", "bgp", "contains"),
    ("route", "rip", "contains"),
    ("route", "forwarding", "contains"),
    ("ipv4", "dhcp", "related"),
    ("ipv6", "cidr", "related"),
    ("tcp", "flow_control", "contains"),
    ("tcp", "retransmit", "contains"),
    ("tcp", "socket", "related"),
    ("udp", "socket", "related"),
    ("udp", "quic", "prerequisite"),
    ("congestion", "flow_control", "related"),
    ("handshake", "retransmit", "related"),
    ("http", "https", "related"),
    ("tls", "https", "prerequisite"),
    ("http", "http2", "contains"),
    ("http", "ftp", "related"),
    ("tcp", "ftp", "prerequisite"),
    ("tcp", "smtp", "prerequisite"),
    ("http", "websocket", "prerequisite"),
    ("http", "proxy", "related"),
    ("dns", "cdn", "related"),
    ("http", "cdn", "related"),
    ("proxy", "cdn", "related"),
    ("http2", "quic", "related"),
    ("ospf", "rip", "related"),
    ("bgp", "ospf", "related"),
    ("nat", "ipv4", "related"),
    ("firewall", "acl", "contains"),
    ("firewall", "ids", "related"),
    ("firewall", "vpn", "related"),
    ("crypto", "pki", "related"),
    ("tls", "pki", "prerequisite"),
    ("ids", "ddos", "related"),
]

# 第二批题目：每个新增知识点至少一道，题库从 48 题补到 80 题。
QUESTIONS += [
    {
        "id": "q_tcpip",
        "chapter_id": "ch_01",
        "concept_id": "tcpip",
        "type": "single",
        "stem": "TCP/IP 四层模型中，IP 协议属于哪一层？",
        "options": [
            {"key": "A", "text": "网络接口层"},
            {"key": "B", "text": "网际层"},
            {"key": "C", "text": "传输层"},
            {"key": "D", "text": "应用层"},
        ],
        "answer": "B",
        "explanation": "IP 负责寻址与分组转发，位于网际层；TCP/UDP 在传输层，HTTP/DNS 在应用层。",
        "source": "教材 §1.3 TCP/IP 体系",
        "difficulty": "easy",
    },
    {
        "id": "q_encapsulation",
        "chapter_id": "ch_01",
        "concept_id": "encapsulation",
        "type": "judge",
        "stem": "封装过程中，每一层只处理本层首部，不修改上层传下来的数据内容。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "各层把上层数据整体当作载荷，只添加或剥离本层首部，从而保持层间独立。",
        "source": "教材 §1.3 封装",
        "difficulty": "easy",
    },
    {
        "id": "q_pdu",
        "chapter_id": "ch_01",
        "concept_id": "pdu",
        "type": "single",
        "stem": "网络层的数据单元通常称为什么？",
        "options": [
            {"key": "A", "text": "报文"},
            {"key": "B", "text": "段"},
            {"key": "C", "text": "分组"},
            {"key": "D", "text": "帧"},
        ],
        "answer": "C",
        "explanation": "应用层称报文、传输层称段、网络层称分组、链路层称帧。",
        "source": "教材 §1.3 PDU",
        "difficulty": "easy",
    },
    {
        "id": "q_service_mode",
        "chapter_id": "ch_01",
        "concept_id": "service_mode",
        "type": "judge",
        "stem": "无连接服务在传输数据之前必须先建立端到端连接。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "F",
        "explanation": "无连接服务直接发送分组、不维护连接状态；建立连接是面向连接服务的前提。",
        "source": "教材 §1.4 服务模型",
        "difficulty": "easy",
    },
    {
        "id": "q_switch",
        "chapter_id": "ch_02",
        "concept_id": "switch",
        "type": "single",
        "stem": "以太网交换机转发帧时主要依据什么？",
        "options": [
            {"key": "A", "text": "目的 IP 地址"},
            {"key": "B", "text": "MAC 地址表"},
            {"key": "C", "text": "TCP 端口号"},
            {"key": "D", "text": "域名"},
        ],
        "answer": "B",
        "explanation": "交换机是二层设备，学习源 MAC 并按键值查表，把帧转发到对应端口。",
        "source": "教材 §2.4 交换机",
        "difficulty": "easy",
    },
    {
        "id": "q_vlan",
        "chapter_id": "ch_02",
        "concept_id": "vlan",
        "type": "single",
        "stem": "802.1Q 标签的主要作用是什么？",
        "options": [
            {"key": "A", "text": "加密帧内容"},
            {"key": "B", "text": "标识帧所属的 VLAN"},
            {"key": "C", "text": "重传丢失的帧"},
            {"key": "D", "text": "自动分配 IP 地址"},
        ],
        "answer": "B",
        "explanation": "标签在二层帧中插入 VLAN ID，用于在同一物理链路上区分不同广播域。",
        "source": "教材 §2.5 VLAN",
        "difficulty": "medium",
    },
    {
        "id": "q_ppp",
        "chapter_id": "ch_02",
        "concept_id": "ppp",
        "type": "judge",
        "stem": "PPP 面向点对点链路设计，不用于共享介质的局域网。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "PPP 只处理两端之间的链路建立与帧定界，共享介质由以太网等协议承担。",
        "source": "教材 §2.6 PPP",
        "difficulty": "easy",
    },
    {
        "id": "q_crc",
        "chapter_id": "ch_02",
        "concept_id": "crc",
        "type": "single",
        "stem": "CRC 校验能完成什么？",
        "options": [
            {"key": "A", "text": "纠正所有传输错误"},
            {"key": "B", "text": "检出突发错误"},
            {"key": "C", "text": "对帧加密"},
            {"key": "D", "text": "压缩帧长度"},
        ],
        "answer": "B",
        "explanation": "CRC 用生成多项式求余数，检错能力强但不能定位并纠正错误，出错通常直接丢弃。",
        "source": "教材 §2.2 差错检测",
        "difficulty": "medium",
    },
    {
        "id": "q_mtu",
        "chapter_id": "ch_02",
        "concept_id": "mtu",
        "type": "judge",
        "stem": "IP 分组长度超过链路 MTU 时，必须分片或丢弃。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "链路层单帧承载能力有限，IPv4 可让路由器分片，IPv6 通常要求源端分片或返回 ICMP 差错。",
        "source": "教材 §3.3 分片",
        "difficulty": "easy",
    },
    {
        "id": "q_ipv6",
        "chapter_id": "ch_03",
        "concept_id": "ipv6",
        "type": "single",
        "stem": "IPv6 地址长度是多少位？",
        "options": [
            {"key": "A", "text": "32 位"},
            {"key": "B", "text": "48 位"},
            {"key": "C", "text": "64 位"},
            {"key": "D", "text": "128 位"},
        ],
        "answer": "D",
        "explanation": "IPv6 用 128 位地址，写成 8 组四位十六进制，地址空间远大于 IPv4。",
        "source": "教材 §4.2 IPv6",
        "difficulty": "easy",
    },
    {
        "id": "q_fragment",
        "chapter_id": "ch_03",
        "concept_id": "fragment",
        "type": "single",
        "stem": "IPv4 分片的重组通常在哪里完成？",
        "options": [
            {"key": "A", "text": "每个中间路由器"},
            {"key": "B", "text": "目的主机"},
            {"key": "C", "text": "二层交换机"},
            {"key": "D", "text": "DNS 服务器"},
        ],
        "answer": "B",
        "explanation": "分片沿路径独立转发，只有目的主机按标识、偏移与 MF 标志重组，中间设备一般不重组。",
        "source": "教材 §3.3 分片",
        "difficulty": "medium",
    },
    {
        "id": "q_ospf",
        "chapter_id": "ch_03",
        "concept_id": "ospf",
        "type": "single",
        "stem": "OSPF 属于哪一类路由协议？",
        "options": [
            {"key": "A", "text": "距离向量"},
            {"key": "B", "text": "链路状态"},
            {"key": "C", "text": "路径向量"},
            {"key": "D", "text": "静态路由"},
        ],
        "answer": "B",
        "explanation": "OSPF 泛洪链路状态、构建拓扑图后用 Dijkstra 求最短路径，属于链路状态协议。",
        "source": "教材 §4.4 OSPF",
        "difficulty": "medium",
    },
    {
        "id": "q_bgp",
        "chapter_id": "ch_03",
        "concept_id": "bgp",
        "type": "judge",
        "stem": "BGP 主要用于自治系统之间的路由选择。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "BGP 是外部网关协议，用 AS_PATH 等属性在自治系统之间选路并实施策略。",
        "source": "教材 §4.5 BGP",
        "difficulty": "easy",
    },
    {
        "id": "q_rip",
        "chapter_id": "ch_03",
        "concept_id": "rip",
        "type": "single",
        "stem": "RIP 允许的最大跳数是多少？",
        "options": [
            {"key": "A", "text": "15"},
            {"key": "B", "text": "16"},
            {"key": "C", "text": "31"},
            {"key": "D", "text": "没有限制"},
        ],
        "answer": "A",
        "explanation": "RIP 以 15 跳为最大可达，16 表示不可达，因此只适合小型网络。",
        "source": "教材 §4.4 RIP",
        "difficulty": "easy",
    },
    {
        "id": "q_dhcp",
        "chapter_id": "ch_03",
        "concept_id": "dhcp",
        "type": "single",
        "stem": "DHCP 默认使用哪一组端口？",
        "options": [
            {"key": "A", "text": "80/443"},
            {"key": "B", "text": "53"},
            {"key": "C", "text": "67/68"},
            {"key": "D", "text": "21"},
        ],
        "answer": "C",
        "explanation": "DHCP 服务端监听 UDP 67，客户端使用 UDP 68，通过广播发现并租用地址。",
        "source": "教材 §5.6 DHCP",
        "difficulty": "easy",
    },
    {
        "id": "q_forwarding",
        "chapter_id": "ch_03",
        "concept_id": "forwarding",
        "type": "judge",
        "stem": "路由器转发分组时采用最长前缀匹配。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "同一目的地址可能匹配多条路由，前缀越长越具体，因此优先选择最长前缀。",
        "source": "教材 §4.3 转发",
        "difficulty": "easy",
    },
    {
        "id": "q_flow_control",
        "chapter_id": "ch_04",
        "concept_id": "flow_control",
        "type": "single",
        "stem": "滑动窗口机制主要解决什么问题？",
        "options": [
            {"key": "A", "text": "网络拥塞"},
            {"key": "B", "text": "接收端缓冲区溢出"},
            {"key": "C", "text": "路由环路"},
            {"key": "D", "text": "帧同步"},
        ],
        "answer": "B",
        "explanation": "接收端通过通告窗口限制在途数据量，防止发送过快导致缓冲区溢出；拥塞控制保护的是网络。",
        "source": "教材 §5.4 流量控制",
        "difficulty": "medium",
    },
    {
        "id": "q_retransmit",
        "chapter_id": "ch_04",
        "concept_id": "retransmit",
        "type": "judge",
        "stem": "TCP 的超时重传定时器 RTO 是固定值，不随网络往返时延变化。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "F",
        "explanation": "RTO 依据测量的往返时延及其抖动动态估算，网络变化时会自适应调整。",
        "source": "教材 §5.5 重传",
        "difficulty": "medium",
    },
    {
        "id": "q_socket",
        "chapter_id": "ch_04",
        "concept_id": "socket",
        "type": "single",
        "stem": "唯一确定一条 TCP 连接的四元组包含哪些字段？",
        "options": [
            {"key": "A", "text": "源 IP、源端口、目的 IP、目的端口"},
            {"key": "B", "text": "仅源 IP 与目的 IP"},
            {"key": "C", "text": "仅两个端口号"},
            {"key": "D", "text": "两个 MAC 地址"},
        ],
        "answer": "A",
        "explanation": "四元组把两端地址与端口组合起来，同一端口的不同连接靠对端信息区分。",
        "source": "教材 §5.2 套接字",
        "difficulty": "easy",
    },
    {
        "id": "q_quic",
        "chapter_id": "ch_04",
        "concept_id": "quic",
        "type": "single",
        "stem": "QUIC 建立在哪种传输协议之上？",
        "options": [
            {"key": "A", "text": "TCP"},
            {"key": "B", "text": "UDP"},
            {"key": "C", "text": "ICMP"},
            {"key": "D", "text": "IP"},
        ],
        "answer": "B",
        "explanation": "QUIC 在 UDP 之上实现可靠传输、拥塞控制与多路复用，避开 TCP 的连接与队头阻塞限制。",
        "source": "教材 §6.3 QUIC",
        "difficulty": "medium",
    },
    {
        "id": "q_https",
        "chapter_id": "ch_05",
        "concept_id": "https",
        "type": "single",
        "stem": "HTTPS 的默认端口是多少？",
        "options": [
            {"key": "A", "text": "80"},
            {"key": "B", "text": "443"},
            {"key": "C", "text": "8080"},
            {"key": "D", "text": "8443"},
        ],
        "answer": "B",
        "explanation": "HTTPS 即 HTTP over TLS，IANA 分配 443 为默认端口；80 是明文 HTTP。",
        "source": "教材 §6.4 HTTPS",
        "difficulty": "easy",
    },
    {
        "id": "q_ftp",
        "chapter_id": "ch_05",
        "concept_id": "ftp",
        "type": "single",
        "stem": "FTP 的控制连接默认使用哪个端口？",
        "options": [
            {"key": "A", "text": "20"},
            {"key": "B", "text": "21"},
            {"key": "C", "text": "22"},
            {"key": "D", "text": "25"},
        ],
        "answer": "B",
        "explanation": "FTP 用 21 端口传命令与响应，数据连接在主动模式下由服务端 20 端口发起。",
        "source": "教材 §6.5 FTP",
        "difficulty": "easy",
    },
    {
        "id": "q_smtp",
        "chapter_id": "ch_05",
        "concept_id": "smtp",
        "type": "judge",
        "stem": "SMTP 负责发送邮件，读取邮件通常使用 POP3 或 IMAP。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "SMTP 把邮件投递到服务器，POP3/IMAP 供客户端下载或同步邮箱内容。",
        "source": "教材 §6.5 邮件",
        "difficulty": "easy",
    },
    {
        "id": "q_websocket",
        "chapter_id": "ch_05",
        "concept_id": "websocket",
        "type": "single",
        "stem": "WebSocket 如何建立连接？",
        "options": [
            {"key": "A", "text": "直接发送 UDP 报文"},
            {"key": "B", "text": "通过 HTTP 升级握手"},
            {"key": "C", "text": "通过邮件协商"},
            {"key": "D", "text": "依赖二层广播"},
        ],
        "answer": "B",
        "explanation": "客户端先发带 Upgrade: websocket 的 HTTP 请求，服务端返回 101 后切换为全双工协议。",
        "source": "教材 §6.6 WebSocket",
        "difficulty": "medium",
    },
    {
        "id": "q_cdn",
        "chapter_id": "ch_05",
        "concept_id": "cdn",
        "type": "single",
        "stem": "CDN 的主要目标是什么？",
        "options": [
            {"key": "A", "text": "加密传输内容"},
            {"key": "B", "text": "就近分发内容、降低时延"},
            {"key": "C", "text": "自动分配 IP 地址"},
            {"key": "D", "text": "做路由聚合"},
        ],
        "answer": "B",
        "explanation": "CDN 把内容缓存到边缘节点，靠 DNS 或任播把用户调度到最近副本，减少回源与跨网时延。",
        "source": "教材 §6.7 CDN",
        "difficulty": "easy",
    },
    {
        "id": "q_proxy",
        "chapter_id": "ch_05",
        "concept_id": "proxy",
        "type": "judge",
        "stem": "反向代理代表服务端接收客户端请求。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "反向代理部署在服务端前面，对外呈现为源站，负责转发、缓存、限流与 TLS 终止。",
        "source": "教材 §6.8 代理",
        "difficulty": "easy",
    },
    {
        "id": "q_http2",
        "chapter_id": "ch_05",
        "concept_id": "http2",
        "type": "single",
        "stem": "HTTP/2 相比 HTTP/1.1 的核心改进是什么？",
        "options": [
            {"key": "A", "text": "改为明文传输"},
            {"key": "B", "text": "单连接多路复用"},
            {"key": "C", "text": "取消 TLS 支持"},
            {"key": "D", "text": "首部改为固定长度"},
        ],
        "answer": "B",
        "explanation": "HTTP/2 用二进制分帧把多个请求复用到一条连接上，配合首部压缩缓解队头阻塞与连接开销。",
        "source": "教材 §6.2 HTTP/2",
        "difficulty": "medium",
    },
    {
        "id": "q_acl",
        "chapter_id": "ch_06",
        "concept_id": "acl",
        "type": "single",
        "stem": "包过滤防火墙的 ACL 通常不匹配以下哪个字段？",
        "options": [
            {"key": "A", "text": "源 IP 地址"},
            {"key": "B", "text": "目的端口"},
            {"key": "C", "text": "传输层协议"},
            {"key": "D", "text": "用户登录密码"},
        ],
        "answer": "D",
        "explanation": "传统 ACL 按五元组匹配，工作在网络层与传输层；用户口令属于应用层身份信息。",
        "source": "教材 §7.2 防火墙",
        "difficulty": "medium",
    },
    {
        "id": "q_ids",
        "chapter_id": "ch_06",
        "concept_id": "ids",
        "type": "judge",
        "stem": "IDS 通常只做检测与告警，不直接阻断流量。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "IDS 旁路部署、只告警；串联部署并能阻断的是 IPS。",
        "source": "教材 §7.3 入侵检测",
        "difficulty": "easy",
    },
    {
        "id": "q_vpn",
        "chapter_id": "ch_06",
        "concept_id": "vpn",
        "type": "single",
        "stem": "IPsec 不提供以下哪项能力？",
        "options": [
            {"key": "A", "text": "身份认证"},
            {"key": "B", "text": "数据加密"},
            {"key": "C", "text": "完整性保护"},
            {"key": "D", "text": "自动分配 IP 地址"},
        ],
        "answer": "D",
        "explanation": "IPsec 提供认证、加密与完整性；地址分配由 DHCP 等机制负责，不属于 IPsec 职责。",
        "source": "教材 §7.4 VPN",
        "difficulty": "medium",
    },
    {
        "id": "q_ddos",
        "chapter_id": "ch_06",
        "concept_id": "ddos",
        "type": "single",
        "stem": "面对 DDoS 攻击，下列哪种处置最有效？",
        "options": [
            {"key": "A", "text": "升级单台服务器 CPU"},
            {"key": "B", "text": "流量清洗与限速"},
            {"key": "C", "text": "关闭 DNS 服务"},
            {"key": "D", "text": "禁用 TCP 协议"},
        ],
        "answer": "B",
        "explanation": "DDoS 靠规模压垮目标，需在入口做流量清洗、限速与任播分散，单机扩容无法吸收。",
        "source": "教材 §7.5 DDoS",
        "difficulty": "easy",
    },
    {
        "id": "q_pki",
        "chapter_id": "ch_06",
        "concept_id": "pki",
        "type": "judge",
        "stem": "数字证书的作用是把公钥与身份绑定起来。",
        "options": [{"key": "T", "text": "正确"}, {"key": "F", "text": "错误"}],
        "answer": "T",
        "explanation": "CA 用私钥签名证书，把主体信息与公钥绑定，验证方沿信任链校验签名即可确认身份。",
        "source": "教材 §7.6 PKI",
        "difficulty": "easy",
    },
    {
        "id": "q_rfc",
        "chapter_id": "ch_01",
        "concept_id": "rfc",
        "type": "single",
        "stem": "关于 RFC 文档，下列说法正确的是？",
        "options": [
            {"key": "A", "text": "发布后可以随时修改编号内容"},
            {"key": "B", "text": "由 IETF 发布，是互联网协议的权威标准文档"},
            {"key": "C", "text": "只用于厂商内部实现，不对外公开"},
            {"key": "D", "text": "与协议的具体实现无关"},
        ],
        "answer": "B",
        "explanation": "RFC 由 IETF 等组织发布并公开归档，编号一经分配不再改变；更新以新编号文档发布。",
        "source": "教材 §1.5 标准化",
        "difficulty": "easy",
    },
]

ASSIGNMENTS = [
    {
        "id": "asg_w3",
        "title": "第 3 周作业：TCP 与子网",
        "chapter_id": "ch_04",
        "due_in_days": 1,
        "items": [
            {
                "type": "short",
                "stem": "TCP 三次握手中，第三次 ACK 的作用是什么？",
                "reference": "客户端确认收到了服务端的 SYN+ACK，证明客户端接收与服务端发送通道可用；同时同步并确认序号，避免历史重复连接被误接受。",
                "rubric": [
                    {"text": "确认客户端接收能力与服务端发送通道", "score": 4},
                    {"text": "同步并确认序号", "score": 3},
                    {"text": "避免历史重复连接被误接受", "score": 3},
                ],
                "score": 10,
                "concept_id": "handshake",
            },
            {
                "type": "short",
                "stem": "TCP 已经有流量控制，为什么还需要拥塞控制？",
                "reference": "流量控制只保护接收端缓冲区，避免发送方压垮接收方；拥塞控制面向整个网络，通过 cwnd 感知链路与路由器负载，避免大量主机同时重传把网络推入拥塞崩溃。",
                "rubric": [
                    {"text": "流量控制保护接收端缓冲区", "score": 4},
                    {"text": "拥塞控制面向网络整体负载", "score": 3},
                    {"text": "避免拥塞崩溃与全局重传放大", "score": 3},
                ],
                "score": 10,
                "concept_id": "congestion",
            },
            {
                "type": "short",
                "stem": "ARP 在同一网段内和跨网段访问时，解析目标有什么不同？",
                "reference": "同网段解析目的主机的 MAC，直接封装帧发送；跨网段解析默认网关的 MAC，由网关转发，目的 IP 仍在 IP 头里保持不变。",
                "rubric": [
                    {"text": "同网段解析目的主机 MAC", "score": 4},
                    {"text": "跨网段解析默认网关 MAC", "score": 4},
                    {"text": "目的 IP 保持不变", "score": 2},
                ],
                "score": 10,
                "concept_id": "arp",
            },
            {
                "type": "calc",
                "stem": "192.168.10.0/27 的网络地址和可用主机数分别是多少？写出计算依据。",
                "reference": "块大小 32，网络地址 192.168.10.0，广播地址 192.168.10.31，可用主机 30 个。",
                "rubric": [
                    {"text": "网络地址 192.168.10.0", "score": 4},
                    {"text": "可用主机 30 个", "score": 4},
                    {"text": "块大小 32，去掉网络与广播地址", "score": 2},
                ],
                "score": 10,
                "concept_id": "cidr",
            },
            {
                "type": "calc",
                "stem": "把 10.0.0.0/8 划分为 /12 子网，可以划分出多少个子网？说明依据。",
                "reference": "前缀从 8 位增加到 12 位，借 4 位主机位做子网号，2^4 = 16 个子网。",
                "rubric": [
                    {"text": "借 4 位作为子网号", "score": 4},
                    {"text": "子网数 16 个", "score": 4},
                    {"text": "2^4 的计算依据", "score": 2},
                ],
                "score": 10,
                "concept_id": "mask",
            },
        ],
    }
]


async def _seed_concepts(session) -> None:
    """概念与关系幂等补种：老演示库缺哪个补哪个，并把未挂知识点的题回填归属。"""
    existing = set((await session.execute(select(Concept.id))).scalars().all())
    for index, (cid, chapter_id, title, description) in enumerate(CONCEPTS):
        if cid in existing:
            continue
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

    # 外键开启后必须先落概念，再写引用概念的边
    await session.flush()
    edge_rows = (await session.execute(select(ConceptEdge.source_id, ConceptEdge.target_id, ConceptEdge.kind))).all()
    known_edges = {(row[0], row[1], row[2]) for row in edge_rows}
    for source, target, kind in EDGES:
        if (source, target, kind) in known_edges:
            continue
        session.add(
            ConceptEdge(
                id=new_id(),
                course_id=COURSE_ID,
                source_id=source,
                target_id=target,
                kind=kind,
            )
        )

    seeded = {item["id"]: item.get("concept_id") for item in QUESTIONS}
    for question_id, concept_id in (await session.execute(select(Question.id, Question.concept_id))).all():
        target = seeded.get(question_id)
        # 题库归属以种子为准：既补空缺，也纠正历史库里的漂移（如章节补充知识点后重新挂接）
        if target and concept_id != target:
            await session.execute(
                update(Question).where(Question.id == question_id).values(concept_id=target)
            )

    await session.commit()


async def _seed_questions(session) -> None:
    """题库幂等补种：旧演示库缺哪道就补哪道，新增题目不需要清库。"""
    existing = set((await session.execute(select(Question.id))).scalars().all())
    for index, item in enumerate(QUESTIONS):
        if item["id"] in existing:
            continue
        session.add(
            Question(
                course_id=COURSE_ID,
                sort_order=index,
                id=item["id"],
                **{key: value for key, value in item.items() if key != "id"},
            )
        )
    await session.commit()


USERS = [
    {"user_key": "teacher", "display_name": "教师", "role": "teacher", "note": ""},
    {"user_key": "demo_user", "display_name": "李金洋", "role": "student", "note": "主账号"},
    {"user_key": "stu_lin", "display_name": "林晓", "role": "student", "note": "示例学生 · 基础偏弱"},
    {"user_key": "stu_zhao", "display_name": "赵一鸣", "role": "student", "note": "示例学生 · 基础较好"},
]


async def _seed_users(session) -> None:
    """账号资料幂等补种：只补缺失账号，不覆盖库里已经改过的展示名。"""
    existing = set((await session.execute(select(User.user_key))).scalars().all())
    for row in USERS:
        if row["user_key"] in existing:
            continue
        session.add(User(**row))
    await session.commit()


async def _seed_assignments(session) -> None:
    """作业幂等补种：只补题目，不造学生提交，避免演示数据看起来像刷出来的。"""
    existing = set((await session.execute(select(Assignment.id))).scalars().all())
    for row in ASSIGNMENTS:
        if row["id"] in existing:
            continue
        due_at = utcnow() + timedelta(days=row["due_in_days"]) if row.get("due_in_days") else None
        items = row["items"]
        session.add(
            Assignment(
                id=row["id"],
                course_id=COURSE_ID,
                chapter_id=row.get("chapter_id"),
                title=row["title"],
                description=row.get("description", ""),
                due_at=due_at,
                total_score=sum(item["score"] for item in items),
                status=row.get("status", "published"),
                created_by="teacher",
            )
        )
        await session.flush()
        for ordinal, item in enumerate(items, start=1):
            session.add(
                AssignmentItem(
                    id=f"{row['id']}_i{ordinal}",
                    assignment_id=row["id"],
                    ordinal=ordinal,
                    type=item["type"],
                    stem=item["stem"],
                    reference=item["reference"],
                    rubric=item["rubric"],
                    score=item["score"],
                    concept_id=item.get("concept_id"),
                    difficulty=item.get("difficulty", "medium"),
                )
            )
    await session.commit()


async def seed_if_empty() -> None:
    async with SessionFactory() as session:
        existing = await session.scalar(select(Course).where(Course.id == COURSE_ID))
        if existing:
            await _seed_users(session)
            await _seed_concepts(session)
            await _seed_questions(session)
            await _seed_assignments(session)
            return

        session.add(
            Course(
                id=COURSE_ID,
                title=COURSE_TITLE,
                description="从分层模型到应用层，围绕协议、地址与转发组织的一门课程。",
            )
        )
        await session.flush()  # 课程先落库，章节与概念才能引用
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
        await session.flush()  # 课程、章节、概念先落库，后面的边与文档才能引用
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
            await session.flush()  # 先落文档行，再插引用它的分块
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
        await _seed_users(session)
        await _seed_questions(session)
        await _seed_assignments(session)
