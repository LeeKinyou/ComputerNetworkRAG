export interface StatItem {
  label: string
  value: string
  hint: string
}

export interface RecentRun {
  id: string
  question: string
  time: string
  status: 'completed' | 'running' | 'waiting'
  tools: number
}

export interface GraphNode {
  id: string
  name: string
  category: number
  value: number
  desc: string
  refs: string[]
}

export interface GraphLink {
  source: string
  target: string
  kind: 'prerequisite' | 'contains' | 'related'
}

export interface CourseDoc {
  id: string
  title: string
  type: 'pdf' | 'md' | 'docx' | 'pptx'
  chunks: number
  size: string
  status: 'ready' | 'parsing' | 'failed'
  updated: string
}

export interface TraceStep {
  kind: 'thought' | 'action' | 'observation' | 'answer'
  title: string
  detail: string
  ms?: number
  status?: 'ok' | 'empty' | 'error'
}

export const stats: StatItem[] = [
  { label: '课程文档', value: '12', hint: '本周新增 2 份' },
  { label: '知识点', value: '46', hint: '覆盖 6 个章节' },
  { label: '图谱关系', value: '78', hint: '先修 31 条' },
  { label: '今日问答', value: '23', hint: '平均 3.2 步工具调用' },
]

export const recentRuns: RecentRun[] = [
  {
    id: 'run_01',
    question: '计算 192.168.10.137/27 的网络地址与可用主机范围',
    time: '10 分钟前',
    status: 'completed',
    tools: 3,
  },
  {
    id: 'run_02',
    question: '为什么 TCP 需要三次握手，两次不够吗？',
    time: '32 分钟前',
    status: 'completed',
    tools: 2,
  },
  {
    id: 'run_03',
    question: '对比 CSMA/CD 与 CSMA/CA 的适用场景',
    time: '1 小时前',
    status: 'completed',
    tools: 4,
  },
  {
    id: 'run_04',
    question: '导入《计算机网络》第 4 章并重建索引',
    time: '2 小时前',
    status: 'waiting',
    tools: 1,
  },
]

export const categories = [
  { name: '分层模型' },
  { name: '数据链路层' },
  { name: '网络层' },
  { name: '传输层' },
  { name: '应用层' },
]

