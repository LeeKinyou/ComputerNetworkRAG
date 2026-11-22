# 后端：智网系统

单进程 FastAPI：API、Agent 执行、前端静态托管在同一个端口（默认 `127.0.0.1:8000`）。

## 启动

```powershell
# 首次
cd backend
uv sync                 # 若本机已有 backend\.venv，可跳过本步

# 前端产物（若尚未构建）
cd ..\frontend; npm ci; npm run build

# 启动（在 backend 目录）
.\.venv\Scripts\python.exe -m app.main
# 或者用 uv：uv run python -m app.main
```

打开 `http://127.0.0.1:8000`，接口文档在 `http://127.0.0.1:8000/api/docs`。

## 数据库

`.env` 中 `DB_BACKEND` 决定存储，两种模式共用同一套模型与接口：

- `postgresql`（当前默认）：`DB_POSTGRES_DSN` 指向 PostgreSQL（`postgresql+asyncpg://...`），首次启动自动建表并写入种子课程；
- `sqlite`：`DB_SQLITE_PATH=./runtime/app.db`，单文件、零外部依赖，适合断网或临时演示。

检查点单独由 `CHECKPOINT_BACKEND` 决定（`postgres` 用 `AsyncPostgresSaver`，`sqlite` 用 `AsyncSqliteSaver` + `CHECKPOINT_SQLITE_PATH`）。两者可组合，但一般与业务库保持一致。

从 SQLite 切到 PostgreSQL 时，用 `python scripts/migrate_sqlite_to_pg.py` 迁业务数据；检查点表结构不兼容（SQLite 为 BLOB、PostgreSQL 为 jsonb），历史会话状态不迁移。

Windows 上 `psycopg` 异步只用 SelectorEventLoop，`app.main` 已在入口固定策略；因此不要用 `uvicorn app.main:app --reload` 启动，直接 `python -m app.main`。

## 模型

`LLM_API_KEY` 为空时，Agent 用确定性模板组织答案（检索、子网计算、审批、事件流全部可用），适合离线演示；
填入 Key 后，`compose` 阶段由模型润色回答，失败会自动回落到模板，不阻塞主流程。

Embedding 是可选通道，默认关闭：

- 三项（`EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL`）任一为空 → 用本地 256 维哈希向量，零外部依赖；
- 三项齐全 → 刷新索引时批量向量化（按「切片 id + 文本」缓存到 `RETRIEVAL_CACHE_DIR`，内容不变不重复计费），查询用同一模型编码；
- 远端失败 → 整份索引回退哈希，查询只走 BM25，服务不中断，也不会混用两种维度；
- 换模型或维度后重启即可重建，缓存文件名带模型指纹，不会复用旧向量。

当前生效的通道可从 `GET /api/v2/health` 的 `vector_mode` / `embedder` 字段确认。

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
| POST | `/api/v2/chat-sessions/{id}/runs` | 创建一次问答运行（202），会话归属须与 `user_key` 一致 |
| GET | `/api/v2/chat-sessions` | 会话列表，含每个会话最近一次运行；`user_key` 必填 |
| GET | `/api/v2/runs/{id}` | 运行详情：答案、引用、卡片、待审批输入 |
| GET | `/api/v2/runs/{id}/steps` | 运行事件回放（前端恢复历史任务） |
| GET | `/api/v2/runs/{id}/events` | SSE：计划、工具调用、观察、token、审批、终态 |
| POST | `/api/v2/runs/{id}/inputs` | 审批结果，恢复被中断的运行 |
| GET | `/api/v2/analytics/overview` | 课程使用统计：提问量、完成率、章节关注度、高频问题 |
| GET | `/api/v2/analytics/concepts` | 概念粒度学情：覆盖数、正确率、参与人数、薄弱学生数（可传 `user_key` 只看个人） |
| GET | `/api/v2/questions` | 组卷：支持 `chapter_id`、`concept_id`、`concept_ids`（逗号分隔多概念）过滤（默认随机 10 题，不下发答案） |
| GET | `/api/v2/questions/recommended` | 按掌握度组卷：未练过的概念优先，其次正确率偏低，返回 `reason` 说明推荐理由 |
| POST | `/api/v2/practice/attempts` | 提交作答，即时判分并返回正确答案、解析与出处 |
| GET | `/api/v2/practice/attempts` | 作答历史（题干、对错、时间） |
| GET | `/api/v2/practice/stats` | 练习统计：总正确率、按章节正确率、错题次数排行 |
| GET | `/api/v2/practice/wrongbook` | 错题本：只保留「最近一次仍答错」的题，按概念分组，返回错次数、总作答次数与待复习/已纠正统计 |
| GET | `/api/v2/learning/next` | 学习计划：按掌握度与先修关系排「下一步」，先修未掌握时先插前置任务，返回任务理由、预计分钟、章节进度与近 7 天练习数 |

`GET /health` 会带 `vector_mode`（`hash` / `remote`）与 `embedder` 标签，用于确认当前生效的向量通道。

