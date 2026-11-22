export type TaskStatus = 'running' | 'waiting_approval' | 'done' | 'failed'
export type TaskMode = 'rag' | 'agent'
export type Mastery = 'mastered' | 'weak' | 'new'
export type ArtifactKind = 'calc' | 'answer' | 'table' | 'note' | 'quiz' | 'graph'

export interface TaskStep {
  id: string
  kind: 'thought' | 'action' | 'observation' | 'approval'
  title: string
  detail?: string
  ms?: number
  status?: 'ok' | 'pending' | 'failed'
}

export interface PlanItem {
  id: string
  label: string
  state: 'done' | 'active' | 'todo'
}

export interface Artifact {
  id: string
  kind: ArtifactKind
  title: string
  summary: string
  meta?: string
  taskId?: string
  createdAt: string
}

export interface SourceRef {
  id: string
  chunkId: string
  documentId?: string
  doc: string
  locator: string
  score: number
  text: string
  carriedOver?: boolean
}

export interface PendingApproval {
  input_id: string
  kind: string
  prompt: string
  tool_call_id?: string
}

export interface CalcCard {
  ip: string
  prefix: number
  network_address: string
  broadcast_address: string
  first_host: string
  last_host: string
  usable_host_count: number
  block_size: number
}

export interface Task {
  id: string
  title: string
  question: string
  course: string
  chapter?: string
  mode: TaskMode
  status: TaskStatus
  createdAt: string
  group: '今天' | '本周' | '更早'
  plan: PlanItem[]
  steps: TaskStep[]
  artifacts: Artifact[]
  sources: SourceRef[]
  answer?: string
  streaming?: string
  calc?: CalcCard
  pending?: PendingApproval | null
  lastSeq?: number
  demo?: boolean
}

export interface TodayTask {
  id: string
  title: string
  reason: string
  minutes: number
  kind: 'learn' | 'review' | 'practice'
  target: string
  highlight?: boolean
}

export interface InsightItem {
  label: string
  value: string
  hint: string
  level: 'high' | 'mid' | 'low'
}

export const masteryMap: Record<string, Mastery> = {
  ipv4: 'mastered',
  osi: 'mastered',
  ethernet: 'mastered',
  csma: 'weak',
  mac: 'mastered',
  arp: 'mastered',
  mask: 'mastered',
  cidr: 'weak',
  route: 'new',
  nat: 'new',
  icmp: 'new',
  tcp: 'mastered',
  handshake: 'mastered',
  congestion: 'weak',
  udp: 'mastered',
  dns: 'new',
  http: 'new',
  tls: 'new',
}

export const masteryLabel: Record<Mastery, string> = {
  mastered: '已掌握',
  weak: '薄弱',
  new: '未学',
}

const subnetSources: SourceRef[] = [
  {
    id: 's1',
    chunkId: 'chunk_4412',
    doc: '计算机网络（第 8 版）',
    locator: '§4.4 子网划分 · p.126',
    score: 0.94,
    text: '/27 表示前 27 位是网络位，主机位 5 位，每个子网包含 2^5 = 32 个地址。',
  },
  {
    id: 's2',
    chunkId: 'chunk_0950',
    doc: 'RFC 950',
    locator: 'Section 3',
    score: 0.88,
    text: 'Subnetting divides the host field into subnet and host parts; network and broadcast addresses are reserved.',
  },
  {
    id: 's3',
    chunkId: 'chunk_1108',
    doc: '子网划分实验手册',
    locator: '§2.1 例题 3',
    score: 0.81,
    text: '对 192.168.10.137/27，块大小为 32，落在 .128–.159 区间，网络地址 .128，广播地址 .159。',
  },
]