export const graphNodes: GraphNode[] = [
  {
    id: 'osi',
    name: 'OSI 七层模型',
    category: 0,
    value: 12,
    desc: '将网络通信划分为物理层、数据链路层、网络层、传输层、会话层、表示层和应用层，是分析协议栈的通用框架。',
    refs: ['教材 §1.2 体系结构'],
  },
  {
    id: 'ethernet',
    name: '以太网',
    category: 1,
    value: 8,
    desc: 'IEEE 802.3 定义的局域网技术，使用 CSMA/CD（半双工）或全双工交换，帧格式含前导码、目的/源 MAC 与 FCS。',
    refs: ['教材 §3.2 以太网'],
  },
  {
    id: 'csma',
    name: 'CSMA/CD',
    category: 1,
    value: 6,
    desc: '载波监听多路访问/冲突检测。发送前监听信道，冲突时停止并退避重发；全双工交换网络中不再需要。',
    refs: ['教材 §3.3 CSMA/CD'],
  },
  {
    id: 'mac',
    name: 'MAC 地址',
    category: 1,
    value: 5,
    desc: '48 位链路层地址，前 24 位为厂商 OUI。用于同一广播域内的帧交付。',
    refs: ['教材 §3.1 链路层寻址'],
  },
  {
    id: 'arp',
    name: 'ARP',
    category: 2,
    value: 7,
    desc: '在同一局域网内把 IPv4 地址解析为 MAC 地址，通过广播请求、单播应答维护 ARP 缓存。',
    refs: ['RFC 826', '教材 §4.2 ARP'],
  },
  {
    id: 'ipv4',
    name: 'IPv4',
    category: 2,
    value: 14,
    desc: '32 位地址的网络层协议，提供无连接、尽力而为的分组交付。地址由网络位与主机位组成。',
    refs: ['RFC 791', '教材 §4.3 IPv4'],
  },
  {
    id: 'mask',
    name: '子网掩码',
    category: 2,
    value: 7,
    desc: '与 IPv4 地址按位与，得到网络地址。掩码中 1 的个数即前缀长度。',
    refs: ['教材 §4.4 子网划分'],
  },
  {
    id: 'cidr',
    name: 'CIDR',
    category: 2,
    value: 8,
    desc: '无类别域间路由，用 /n 前缀表示网络范围，支持路由聚合，替代传统的 A/B/C 类划分。',
    refs: ['RFC 1519', '教材 §4.5 CIDR'],
  },
  {
    id: 'route',
    name: '路由表',
    category: 2,
    value: 9,
    desc: '目的网络、下一跳、出接口与度量值组成；转发时按最长前缀匹配选择条目。',
    refs: ['教材 §5.1 路由原理'],
  },
  {
    id: 'nat',
    name: 'NAT',
    category: 2,
    value: 6,
    desc: '在私有地址与公网地址之间转换，缓解 IPv4 地址枯竭；破坏端到端语义，需要穿透机制。',
    refs: ['RFC 3022'],
  },
  {
    id: 'icmp',
    name: 'ICMP',
    category: 2,
    value: 5,
    desc: '承载网络层差错与控制报文，ping 使用 Echo Request/Reply，traceroute 依赖 TTL 超时报文。',
    refs: ['RFC 792'],
  },
  {
    id: 'tcp',
    name: 'TCP',
    category: 3,
    value: 13,
    desc: '面向连接的传输层协议，提供可靠、有序、流量控制与拥塞控制的字节流服务。',
    refs: ['RFC 9293', '教材 §6.2 TCP'],
  },
  {
    id: 'handshake',
    name: '三次握手',
    category: 3,
    value: 6,
    desc: 'SYN → SYN+ACK → ACK，双方同步初始序号并确认彼此可达，避免历史重复连接被误接受。',
    refs: ['教材 §6.3 连接管理'],
  },
  {
    id: 'congestion',
    name: '拥塞控制',
    category: 3,
    value: 7,
    desc: '慢启动、拥塞避免、快重传与快恢复；通过 cwnd 调节发送速率，避免网络进入拥塞崩溃。',
    refs: ['教材 §6.4 拥塞控制'],
  },
  {
    id: 'udp',
    name: 'UDP',
    category: 3,
    value: 5,
    desc: '无连接传输协议，只有端口与校验和，适合实时音视频与 DNS 等可容忍丢包的场景。',
    refs: ['RFC 768'],
  },
  {
    id: 'dns',
    name: 'DNS',
    category: 4,
    value: 8,
    desc: '把域名解析为地址，采用分布式层级命名系统，递归查询与迭代查询配合使用。',
    refs: ['RFC 1034'],
  },
  {
    id: 'http',
    name: 'HTTP',
    category: 4,
    value: 9,
    desc: '应用层请求/响应协议，HTTP/1.1 持久连接、HTTP/2 多路复用、HTTP/3 基于 QUIC。',
    refs: ['RFC 9110'],
  },
  {
    id: 'tls',
    name: 'TLS',
    category: 4,
    value: 7,
    desc: '在传输层之上提供加密、身份认证与完整性保护，HTTPS 即 HTTP over TLS。',
    refs: ['RFC 8446'],
  },
]

