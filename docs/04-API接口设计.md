# 04 · API 接口设计

> 版本 v0.2 ｜ 2026-09-23 ｜ 状态：待评审
> 约定：所有接口同源（`http://127.0.0.1:8000`），JSON 请求/响应；SSE 响应头 `Content-Type: text/event-stream`。
> 统一错误体：`{ "error_code": "string", "message": "中文说明", "detail": "可选" }`。
> 变更（v0.2）：新增 §8 数据大屏类、§9 学习路径类（原"通用约定"顺延为 §10），§1 总览补 4 行；§2–§7 契约未改动。

## 1. 接口总览

| 方法 | 路径 | 说明 | 形态 |
|---|---|---|---|
| GET | `/api/health` | 健康检查 | JSON |
| GET | `/api/stats` | 概览统计 | JSON |
| POST | `/api/documents/upload` | 上传文档并触发建库 | multipart→JSON |
| GET | `/api/documents` | 文档列表 | JSON |
| DELETE | `/api/documents/{doc_id}` | 删除文档（含索引与文件） | JSON |
| POST | `/api/documents/{doc_id}/reindex` | 对单篇重建索引 | JSON |
| GET | `/api/graph` | 图谱节点与边（筛选/搜索） | JSON |
| GET | `/api/graph/entity/{name}` | 单实体详情与一跳子图 | JSON |
| POST | `/api/rag/chat` | RAG 问答 | **SSE** |
| POST | `/api/agent/chat` | ReAct 智能体问答 | **SSE** |
| POST | `/api/agent/runs/{run_id}/resume` | 人工审批后恢复运行（P1） | **SSE** |
| GET | `/api/sessions` | 会话列表 | JSON |
| GET | `/api/sessions/{session_id}` | 会话消息 | JSON |
| GET | `/api/sessions/{session_id}/runs/{run_id}` | Agent 运行 trace 回放 | JSON |
| GET | `/screen` | 数据大屏独立页面 | HTML |
| GET | `/api/screen/overview` | 大屏一次性聚合（十字段，字段级降级） | JSON |
| GET | `/api/path` | 章节知识点先修图（物化快照） | JSON |
| GET | `/api/path/plan` | 到目标知识点的必修链与学习顺序 | JSON |

## 2. 系统类

### 2.1 GET /api/health

响应 200：

```json
{ "status": "ok", "version": "0.1.0", "llm": "unknown|ok|error", "time": "2026-09-08T15:00:00" }
```

`llm` 为轻量探测结果（可选，请求带 `?check_llm=1` 时发起一次最小请求，默认不探测以节省额度）。

### 2.2 GET /api/stats

```json
{
  "documents": 12,
  "documents_indexed": 11,
  "chunks": 486,
  "entities": 1320,
  "relations": 954,
  "sessions": 7
}
```

实体/关系数由 `GraphService` 从 NetworkX 图统计（节点数、边数）。

## 3. 文档类

### 3.1 POST /api/documents/upload

- 请求：`multipart/form-data`，字段 `file`（单文件）；
- 校验：扩展名 ∈ `.md/.txt/.docx/.pdf/.pptx`，大小 ≤ `UPLOAD_MAX_MB`；
- 行为：落盘 `data/uploads/`，写 documents(pending)，**异步**启动 IngestionService 流水线，立即返回。

响应 202：

```json
{ "doc_id": "d_8f31c2", "filename": "第4章-网络层.docx", "ext": ".docx", "status": "pending" }
```

错误：415（扩展名不支持/未启用）、413（超限）。

### 3.2 GET /api/documents

```json
{
  "items": [
    {
      "doc_id": "d_8f31c2", "filename": "第4章-网络层.docx", "ext": ".docx",
      "size_bytes": 248113, "parser": "DocxParser", "status": "indexed",
      "chunk_count": 42, "error": null, "created_at": "2026-09-08T14:31:02"
    }
  ]
}
```

`status`：pending | parsed | indexed | failed | unsupported。

### 3.3 DELETE /api/documents/{doc_id}

删除 uploads/parsed 文件、documents 记录，并调用 LightRAG 删除该文档相关实体（若 LightRAG 版本删除能力不完整，则标记删除并在图谱读取时过滤；此限制在 07 计划任务中验证并记录）。

响应：`{ "deleted": "d_8f31c2" }`

### 3.4 POST /api/documents/{doc_id}/reindex

复用 `data/parsed/{doc_id}.md` 缓存重新 `ainsert`（缓存缺失则重新解析）。响应：`{ "doc_id": "...", "status": "pending" }`。

## 4. 图谱类