export const tasks: Task[] = [
  {
    id: 'task_01',
    title: '192.168.10.137/27 的子网划分',
    question: '计算 192.168.10.137/27 的网络地址、广播地址和可用主机范围，并解释网关。',
    course: '计算机网络',
    chapter: '第 3 章 · 网络层',
    mode: 'agent',
    status: 'done',
    createdAt: '10:21',
    group: '今天',
    plan: [
      { id: 'p1', label: '识别问题与所需知识点', state: 'done' },
      { id: 'p2', label: '检索课程资料（向量 + 图谱）', state: 'done' },
      { id: 'p3', label: '计算网络地址与主机范围', state: 'done' },
      { id: 'p4', label: '组织回答并给出原文出处', state: 'done' },
    ],
    steps: [
      {
        id: 'st1',
        kind: 'thought',
        title: '识别任务',
        detail: '需要按 /27 计算网络地址与主机范围，网关无法从 IP 与掩码推断，回答中不臆测。',
        ms: 120,
      },
      {
        id: 'st2',
        kind: 'action',
        title: 'search_course',
        detail: 'query="IPv4 子网划分 /27" · top_k=5 · 混合检索',
        ms: 386,
        status: 'ok',
      },
      {
        id: 'st3',
        kind: 'observation',
        title: '命中 5 个课程片段',
        detail: '教材 §4.4、RFC 950、实验手册 §2.1',
        ms: 42,
        status: 'ok',
      },
      {
        id: 'st4',
        kind: 'action',
        title: 'subnet',
        detail: 'ip=192.168.10.137 · prefix=27',
        ms: 3,
        status: 'ok',
      },
      {
        id: 'st5',
        kind: 'observation',
        title: '网络地址 192.168.10.128',
        detail: '广播 .159，可用 .129–.158，共 30 个主机地址',
      },
    ],
    artifacts: [
      {
        id: 'art_01',
        kind: 'calc',
        title: '/27 子网计算卡',
        summary: '网络地址 192.168.10.128 · 可用 30 个主机',
        meta: '可调前缀，结果实时重算',
        taskId: 'task_01',
        createdAt: '10:21',
      },
      {
        id: 'art_02',
        kind: 'note',
        title: '子网划分速记',
        summary: '块大小 = 2^(32−前缀)；网络地址按块对齐，广播地址是下一块减一。',
        meta: '已存为笔记',
        taskId: 'task_01',
        createdAt: '10:23',
      },
    ],
    sources: subnetSources,
    answer: '按 /27 计算，主机位 5 位，块大小为 32。网络地址为 192.168.10.128，广播地址为 192.168.10.159，可用主机为 .129–.158，共 30 个。',
  },
  {
    id: 'task_02',
    title: 'TCP 为什么需要三次握手',
    question: '为什么 TCP 需要三次握手，两次不够吗？',
    course: '计算机网络',
    chapter: '第 4 章 · 传输层',
    mode: 'agent',
    status: 'done',
    createdAt: '09:48',
    group: '今天',
    plan: [
      { id: 'p1', label: '定位传输层知识点', state: 'done' },
      { id: 'p2', label: '检索教材与 RFC', state: 'done' },
      { id: 'p3', label: '组织因果解释', state: 'done' },
    ],
    steps: [
      {
        id: 'st1',
        kind: 'thought',
        title: '识别任务',
        detail: '解释三次握手的必要性，重点在防止历史连接与序列号同步。',
        ms: 96,
      },
      {
        id: 'st2',
        kind: 'action',
        title: 'search_course',
        detail: 'query="TCP 三次握手 必要性" · top_k=5',
        ms: 312,
        status: 'ok',
      },
      {
        id: 'st3',
        kind: 'observation',
        title: '命中 4 个课程片段',
        detail: '教材 §5.3、RFC 793、课堂讲义 §2',
        ms: 38,
        status: 'ok',
      },
    ],
    artifacts: [
      {
        id: 'art_03',
        kind: 'answer',
        title: '三次握手解释卡',
        summary: '两次握手无法确认客户端收到 SYN-ACK，且可能建立历史连接。',
        taskId: 'task_02',
        createdAt: '09:50',
      },
    ],
    sources: subnetSources.slice(0, 1),
    answer: '两次握手只能确认双方收发能力，无法让服务端确认客户端已收到自己的 SYN-ACK，也可能因延迟的旧 SYN 建立错误连接。',
  },
  {
    id: 'task_03',
    title: 'CSMA/CD 与 CSMA/CA 的差异',
    question: '对比 CSMA/CD 与 CSMA/CA 的适用场景和冲突处理方式。',
    course: '计算机网络',
    chapter: '第 2 章 · 数据链路层',
    mode: 'rag',
    status: 'done',
    createdAt: '09:12',
    group: '今天',
    plan: [
      { id: 'p1', label: '查询改写', state: 'done' },
      { id: 'p2', label: '向量 + BM25 召回', state: 'done' },
      { id: 'p3', label: 'RRF 融合与重排', state: 'done' },
    ],
    steps: [
      {
        id: 'st1',
        kind: 'action',
        title: 'hybrid_retrieve',
        detail: '向量 20 条 + BM25 20 条 · RRF k=60',
        ms: 428,
        status: 'ok',
      },
      {
        id: 'st2',
        kind: 'observation',
        title: '重排保留 5 条',
        detail: '教材 §3.3、§3.5、实验手册 §1',
        ms: 12,
        status: 'ok',
      },
    ],
    artifacts: [
      {
        id: 'art_04',
        kind: 'table',
        title: '两种 CSMA 对比表',
        summary: '监听方式、冲突处理、适用介质、典型标准',
        taskId: 'task_03',
        createdAt: '09:14',
      },
    ],
    sources: subnetSources.slice(0, 2),
    answer: 'CSMA/CD 用于有线共享介质，边发边听、冲突后停止并退避；CSMA/CA 用于无线，靠预约与 ACK 避免冲突，因为无线端无法在发送时可靠检测冲突。',
  },
  {
    id: 'task_04',
    title: '导入第 4 章并重建索引',
    question: '导入《计算机网络》第 4 章 PDF，解析后重建课程索引。',
    course: '计算机网络',
    chapter: '第 4 章 · 传输层',
    mode: 'agent',
    status: 'waiting_approval',
    createdAt: '09:40',
    group: '今天',
    plan: [
      { id: 'p1', label: '解析 PDF 并分块', state: 'done' },
      { id: 'p2', label: '写入向量与 BM25 索引', state: 'active' },
      { id: 'p3', label: '重建完成后校验覆盖率', state: 'todo' },
    ],
    steps: [
      {
        id: 'st1',
        kind: 'action',
        title: 'parse_document',
        detail: '文件=第 4 章.pdf · 42 页 · 输出 63 个分块',
        ms: 1840,
        status: 'ok',
      },
      {
        id: 'st2',
        kind: 'approval',
        title: '需要确认：重建索引',
        detail: '将替换索引 v3，影响 98 个分块的检索结果。',
        status: 'pending',
      },
    ],
    artifacts: [],
    sources: [],
  },
  {
    id: 'task_05',
    title: '第 3 章子网练习（5 题）',
    question: '根据第 3 章薄弱点生成 5 道子网划分练习。',
    course: '计算机网络',
    chapter: '第 3 章 · 网络层',
    mode: 'rag',
    status: 'done',
    createdAt: '昨天 20:16',
    group: '本周',
    plan: [
      { id: 'p1', label: '读取薄弱知识点', state: 'done' },
      { id: 'p2', label: '生成并筛选题目', state: 'done' },
    ],
    steps: [
      {
        id: 'st1',
        kind: 'action',
        title: 'generate_quiz',
        detail: '知识点=cidr, mask · 难度=中 · 数量=5',
        ms: 620,
        status: 'ok',
      },
    ],
    artifacts: [
      {
        id: 'art_05',
        kind: 'quiz',
        title: '子网划分练习（5 题）',
        summary: '含答案与解析，覆盖 /26–/29 与路由聚合',
        taskId: 'task_05',
        createdAt: '昨天 20:18',
      },
    ],
    sources: [],
  },
]