export const graphLinks: GraphLink[] = [
  { source: 'osi', target: 'ethernet', kind: 'contains' },
  { source: 'osi', target: 'ipv4', kind: 'contains' },
  { source: 'osi', target: 'tcp', kind: 'contains' },
  { source: 'osi', target: 'http', kind: 'contains' },
  { source: 'ethernet', target: 'csma', kind: 'related' },
  { source: 'ethernet', target: 'mac', kind: 'related' },
  { source: 'mac', target: 'arp', kind: 'prerequisite' },
  { source: 'arp', target: 'ipv4', kind: 'prerequisite' },
  { source: 'ipv4', target: 'mask', kind: 'contains' },
  { source: 'mask', target: 'cidr', kind: 'prerequisite' },
  { source: 'ipv4', target: 'route', kind: 'prerequisite' },
  { source: 'route', target: 'nat', kind: 'related' },
  { source: 'route', target: 'icmp', kind: 'related' },
  { source: 'ipv4', target: 'tcp', kind: 'prerequisite' },
  { source: 'ipv4', target: 'udp', kind: 'prerequisite' },
  { source: 'tcp', target: 'handshake', kind: 'contains' },
  { source: 'tcp', target: 'congestion', kind: 'contains' },
  { source: 'tcp', target: 'http', kind: 'prerequisite' },
  { source: 'http', target: 'tls', kind: 'related' },
  { source: 'dns', target: 'http', kind: 'prerequisite' },
  { source: 'udp', target: 'dns', kind: 'related' },
]

export const documents: CourseDoc[] = [
  {
    id: 'doc_01',
    title: '计算机网络（第 8 版）第 4 章：网络层',
    type: 'pdf',
    chunks: 42,
    size: '6.4 MB',
    status: 'ready',
    updated: '2026-11-18 09:20',
  },
  {
    id: 'doc_02',
    title: 'RFC 950：Internet 子网划分流程',
    type: 'md',
    chunks: 18,
    size: '212 KB',
    status: 'ready',
    updated: '2026-11-18 09:18',
  },
  {
    id: 'doc_03',
    title: '子网划分实验手册（含 12 组练习）',
    type: 'docx',
    chunks: 26,
    size: '1.1 MB',
    status: 'ready',
    updated: '2026-11-17 21:04',
  },
  {
    id: 'doc_04',
    title: '课程大纲与章节知识点映射',
    type: 'md',
    chunks: 12,
    size: '48 KB',
    status: 'parsing',
    updated: '2026-11-18 10:02',
  },
]

export const demoQuestions = [
  '/27 子网怎么算？',
  'TCP 为什么需要三次握手？',
  'CSMA/CD 和 CSMA/CA 的区别',
  'CIDR 与路由聚合的关系',
]

export const traceSteps: TraceStep[] = [
  {
    kind: 'thought',
    title: '识别任务',
    detail: '需要计算 /27 子网的网络地址与主机范围，并解释网关。',
    ms: 120,
  },
  {
    kind: 'action',
    title: 'search_course',
    detail: 'query="IPv4 子网划分 /27" · top_k=5',
    ms: 386,
    status: 'ok',
  },
  {
    kind: 'observation',
    title: '命中 5 个课程片段',
    detail: '教材 §4.4、RFC 950、实验手册 §2.1',
    ms: 42,
    status: 'ok',
  },
  {
    kind: 'action',
    title: 'subnet',
    detail: 'ip=192.168.10.137 · prefix=27',
    ms: 3,
    status: 'ok',
  },
  {
    kind: 'observation',
    title: '网络地址 192.168.10.128',
    detail: '广播 .159，可用 .129–.158，共 30 个主机地址',
  },
  {
    kind: 'thought',
    title: '组织回答',
    detail: '引用 2 条来源；网关无法从 IP 与掩码推断，需谨慎说明。',
    ms: 210,
  },
]

export interface Chapter {
  id: string
  order: number
  title: string
  subtitle: string
  topics: string[]
  minutes: number
  progress: number
  status: 'done' | 'active' | 'todo'
}

