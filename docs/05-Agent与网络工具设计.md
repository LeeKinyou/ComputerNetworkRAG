# 05 · Agent 与网络工具设计

> 版本 v0.1 ｜ 2026-09-08 ｜ 状态：待评审
> 上游：[03 详细设计 §3–§4](./03-详细设计说明书.md)、[04 API §6](./04-API接口设计.md)

## 1. ReAct 智能体总览

### 1.1 运行机制

- 编排由 LangChain/LangGraph 1.x 预构建 `create_agent` 承担（02 ADR-4）：内部即 model ⇄ tools 的 ReAct 循环，工具经注册表适配器暴露给框架；
- model 节点基于 **Function Calling** 返回 tool_calls → tools 节点执行 → ToolMessage 回灌 → 进入下一轮；不再请求工具时直接流式作答结束；
- 递归上限 `AGENT_RECURSION_LIMIT=24`（一次工具往返经过两个节点，约等于 12 轮工具调用；复合问题要跑满多轮直到结果验证完整，上限留足余量）；
- **多轮推进 CompoundTaskMiddleware**：实测 deepseek-chat 对纯 prompt 的多轮要求阳奉阴违（一轮工具后直接作答），故在 `wrap_model_call` 拦截——复合问题（问句标记 ≥2，或含 CIDR/域名等计算对象且带"为什么/课件"溯源要求）且已完成工具轮数 < 2 时，向当次 model 请求末尾注入一条**不落库**的调度提醒（"还有子问题未核实，继续调用工具"）；提醒只在当轮生效、不写检查点，避免过早答案与续跑答案双重流式。工具轮数达下限后不再干预，模型自行决定是否继续；
- 标记 `requires_approval` 的工具在执行前 interrupt，等待 resume（P1，机制见 03 §3.4、端点见 04 §6.5）；
- runner 把框架流事件映射为 SSE 事件（见 04 文档 §6.2），同时落 `agent_steps` 表。

### 1.2 工具选择策略（写入 system prompt）

| 问题特征 | 选择工具 |
|---|---|
| 概念、原理、协议、课程内容 | `course_rag_query` |
| IP/子网/掩码/主机数计算 | `subnet_calculator` |
| 目的 IP 走哪条路由、路由表查表 | `lpm_lookup` |
| 域名解析、查 IP、查邮件服务器等 | `dns_lookup` |
| 复合问题 | 按顺序多步调用，并在 thought 中说明每步原因 |

越界（与计算机网络无关）问题不调用工具，直接礼貌说明范围。

### 1.3 统一工具基类

```python
class BaseTool(ABC):
    name: str                 # 蛇形唯一标识，即 SSE action.tool
    description: str          # 给 LLM 的选用说明（中文，含示例）
    args_schema: dict         # OpenAI tools[].function.parameters（JSON Schema）
    requires_approval: bool = False  # True=HITL 先审后执行（真实网络操作类）
    @abstractmethod
    async def _run(self, **kwargs) -> ToolResult: ...

class ToolResult(BaseModel):
    status: Literal["success", "failed"]
    output: str               # 回灌 LLM 的纯文本（简洁、确定）
    structured: dict = {}     # 前端富渲染数据（字段由各工具自定）
    elapsed_ms: int = 0
```

`ToolRegistry.run()` 统一负责：参数 schema 校验 → 计时 → try/except 转 failed → 网络类工具强制超时。**工具内部不允许抛出未捕获异常、不允许访问 `.env` 之外的密钥。**

业务工具只继承 BaseTool、不 import LangChain；`registry.to_langchain_tools()` 统一适配为 create_agent 需要的框架工具（校验/计时/异常/ToolResult JSON 信封都在适配层），因此新增工具不动 builder/runner 与前端。审批标记原则：纯本地计算与课程检索（subnet_calculator、lpm_lookup、course_rag_query）恒为 False；会产生真实出站请求的 ping_host、http_probe 默认 True；dns_lookup 默认 False（仅 DNS 查询，可由 `APPROVAL_TOOLS` 调整）。

## 2. P0 工具详细设计

### 2.1 subnet_calculator 子网计算器

- **用途**：IPv4 子网划分计算，课程"网络层/编址"核心算法，纯本地、确定性、离线可演。
- **参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ip_cidr | string | 是 | 形如 `192.168.10.137/27`；也允许只给掩码的第二参数形式 |