### 4.1 GET /api/graph

查询参数：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| keyword | string | 空 | 实体名模糊匹配 |
| entity_type | string | 空 | 实体类型筛选，多个类型用英文逗号分隔（前端类型多选，对应 06 §4.2） |
| limit | int | 500 | 节点上限，防止前端一次渲染过多 |

响应：

```json
{
  "nodes": [
    { "id": "TCP", "name": "TCP", "type": "协议", "description": "面向连接的传输层协议……" }
  ],
  "edges": [
    { "source": "TCP", "target": "三次握手", "label": "包含机制", "description": "……" }
  ],
  "types": ["协议", "设备", "层次", "地址", "算法", "概念"],
  "truncated": false
}
```

边只保留两端节点均在返回节点集合内者；`truncated=true` 时前端提示"已按 limit 截断，请搜索缩小范围"。

### 4.2 GET /api/graph/entity/{name}?neighbors=1

```json
{
  "entity": { "name": "TCP", "type": "协议", "description": "……", "sources": [{"doc_name": "第5章.docx", "chunk_id": "chunk-021"}] },
  "neighbors": [
    { "name": "三次握手", "relation": "包含机制", "description": "……" }
  ],
  "subgraph": { "nodes": [], "edges": [] }
}
```

## 5. RAG 问答（SSE）

### 5.1 POST /api/rag/chat

请求体：

```json
{
  "question": "简述 TCP 三次握手的过程",
  "mode": "hybrid",                 // naive|local|global|hybrid，缺省取 RAG_QUERY_MODE
  "session_id": "s_xxx"              // 可选，缺省新建会话
}
```

SSE 事件序列（`event:` 为事件名，`data:` 为 JSON 字符串）：

```
event: meta
data: {"session_id":"s_xxx","mode":"hybrid"}

event: sources
data: {"items":[{"doc_name":"第5章-传输层.docx","chunk_id":"chunk-021","snippet":"……"}]}

event: token
data: {"delta":"TCP"}

event: token
data: {"delta":" 三次握手……"}

event: final
data: {"answer":"TCP 三次握手……"}
```

异常：`event: error` + `data: {"message":"模型服务超时，请重试"}`，随后服务端关闭流。

## 6. Agent 问答（SSE）

### 6.1 POST /api/agent/chat

请求体：

```json
{
  "question": "192.168.10.137/27 属于哪个子网？网关一般设哪个地址？",
  "session_id": "s_xxx",          // 可选
  "tools": ["subnet_calculator", "course_rag_query"]  // 可选 P1：工具子集，缺省全部启用
}
```

### 6.2 事件协议（前端时间线的唯一数据源）

| event | data 字段 | 时机 | 前端动作 |
|---|---|---|---|
| `meta` | session_id, run_id | 运行创建 | 建立时间线容器 |
| `step_start` | step_no | 每轮循环开始 | 追加第 N 步分组 |
| `thought` | step_no, content | 模型思考产出 | 蓝色思考卡片，支持流式追加（若 LLM 非流式则一次性显示） |
| `action` | step_no, tool, args | 决定调用工具 | 橙色行动卡片，展示工具名与格式化参数 |
| `observation` | step_no, status, elapsed_ms, result, structured | 工具返回 | 绿色/红色观察卡片，显示耗时，structured 用于富渲染 |
| `token` | delta | 最终回答生成 | 底部答案区逐字追加 |
| `final` | answer, truncated?, steps_count | 结束 | 标记完成，写入历史 |
| `interrupt` | step_no, tool, args | 待审批工具执行前暂停（P1，HITL） | 行动卡片下展示批准/改参/拒绝 |
| `resumed` | run_id, decision | 审批后新流开启（P1） | 接续原时间线，不新建容器 |
| `error` | message | 任意阶段失败 | 红色错误条 + "重试本轮"按钮 |

示例：

```
event: meta
data: {"session_id":"s_abc","run_id":"r_001"}

event: step_start
data: {"step_no":1}

event: thought
data: {"step_no":1,"content":"这是子网计算题，先调用子网计算器。"}

event: action
data: {"step_no":1,"tool":"subnet_calculator","args":{"ip_cidr":"192.168.10.137/27"}}

event: observation
data: {"step_no":1,"status":"success","elapsed_ms":12,
       "structured":{"network":"192.168.10.128","prefix":27,"netmask":"255.255.255.224",
       "broadcast":"192.168.10.159","first_host":"192.168.10.129","last_host":"192.168.10.158","host_count":30},
       "result":"网络地址 192.168.10.128/27，可用主机 192.168.10.129-158，共 30 台。"}

event: step_start
data: {"step_no":2}
...（course_rag_query 行动与观察）...

event: final
data: {"answer":"……","steps_count":2,"truncated":false}
```

