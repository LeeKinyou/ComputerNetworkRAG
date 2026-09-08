# 04 · API 接口设计

> 版本 v0.1 ｜ 2026-09-08 ｜ 状态：待评审
> 约定：所有接口同源（`http://127.0.0.1:8000`），JSON 请求/响应；SSE 响应头 `Content-Type: text/event-stream`。
> 统一错误体：`{ "error_code": "string", "message": "中文说明", "detail": "可选" }`。

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
- 校验：扩展名 ∈ `.md/.txt/.docx`（P1 后追加 `.pdf/.pptx`），大小 ≤ `UPLOAD_MAX_MB`；
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
| entity_type | string | 空 | 实体类型筛选（协议/设备/层次/地址/算法/概念…） |
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

## 8. 通用约定

1. 时间一律 ISO 8601 本地时间字符串（`YYYY-MM-DDTHH:mm:ss`）；
2. ID 规则：`d_` 文档、`s_` 会话、`r_` 运行，后接 6–8 位随机十六进制；
3. 分页：列表接口 MVP 全量返回（数据量小），预留 `?limit=&offset=` 参数位但不实现分页逻辑；
4. 所有 SSE 端点必须在 finally 中关闭 run/连接，避免悬挂；
5. FastAPI 自动生成 `/docs`（Swagger），开发期保留，演示期可由 settings 开关关闭。