- **算法**：
  1. 解析 IP 与前缀长度 n（0–30 走主机公式；/31、/32 按 RFC 特殊处理并在结果中注明）；
  2. `mask = (0xFFFFFFFF << (32-n)) & 0xFFFFFFFF`；`network = ip & mask`；`broadcast = network | (~mask & 0xFFFFFFFF)`；
  3. `host_count = 2^(32-n) - 2`；first/last host 为网络地址 +1 / 广播地址 -1；
  4. 用 `ipaddress` 模块交叉校验，防止手写位运算出错。
- **structured 输出**：

```json
{
  "input": "192.168.10.137/27",
  "network": "192.168.10.128", "prefix": 27, "netmask": "255.255.255.224",
  "broadcast": "192.168.10.159",
  "first_host": "192.168.10.129", "last_host": "192.168.10.158",
  "host_count": 30, "is_private": true
}
```

- **output（回灌 LLM）模板**：
  `网络地址 192.168.10.128/27；掩码 255.255.255.224；广播地址 192.168.10.159；可用主机 192.168.10.129-192.168.10.158，共 30 台；属于私网地址。`
- **失败场景**：格式非法、n 越界 → failed + 中文原因（如"CIDR 前缀应为 0-32 的整数"）。
- **测试用例（pytest 必写）**：/24、/27、/16、/32、非法输入各至少 1 条；断言与 Python `ipaddress.ip_network(..., strict=False)` 结果一致。

### 2.2 lpm_lookup 最长前缀匹配

- **用途**：演示路由器查表过程（课程经典算法），输出**逐条比对过程**而非只给结果，便于讲解。
- **参数**：

```json
{
  "destination_ip": "10.2.3.4",
  "routes": [
    {"prefix": "0.0.0.0/0", "next_hop": "R1", "interface": "eth0"},
    {"prefix": "10.2.0.0/16", "next_hop": "R2", "interface": "eth1"},
    {"prefix": "10.2.3.0/24", "next_hop": "R3", "interface": "eth2"}
  ]
}
```

`routes` 缺省时使用内置演示路由表（5–6 条，覆盖默认路由/聚合/主机路由），让智能体零参数也能演示。
- **算法**：按前缀长度从大到小排序；逐条判断 `(dst & mask) == network`，记录每条"匹配/不匹配"；第一个匹配即选中（最长前缀），全部不匹配则"无路由（丢弃）"。
- **structured 输出**：

```json
{
  "selected": {"prefix": "10.2.3.0/24", "next_hop": "R3", "interface": "eth2"},
  "trace": [
    {"prefix": "10.2.3.0/24", "matched": true},
    {"prefix": "10.2.0.0/16", "matched": true, "note": "命中但前缀更短，不选"},
    {"prefix": "0.0.0.0/0", "matched": true, "note": "默认路由，最后兜底"}
  ]
}
```

- **前端富渲染（P1）**：trace 表格逐行高亮命中/落选；MVP 先文本展示。
- **测试**：内置路由表对 3 个目的 IP 的选中结果断言；构造"仅默认路由命中""全部不命中"用例。

### 2.3 dns_lookup DNS 解析

- **用途**：真实网络探测，增强现场感；基于 `dnspython`。
- **参数**：`domain`（必填）、`rtype`（A/AAAA/CNAME/MX，默认 A）。
- **实现要点**：
  - `dns.resolver.Resolver()`，`lifetime=TOOL_TIMEOUT`（默认 3s）；
  - 返回解析记录列表、实际使用的解析服务器、耗时；
  - 域名合法性校验（正则 + 长度限制 253）；**仅允许查询，不做任何反向枚举**。
- **structured 输出**：

```json
{"domain":"www.example.com","rtype":"A","records":["93.184.216.34"],
 "resolver":["114.114.114.114"],"elapsed_ms":86}
```

- **失败**：NXDOMAIN/超时 → failed，output 写"域名不存在/解析超时"，LLM 可据此回答。

### 2.4 course_rag_query 课程知识检索