多租户：`/runs/{id}`、`/runs/{id}/steps`、`/runs/{id}/events`、`/runs/{id}/inputs`、`/runs/{id}/cancel`、`/chat-sessions/{id}/messages` 都要求 `?user_key=`，缺参数返回 422，归属不符统一 404（不区分"不存在"和"不是你的"）。

## 测试

```bash
uv run pytest -q
```

当前覆盖确定性逻辑：子网计算的前缀边界与地址策略、文档解析分块的长度与重叠、双模式的任务计划分流、练习判分的答案归一化（大小写、对/错中英文、空作答）、学习画像的概念分类（未练 / 薄弱 / 正常 / 已掌握）与提示词生成。测试不依赖网络、模型 Key 或运行时数据库。

## 演示前重置

停掉服务后，在 `backend` 目录执行：

```bash
uv run python -m app.reset_demo              # 只清任务、消息、运行记录
uv run python -m app.reset_demo --documents  # 同时移除后台上传的文档
```

课程种子、知识点与三份预置课件始终保留。历史运行对应的检查点不会被这里删除；
需要一并清空时，删除 `runtime/checkpoints.db` 再启动服务。

## 事件流

`run.queued / step_start / plan / action / observation / token / final / input.required / resumed / run.failed / run.cancelled`

每条事件带 `id`（run 内递增 seq），前端按 seq 去重；终态后连接关闭。

## Agent 结构

`app/agent.py` 用 LangGraph `StateGraph`：分析 → 检索 →（计算 → 审批）→ 组织 → 落库。
`mode=rag` 的快速检索走「分析 → 检索 → 组织」，不触达计算与审批；默认的智能体模式保留完整链路。
写操作（如「重建第 4 章索引」）会进入 `waiting_user`，`interrupt()` 挂起；前端提交
`POST /runs/{id}/inputs` 后以 `Command(resume=...)` 继续。审批参数带 `args_hash`，客户端不能改写。

检查点由 `AsyncSqliteSaver` 落在 `CHECKPOINT_SQLITE_PATH`（默认 `runtime/checkpoints.db`），
进程重启后仍可恢复 `waiting_user` 的运行；应用启动时在 lifespan 中注入，测试脚本单独导入
`app.agent` 时回落到内存存储。

## 学习画像

`app/profile.py` 在每次运行开始时，按 `Attempt.user_key` 聚合练习作答，得到每个概念的
「未练 / 薄弱（<60%）/ 正常 / 已掌握（≥80%）」，压成 `profile` 放进初始 state：

- `profile_prompt()` 生成 4–6 行中文提示，拼在回答指令里（薄弱或未练的概念先补基础直觉，已掌握的略过铺垫）；没有作答记录时返回空串，不注入。
- `weak_chapters` 传给 `retriever.search(boost_chapters=...)`，RRF 融合后对这些章节的候选乘 1.15，让引用更贴短板。
- 画像不落库，只给 `runs` 加了一列 `user_key`（默认 `demo_user`），由 `db._ensure_columns()` 补列，旧库无需重建。
- 多身份：前端顶栏可切 `demo_user`（李金阳）/ `stu_lin`（林晓）/ `stu_zhao`（赵一鸣），`Run.user_key` 与 `Attempt.user_key` 都取自这个选择；教师端 `/analytics/concepts` 不传 `user_key`，看到的就是全班。
- 会话隔离：`ChatSession.user_key` 决定会话归属，`GET /chat-sessions?user_key=` 只返回本人会话；新建 run 继承会话的 `user_key`，不采信请求体，避免同一会话里混入别人的运行。
- 租户校验：所有按 id 读取或写入运行的接口都要带 `user_key`，归属不符返回 404；启动时 `_sync_run_owner` 会把早期版本留下的「run 归属与会话归属不一致」按会话对齐一次，幂等。
- 演示数据：`python -m app.seed_students` 幂等写入两名示例学生的作答，方便对比「弱学生」与「强学生」。

## 目录

```
app/
  config.py      配置与路径
  db.py          异步引擎、会话、建表
  models.py      Course/Chapter/Concept/Edge/Document/Chunk/Session/Message/Run/RunStep
  seed.py        预置课程、20 个知识点、23 条关系、3 份课件（启动时幂等补种，老库缺概念/关系会补齐）
  seed_students.py 幂等写入两名示例学生的练习作答
  ingest.py      md/txt/pdf/docx/pptx 解析与 600–1000 字分块
  retrieval.py   BM25 + 向量通道 + RRF（哈希本地 / 远端 embedding 可切换）
  tools.py       子网计算、知识点查询
  agent.py       LangGraph 状态图与审批中断
  profile.py     练习作答聚合为学生画像（问答注入 + 检索加权）
  api.py         /api/v2 路由与 SSE
  main.py        单进程入口与静态托管
```

## 已知约束

- `starlette` 锁定 `<1.0`：当前 FastAPI 版本与 Starlette 1.x 的 `include_router` 不兼容，会导致路由不生效。
- lite 档只适合单用户演示，`WORKER_CONCURRENCY` 固定为 1；
- 预置文档不可删除，上传文档可删。