export const todayTasks: TodayTask[] = [
  {
    id: 'today_01',
    title: '完成「网络层：IPv4 与子网」剩余 3 个知识点',
    reason: '学习计划中的当前章节，已完成 55%',
    minutes: 25,
    kind: 'learn',
    target: '/chat',
    highlight: true,
  },
  {
    id: 'today_02',
    title: '复习 2 个薄弱点：CIDR 路由聚合、拥塞控制',
    reason: '近两次作答错误集中在先修关系',
    minutes: 8,
    kind: 'review',
    target: '/graph',
  },
  {
    id: 'today_03',
    title: '做 5 道子网划分练习',
    reason: '昨日错题中有 3 道同类计算',
    minutes: 12,
    kind: 'practice',
    target: '/chat',
  },
]

export const recentArtifacts: Artifact[] = [
  {
    id: 'art_01',
    kind: 'calc',
    title: '/27 子网计算卡',
    summary: '网络地址 192.168.10.128 · 可用 30 个主机',
    taskId: 'task_01',
    createdAt: '10:21',
  },
  {
    id: 'art_02',
    kind: 'note',
    title: '子网划分速记',
    summary: '块大小 = 2^(32−前缀)；网络地址按块对齐。',
    taskId: 'task_01',
    createdAt: '10:23',
  },
  {
    id: 'art_04',
    kind: 'table',
    title: '两种 CSMA 对比表',
    summary: '监听方式、冲突处理、适用介质、典型标准',
    taskId: 'task_03',
    createdAt: '09:14',
  },
]