### 6.3 断线与重连

- EventSource `onerror` 时前端自动重连一次；SSE 为一次性流，重连后无法续传，提示用户"连接中断，请重试"；
- 已落库的步骤不丢失，可通过 6.4 回放接口恢复已完成部分。

### 6.4 GET /api/sessions/{session_id}/runs/{run_id}

```json
{
  "run": { "run_id": "r_001", "question": "……", "final_answer": "……", "status": "success",
           "steps_count": 4, "started_at": "...", "finished_at": "..." },
  "steps": [
    { "step_no": 1, "kind": "thought", "content": "……" },
    { "step_no": 1, "kind": "action", "tool_name": "subnet_calculator", "tool_args": {"ip_cidr":"..."} },
    { "step_no": 1, "kind": "observation", "status": "success", "elapsed_ms": 12,
      "content": "……", "structured": { } }
  ]
}
```

前端用同一套时间线组件渲染，实现"实时流"与"历史回放"复用。

### 6.5 POST /api/agent/runs/{run_id}/resume（P1，人工审批）

中断原理见 03 §3.4：中断时 Checkpointer 已按 thread_id=run_id 持久化图状态，本端点用同一 run_id 恢复。

请求体：

```json
{ "decision": "approve", "edited_args": null }
```

- `decision`：`approve`（按原参数执行）/ `edit`（用 `edited_args` 替换工具参数后执行）/ `reject`（取消该工具，向图中回注"用户拒绝"结果，由模型重新决策）；
- 响应：**新的 SSE 流**，首帧 `event: resumed`，后续事件序列与 6.2 相同（action/observation/…/final），前端追加到原时间线；
- 错误：run_id 不存在或无中断 → 409 `{"error_code":"NO_PENDING_INTERRUPT"}`；HITL_ENABLED=false 时调用 → 400。

## 7. 会话类

### 7.1 GET /api/sessions

```json
{ "items": [ { "session_id": "s_abc", "title": "192.168.10.137/27……", "mode": "agent",
               "last_active_at": "2026-09-08T15:02:11" } ] }
```

### 7.2 GET /api/sessions/{session_id}

```json
{ "session": { "session_id": "s_abc", "mode": "agent", "title": "……" },
  "messages": [ {"role":"user","content":"……","run_id":null},
                {"role":"assistant","content":"……","run_id":"r_001"} ] }
```

## 8. 数据大屏类

### 8.1 GET /screen（HTML）

大屏独立页面，非 `/` 单页应用的一个 Tab：深色、固定 1920×1080 画布 + JS 等比缩放。普通路由，注册顺序**必须早于** `StaticFiles("/")` 兜底，否则会被静态挂载吃掉。

### 8.2 GET /api/screen/overview

大屏唯一取数入口。固定十个字段，一次返回：

```json
{
  "stats":        { "documents": 12, "documents_indexed": 11, "chunks": 486,
                    "entities": 1591, "relations": 2375, "sessions": 7 },
  "entity_types": [ { "type": "CONCEPT", "count": 412 } ],
  "top_entities": [ { "name": "TCP", "type": "PROTOCOL", "degree": 120 } ],
  "top_relations":[ { "label": "使用", "count": 88 } ],
  "chapters":     [ { "chapter": 4, "documents": 3, "chunks": 44, "entities": 512 } ],
  "tools":        [ { "name": "subnet_calculator", "calls": 31, "avg_ms": 12, "ok_rate": 1.0 } ],
  "trend":        [ { "date": "2026-09-23", "count": 9 } ],
  "runs":         { "total": 24, "steps": 136, "interrupted": 2 },
  "feed":         [ { "text": "192.168.10.137/27……", "created_at": "2026-09-23T10:02:11" } ],
  "coverage":     { "touched": 50, "total": 1591, "rate": 0.0314 }
}
```

约定与口径：

