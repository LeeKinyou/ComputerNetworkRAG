# ComputerNetworkRAG · 计算机网络智能学习工作台

面向计算机网络课程的智能学习演示系统：**知识图谱 + 课程检索增强问答（RAG）+ ReAct 智能体 + 每一步可视化 + 人工审批**。

单进程、单端口部署：FastAPI 同时提供 `/api/v2` 接口与前端静态页面，不需要 Docker、Redis、MinIO，也不需要同时开两个服务。

> **当前状态：V2 已可运行（lite 档）。** 后端、前端、课程种子、检索、Agent、审批检查点、统计接口均已实现并做过端到端验证；`v1` 分支保留原版演示系统。

## 已实现

| 模块 | 能力 |
| --- | --- |
| 课程图谱 | 6 章、18 个知识点、21 条关系；点击节点看定义与原文出处 |
| 知识库 | md / txt / pdf / docx / pptx 上传，解析、分块、挂章节；切片预览、上传文档可删除 |
| 混合检索 | jieba 分词 + BM25 + 哈希向量 + RRF 融合，引用可定位到文档与章节 |
| 双问答模式 | 快速检索（RAG）只走检索与组织；智能体（Agent）追加计算与审批，两种链路可现场对比 |
| 每步可视化 | 计划、工具调用、观察结果、流式 token、最终答案与引用，事件可回放 |
| 确定性计算 | IPv4 子网计算工具（`/0`–`/32`，可排除网络/广播地址），结果以计算卡呈现 |
| 人工审批 | 写操作（如「重建索引」）进入 `waiting_user`，LangGraph `interrupt` 挂起；检查点落 SQLite，进程重启后仍可批准 |
| 学情与报告 | `/analytics/overview` 聚合真实运行记录：提问量、完成率、章节关注度、高频问题、近 7 天趋势 |
| 练习中心 | 6 章共 48 道题（单选 + 判断，含 9 道配图题），按章节 / 知识点 / 掌握度组卷，即时批改给解析与出处、错题记录可回跳问答追问 |
| 概念学情 | 教师端按知识点聚合作答：覆盖数、正确率、参与人数、薄弱学生数，直接定位班级共性薄弱点 |
| 图谱联动 | 先修 / 包含 / 关联三种线型与配色（先修带箭头指向后继）；节点按概念掌握度着色，点节点看章节正确率、下一步概念与相关题目，可一键跳练习作答 |
| 界面 | 浅色 / 深色双主题，学生区与教师视图，`Ctrl K` 搜索知识点（适配 Windows） |

## 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite 8 + Tailwind CSS 4 + ECharts 6 + lucide 图标 |
| 后端 | Python 3.12（uv 管理）+ FastAPI + SQLAlchemy async + Pydantic Settings |
| Agent | LangGraph 1.x 显式状态图；`AsyncSqliteSaver` 持久化审批检查点 |
| 存储 | SQLite（`runtime/app.db` 业务库、`runtime/checkpoints.db` 检查点） |
| 检索 | BM25 + 256 维 blake2b 哈希向量 + RRF；配置 `EMBEDDING_*` 后自动切换远端语义向量 |
| 部署 | 单进程 `uv run python -m app.main`，内置静态托管 |

PostgreSQL、Redis、MinIO 的配置字段保留在 `.env`，lite 演示档不启用；切换到 `DB_BACKEND=postgresql` 即可改用外部数据库。

## 快速开始

### 一键启动（推荐）

```powershell
git clone git@github.com:LeeKinyou/ComputerNetworkRAG.git
cd ComputerNetworkRAG
# 首次运行前复制配置模板，按需填写 LLM_API_KEY
Copy-Item .env.example .env
.\start.bat
```

脚本会依次检查 uv、同步依赖、构建前端、启动服务并打开 <http://127.0.0.1:8000>。
`start.ps1 -SkipBuild` 可跳过前端构建，`-NoBrowser` 不自动打开浏览器。

### 手动启动

```powershell
cd backend
uv sync
uv run python -m app.main
```

前端改动后需要重新构建（产物输出到 `backend/app/static`，已被 gitignore）：

```powershell
cd frontend
npm install
npm run build
```

### 配置

`.env` 位于项目根目录，不提交 Git。关键字段：

```dotenv
DB_BACKEND=sqlite
DB_SQLITE_PATH=./runtime/app.db
CHECKPOINT_SQLITE_PATH=./runtime/checkpoints.db

LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=

EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_API_KEY=
```

`LLM_API_KEY` 为空时系统仍可完整演示：检索、计算、审批、引用全部正常，回答使用模板组织；填入后重启服务，答案会额外经过模型润色（失败自动回落到模板）。
`.env` 不会热加载，修改后需重启。

## 演示前重置

停掉服务后在 `backend` 目录执行：

```powershell
uv run python -m app.reset_demo              # 清任务、消息、运行记录
uv run python -m app.reset_demo --documents  # 同时移除上传文档
```

课程种子与三份预置课件始终保留。检查点文件如需清空，删除 `runtime/checkpoints.db` 后重启。

## 目录

```text
backend/
  app/
    config.py     配置与路径解析
    db.py         异步引擎、会话、建表与种子
    models.py     Course/Chapter/Concept/Edge/Document/Chunk/Session/Message/Run/RunStep
    seed.py       预置课程、18 个知识点、21 条关系、3 份课件
    ingest.py     md/txt/pdf/docx/pptx 解析与分块
    retrieval.py  jieba + BM25 + 哈希向量 + RRF
    tools.py      子网计算与知识点查询
    agent.py      LangGraph 状态图、双模式分流与审批中断
    api.py        /api/v2 路由、SSE 与统计
    main.py       单进程入口与静态托管
    static/       前端构建产物（构建生成，不提交）
  README.md       接口清单与事件契约
frontend/
  src/pages/      工作台、问答、图谱、知识库、学情、报告、个人中心、演示大屏
  src/api/        接口客户端与 SSE 解析
docs/v2/          设计与交付文档
start.ps1 / start.bat
```

## 文档

从 [开发文档入口](./docs/v2/README.md) 开始：

- [架构设计说明书](./docs/v2/01-架构设计说明书.md)
- [需求规格与验收标准](./docs/v2/03-需求规格与验收标准.md)
- [API 与事件契约](./docs/v2/05-API与事件契约.md)
- [Agent 与检索实现规范](./docs/v2/06-Agent与检索实现规范.md)
- [前端页面与交互规范](./docs/v2/07-前端页面与交互规范.md)
- [技术复核与单体化部署方案](./docs/v2/11-技术复核与单体化部署方案.md)
- [产品逻辑对标与前端重构](./docs/v2/12-产品逻辑对标与前端重构.md)
- [部署与演示手册](./docs/v2/13-部署与演示手册.md)

## 已知约束

- `starlette` 锁定 `<1.0`：当前 FastAPI 版本与 Starlette 1.x 的 `include_router` 不兼容，会导致路由全部 404。
- lite 档面向单用户演示，`WORKER_CONCURRENCY` 固定为 1，未做并发压测。
- 预置文档不可删除，上传文档可删。
- 检索默认用本地哈希向量（零外部依赖）；`EMBEDDING_BASE_URL / KEY / MODEL` 三项齐全时，启动或上传后重建索引会自动改用远端 embedding，失败整体回退哈希，不会混用两种维度。