- **用途**：把 RAG 能力作为工具交给智能体，实现"自主决定查课件"。
- **依赖**：注入 `RAGService`（构造注入，不直接 import LightRAG 单例）。
- **参数**：`query`（必填）、`mode`（naive/local/global/hybrid，默认跟随全局配置）。
- **输出**：
  - output：检索片段拼接的简明上下文（带编号，限长 1500 字，防 prompt 膨胀）；
  - structured：`{"mode":"hybrid","sources":[{"doc_name":"","chunk_id":"","snippet":""}]}`，observation 卡片可展示来源。
- **与 RAG 问答页的区别**：问答页是"检索后直接生成答案"；本工具只返回检索结果，是否继续调用其他工具、如何组织答案由 ReAct 决定。

## 3. P1 预留工具（接口先建、实现后置）

| 工具 | 参数（草案） | 能力 | 备注 |
|---|---|---|---|
| `packet_parser` | `packet_hex`, `layer`=ether/ip/tcp | 解析十六进制报文首部字段（版本/IHL/TTL/标志位/端口/序号/标志位） | 纯计算、无安全风险，适合答辩演示 |
| `number_convert` | `value`, `from`, `to` | 掩码↔前缀长度、二/十/十六进制互转 | 纯计算 |
| `ping_host` | `host`, `count`=3 | ICMP ping，返回延迟/丢包 | Windows 可能需提权；备选 TCP connect；白名单+限速 |
| `http_probe` | `url`, `method`=GET | 返回状态码、关键响应头、TTFB、是否 HTTPS | 仅允许 http/https、禁内网段（除 127.0.0.1）、3s 超时 |
| `traceroute` / `whois` | — | 路径追踪/注册信息 | P2，MVP 不注册 |

## 4. 安全与边界（对应 NFR-SEC-03）

1. 所有真实网络工具：统一超时、单请求频率限制（同一会话 1 次/秒）、目标校验；
2. 禁止网段扫描、端口批量探测：工具层面不提供"IP 段/端口段"入参；
3. `http_probe` 禁止访问内网保留地址（10/8、172.16/12、192.168/16、169.254/16），127.0.0.1 例外用于本机演示；
4. 工具返回不携带原始异常堆栈给前端，只给中文 message，堆栈进后端日志。

## 5. 智能体 Prompt 草案（system）

```
你是"计算机网络"课程的智能助教，运行在课程演示系统中。
你可以使用工具：
- course_rag_query：检索课程课件与教材，回答概念/原理/协议类问题；
- subnet_calculator：IPv4 子网计算（网络地址、掩码、广播、可用主机）；
- lpm_lookup：路由表最长前缀匹配查表，可展示比对过程；
- dns_lookup：域名 DNS 解析。
行为准则：
1. 回答前先在思考中把问题拆成子问题清单，说明每个子问题需要哪个工具的数据；
2. 需要数据的问题必须调用工具，不得心算编造子网结果；
3. 每轮只调用一个工具，拿到观察结果后逐项核对子问题清单：只要有子问题还没有对应的工具观察结果，就必须继续调用下一个工具；
4. 所有子问题都有工具观察结果支撑后才允许给最终答案；复合问题只调用一次工具通常不足以完整回答；
5. 引用课件内容必须来自 course_rag_query 的检索结果并注明课件名，不得凭记忆虚构课件内容；
6. 最终答案用中文，先给结论再给关键过程，引用检索结果时注明来自哪份课件；
7. 与计算机网络无关的问题不调用工具，简要说明你的服务范围。
```

## 6. 演示用样例问题库（课前预置，保证现场效果）

| 类型 | 样例问题 | 预期工具链 |
|---|---|---|
| 纯计算 | 192.168.10.137/27 的网络地址、广播地址和可用主机范围是什么？ | subnet_calculator |
| 计算+概念 | 上题这个子网的网关一般设哪个地址？为什么？ | subnet_calculator → course_rag_query |
| 路由查表 | 目的地址 10.2.3.4 在这张路由表里应该从哪个接口转发？ | lpm_lookup |
| 真实探测 | www.example.com 解析到哪些 IP？它是什么类型的记录？ | dns_lookup |
| 探测+概念 | 域名解析用的是 TCP 还是 UDP？结合课件说明 | dns_lookup → course_rag_query |
| 纯课程 | 对比 TCP 和 UDP 的区别，课件里是怎么讲的？ | course_rag_query |