export const chapters: Chapter[] = [
  {
    id: 'ch_01',
    order: 1,
    title: '概述与分层模型',
    subtitle: 'OSI 七层、TCP/IP 四层与封装解封装',
    topics: ['OSI 七层模型', 'TCP/IP 体系', '封装与解封装'],
    minutes: 90,
    progress: 100,
    status: 'done',
  },
  {
    id: 'ch_02',
    order: 2,
    title: '物理层与数据链路层',
    subtitle: '编码调制、以太网、CSMA/CD、MAC 与 ARP',
    topics: ['以太网', 'CSMA/CD', 'MAC 地址', 'ARP'],
    minutes: 120,
    progress: 82,
    status: 'done',
  },
  {
    id: 'ch_03',
    order: 3,
    title: '网络层：IPv4 与子网划分',
    subtitle: 'IP 地址、子网掩码、CIDR、路由与 NAT',
    topics: ['IPv4', '子网掩码', 'CIDR', '路由表', 'NAT', 'ICMP'],
    minutes: 150,
    progress: 55,
    status: 'active',
  },
  {
    id: 'ch_04',
    order: 4,
    title: '传输层：TCP 与 UDP',
    subtitle: '三次握手、可靠传输、流量与拥塞控制',
    topics: ['TCP', 'UDP', '三次握手', '拥塞控制'],
    minutes: 140,
    progress: 0,
    status: 'todo',
  },
  {
    id: 'ch_05',
    order: 5,
    title: '应用层与 Web 协议',
    subtitle: 'DNS 解析、HTTP 报文、TLS 握手',
    topics: ['DNS', 'HTTP', 'TLS'],
    minutes: 110,
    progress: 0,
    status: 'todo',
  },
  {
    id: 'ch_06',
    order: 6,
    title: '网络安全与综合实验',
    subtitle: '抓包分析、子网规划与端到端联调',
    topics: ['抓包分析', '子网规划', '综合实验'],
    minutes: 120,
    progress: 0,
    status: 'todo',
  },
]

export interface RagPassage {
  id: string
  source: string
  locator: string
  score: number
  text: string
}

export const ragPassages: RagPassage[] = [
  {
    id: 'p1',
    source: '计算机网络（第 8 版）',
    locator: '§4.4 子网划分 · p.126',
    score: 0.94,
    text: '/27 表示前 27 位是网络位，主机位 5 位，每个子网包含 2^5 = 32 个地址。',
  },
  {
    id: 'p2',
    source: 'RFC 950',
    locator: 'Section 3',
    score: 0.88,
    text: 'Subnetting divides the host field into subnet and host parts; the network and broadcast addresses are reserved.',
  },
  {
    id: 'p3',
    source: '子网划分实验手册',
    locator: '§2.1 例题 3',
    score: 0.81,
    text: '对 192.168.10.137/27，块大小为 32，落在 .128–.159 区间，网络地址 .128，广播地址 .159。',
  },
  {
    id: 'p4',
    source: '课程大纲与章节知识点映射',
    locator: '第 3 章 · 子网掩码',
    score: 0.72,
    text: '子网掩码 255.255.255.224 与 /27 等价，可用主机数为 2^5 − 2 = 30。',
  },
]

export const profile = {
  name: '李金阳',
  initials: '李',
  school: '重庆邮电大学',
  major: '计算机科学与技术 · 研一',
  role: '课程助教 / 演示环境管理员',
  joined: '2026-09-01',
  email: 'leekinyou@example.com',
}

export const learningStats = [
  { label: '累计问答', value: '128', hint: '本周 23 次' },
  { label: '学习时长', value: '36h', hint: '近 30 天' },
  { label: '掌握知识点', value: '31', hint: '共 46 个' },
  { label: '连续学习', value: '9', hint: '天' },
]

export const activities = [
  { time: '10:21', title: '完成 /27 子网划分问答', detail: 'ReAct 智能体 · 3 次工具调用' },
  { time: '09:40', title: '上传《计算机网络》第 4 章', detail: 'PDF · 42 个分块 · 索引 v3' },
  { time: '昨天', title: '完成第 2 章知识检查', detail: '得分 86 · 错题 4 道' },
  { time: '11-16', title: '创建学习路径', detail: '6 个章节 · 预计 12 小时' },
]

