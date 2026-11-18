# 后端：CNRAG 计算机网络智能助教

单进程 FastAPI：API、Agent 执行、前端静态托管在同一个端口（默认 `127.0.0.1:8000`）。

## 启动

```powershell
# 首次
cd backend
uv sync

# 前端产物（若尚未构建）
cd ..\frontend; npm ci; npm run build

# 启动（在 backend 目录）
uv run python -m app.main
```

打开 `http://127.0.0.1:8000`，接口文档在 `http://127.0.0.1:8000/api/docs`。

## 数据库

`.env` 中 `DB_BACKEND` 决定存储：

- `sqlite`（默认，演示推荐）：`DB_SQLITE_PATH=./runtime/app.db`，首次启动自动建表并写入种子课程，零外部依赖；
- `postgresql`：`DB_POSTGRES_DSN` 指向 PostgreSQL，适合联调真实链路。

演示场景建议保持 SQLite：单文件、可随仓库目录一起拷贝、断网也能跑。

## 模型

`LLM_API_KEY` 为空时，Agent 用确定性模板组织答案（检索、子网计算、审批、事件流全部可用），适合离线演示；
填入 Key 后，`compose` 阶段由模型润色回答，失败会自动回落到模板，不阻塞主流程。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v2/health` | 健康检查、模型与索引状态 |
| GET | `/api/v2/meta` | 课程概况、演示问题 |
| GET | `/api/v2/courses/{id}/graph` | 图谱节点与关系 |
| GET | `/api/v2/concepts/{id}` | 知识点详情与相关原文 |
| GET/POST | `/api/v2/courses/{id}/documents` | 文档列表 / 上传（md、txt、pdf、docx、pptx） |
| GET | `/api/v2/documents/{id}/chunks` | 分块预览 |
| POST | `/api/v2/search` | BM25 + 向量 + RRF 检索 |
| GET | `/api/v2/sources/{chunk_id}` | 引用片段与相邻原文 |
| POST | `/api/v2/chat-sessions/{id}/runs` | 创建一次问答运行（202） |
| GET | `/api/v2/chat-sessions` | 会话列表，含每个会话最近一次运行 |
| GET | `/api/v2/runs/{id}` | 运行详情：答案、引用、卡片、待审批输入 |
| GET | `/api/v2/runs/{id}/steps` | 运行事件回放（前端恢复历史任务） |
| GET | `/api/v2/runs/{id}/events` | SSE：计划、工具调用、观察、token、审批、终态 |
| POST | `/api/v2/runs/{id}/inputs` | 审批结果，恢复被中断的运行 |

## 事件流

`run.queued / step_start / plan / action / observation / token / final / input.required / resumed / run.failed / run.cancelled`

每条事件带 `id`（run 内递增 seq），前端按 seq 去重；终态后连接关闭。

## Agent 结构

`app/agent.py` 用 LangGraph `StateGraph`：分析 → 检索 → 计算 → 审批 → 组织 → 落库。
写操作（如「重建第 4 章索引」）会进入 `waiting_user`，`interrupt()` 挂起；前端提交
`POST /runs/{id}/inputs` 后以 `Command(resume=...)` 继续。审批参数带 `args_hash`，客户端不能改写。

检查点由 `AsyncSqliteSaver` 落在 `CHECKPOINT_SQLITE_PATH`（默认 `runtime/checkpoints.db`），
进程重启后仍可恢复 `waiting_user` 的运行；应用启动时在 lifespan 中注入，测试脚本单独导入
`app.agent` 时回落到内存存储。

## 目录

```
app/
  config.py      配置与路径
  db.py          异步引擎、会话、建表
  models.py      Course/Chapter/Concept/Edge/Document/Chunk/Session/Message/Run/RunStep
  seed.py        预置课程、18 个知识点、21 条关系、3 份课件
  ingest.py      md/txt/pdf/docx/pptx 解析与 600–1000 字分块
  retrieval.py   BM25 + 哈希向量 + RRF
  tools.py       子网计算、知识点查询
  agent.py       LangGraph 状态图与审批中断
  api.py         /api/v2 路由与 SSE
  main.py        单进程入口与静态托管
```

## 已知约束

- `starlette` 锁定 `<1.0`：当前 FastAPI 版本与 Starlette 1.x 的 `include_router` 不兼容，会导致路由不生效。
- lite 档只适合单用户演示，`WORKER_CONCURRENCY` 固定为 1；
- 预置文档不可删除，上传文档可删。