- **永远 200**：十个字段各自 try/except，单字段失败只把自己降级成占位值（`stats`/`runs` 归零、`coverage` 为 `{0,0,0.0}`、数组类为空数组、`trend` 为 14 天全 0），其余字段照常返回，前端面板保留占位文字。**没有"整屏失败"这个状态**；
- `stats` 与 §2.2 `/api/stats` 调同一个 `core_stats`，两处数字必然一致；
- `entity_types` / `top_entities` / `top_relations` 来自**同一次全量图谱快照**，不受 §4.1 `/api/graph` 的 `limit` 截断影响（用截断后的子图聚合会让大屏数字小于真实值）；`top_*` 各取前 10；
- `chapters` 按文件名里的"第 N 章"归章，解析不出的文档不进该图；
- `tools.avg_ms` 与 `ok_rate` 由 `agent_steps` 自连接 `(run_id, step_no)` 得到——`tool_name` 在 action 行、耗时与状态在 observation 行，直接按 action 行分组会得到全 0；无配对观测行时两字段为 `null`（不是 0）；
- `trend` 固定 14 天连续序列，缺日补零（否则前端折线会断点）；
- `feed` 为最近 20 条用户提问，同一秒内用 `rowid` 兜底排序；
- `coverage` **口径与 `#/path` 完全同源**：分母 = `knowledge_node` 中 `chapter IS NOT NULL` 的点数，分子 = 其中在 `knowledge_touch` 有 ≥1 条**已回填 kp_id** 记录的点数；未回填的触达不计（宁少不假）；快照为空时 `rate=0.0` 且前端隐藏进度条。

## 9. 学习路径类

读侧两个端点，**只查 SQLite 的物化快照**，不碰 LightRAG、不调 LLM，因此与建库/额度无关、毫秒级返回。数据由离线脚本 `scripts/build_learning_path` 生成（见 09 号文档 §3.3）。

### 9.1 GET /api/path?chapter=&limit=

| 参数 | 默认 | 说明 |
|---|---|---|
| `chapter` | `0` | 章号；`0` 或省略 = 全部章，每章各取前 `limit` 个知识点 |
| `limit` | `40` | 每章知识点上限，**硬上限 200**（防演示现场手改 URL 拖死浏览器） |

```json
{
  "nodes": [ { "kp_id": "kp_1a2b3c4d", "name": "TCP", "type": "PROTOCOL",
               "chapter": 4, "degree": 120, "description": "……",
               "layer": 2, "touch_count": 3 } ],
  "edges": [ { "source": "kp_…", "target": "kp_…", "chapter": 4,
               "reason": "TCP 头部字段建立在 IP 数据报封装之上", "confidence": 0.9 } ],
  "chapters": [1, 2, 3, 4, 5, 6, 8],
  "truncated": true
}
```

- `layer` 由后端算（最长路径分层，层号 = 到该点的最长链长度），前端据此摆坐标 `x = layer × 180`，不再自行布局；检出环时环内节点强制收敛，不会死循环；
- `chapters` 只列**真正有知识点**的章，供下拉框渲染，避免点开空图；
- `truncated=true` 表示本章还有未返回的知识点（受 `limit` 截断）；
- 边一律裁到两端都在节点集内——留一条悬空边，ECharts 关系图会直接报错；
- 空态由前端区分文案：无节点 → "尚未物化知识点 / 该范围内没有已归章的知识点"；有节点无边 → 提示"还没有前驱关系"并给出构建命令。

### 9.2 GET /api/path/plan?target=kp_xxxx

到目标知识点的必修链：反向 BFS 取先修闭包，再按 **（章号, 拓扑层, 名字）** 排序。章号作主排序键是刻意的——LLM 抽错边只会把同章内部顺序排歪，不会让第 8 章插到第 2 章前面。

```json
{
  "target": { "kp_id": "kp_…", "name": "TCP 拥塞控制", "type": "CONCEPT", "chapter": 5, "degree": 41 },
  "steps":  [ { "kp_id": "kp_…", "name": "…", "type": "…", "chapter": 5, "degree": 12,
                "reason": "指向该点的最高置信边的依据", "touch_count": 0 } ],
  "no_prereq": false
}
```

- 闭包只剩目标自身时 `no_prereq=true`（该点没有已知先修）；
- 目标不在物化快照 → **404** `{"error_code":"PATH_TARGET_NOT_FOUND","message":"目标知识点不在物化快照中，请先运行构建脚本"}`，不做相近名模糊匹配；
- 重建索引后知识点改名会留下悬空边，读侧跳过而不报 500。

## 10. 通用约定

1. 时间一律 ISO 8601 本地时间字符串（`YYYY-MM-DDTHH:mm:ss`）；
2. ID 规则：`d_` 文档、`s_` 会话、`r_` 运行，后接 6–8 位随机十六进制；
3. 分页：列表接口 MVP 全量返回（数据量小），预留 `?limit=&offset=` 参数位但不实现分页逻辑；
4. 所有 SSE 端点必须在 finally 中关闭 run/连接，避免悬挂；
5. FastAPI 自动生成 `/docs`（Swagger），开发期保留，演示期可由 settings 开关关闭。