export const artifactLabel: Record<ArtifactKind, string> = {
  calc: '计算卡',
  answer: '答案卡',
  table: '对比表',
  note: '笔记',
  quiz: '练习',
  graph: '图谱快照',
}

export const insights = {
  className: '计科 2301 · 计算机网络',
  students: 42,
  weeklyQuestions: 186,
  highFrequency: [
    { q: '子网掩码与 CIDR 怎么换算', count: 31 },
    { q: 'TCP 为什么不能两次握手', count: 24 },
    { q: 'CSMA/CD 与 CSMA/CA 的区别', count: 19 },
  ],
  weakPoints: [
    { label: 'CIDR 与路由聚合', rate: '62%', level: 'high' as const },
    { label: '拥塞控制', rate: '55%', level: 'high' as const },
    { label: 'TLS 握手流程', rate: '48%', level: 'mid' as const },
  ],
  errorTypes: [
    { label: '概念混淆', value: 38 },
    { label: '步骤遗漏', value: 27 },
    { label: '计算错误', value: 22 },
    { label: '读题偏差', value: 13 },
  ],
  chapterMastery: [
    { label: '分层模型', value: 96 },
    { label: '数据链路层', value: 88 },
    { label: '网络层', value: 64 },
    { label: '传输层', value: 52 },
    { label: '应用层', value: 41 },
  ],
}

export const profileAssets = [
  { label: '产物', value: '18', hint: '本周 +5' },
  { label: '笔记', value: '7', hint: '自动归档 3 条' },
  { label: '练习', value: '24', hint: '正确率 79%' },
  { label: '错题', value: '11', hint: '待复习 4 道' },
]

export const studentReport = {
  range: '本周',
  weeklyMinutes: 165,
  weeklyDelta: '+18%',
  tasksDone: 5,
  streak: 9,
  masteryRate: 72,
  summary:
    '这周把网络层推进到子网划分，动手算了 6 道题，正确率从 62% 提到 79%。CIDR 的块对齐还会错，建议下周先复习它，再进传输层。',
  daily: [
    { day: '一', minutes: 25 },
    { day: '二', minutes: 42 },
    { day: '三', minutes: 18 },
    { day: '四', minutes: 55 },
    { day: '五', minutes: 12 },
    { day: '六', minutes: 0 },
    { day: '日', minutes: 13 },
  ],
  chapterMastery: [
    { label: '分层模型', value: 92 },
    { label: '数据链路层', value: 85 },
    { label: '网络层', value: 58 },
    { label: '传输层', value: 47 },
    { label: '应用层', value: 30 },
  ],
  weakPoints: [
    { id: 'cidr', label: 'CIDR 与路由聚合', wrong: 3, hint: '错在块对齐，不是概念' },
    { id: 'congestion', label: '拥塞控制', wrong: 2, hint: '四种算法的触发条件混淆' },
    { id: 'tls', label: 'TLS 握手', wrong: 2, hint: '还没学过，先看原文' },
  ],
  mistakes: [
    {
      id: 'm1',
      topic: 'CIDR',
      title: '把 /26 的块大小算成 32',
      reason: '计算错误',
      state: '待复习',
      time: '昨天',
    },
    {
      id: 'm2',
      topic: 'TCP',
      title: '把三次握手说成“确认双方端口”',
      reason: '概念混淆',
      state: '已订正',
      time: '11-16',
    },
    {
      id: 'm3',
      topic: 'CSMA/CA',
      title: '漏掉 ACK 与退避阶段',
      reason: '步骤遗漏',
      state: '待复习',
      time: '11-15',
    },
    {
      id: 'm4',
      topic: '子网划分',
      title: '广播地址取成了网段最后一个可用地址',
      reason: '计算错误',
      state: '已订正',
      time: '11-14',
    },
  ],
  achievements: [
    { label: '连续学习 9 天', hint: '最长记录 12 天' },
    { label: '本周 5 个任务', hint: '超过 78% 的同学' },
    { label: '产物 18 份', hint: '笔记 7 · 练习 24' },
  ],
}

