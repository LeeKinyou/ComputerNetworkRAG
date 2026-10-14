# ComputerNetworkRAG · 计算机网络课程智能问答演示系统

面向"计算机网络"课程的单机演示系统：上传课程课件自动构建知识图谱，提供 RAG 课程问答与 ReAct 智能体问答——智能体可调用子网计算、路由查表、DNS 解析、课程检索等工具，每一步"思考 → 行动 → 观察"在时间线中全程可视化，真实网络操作支持人工审批（批准/改参/拒绝后断点续跑）。在此之上叠加**学习路径**（章节知识点先修图 + 到目标知识点的必修链 + 问答触达记录）与**投屏数据大屏**（`/screen`，独立深色页面）。

**单进程部署、无外部数据库与中间件、前端同源托管**，一条命令即可启动演示。

## 功能总览

| 视图 | 能力 |
|---|---|
| 概览 | 建库统计、知识图谱速览、实体类型分布、高频关系 Top 8、数据大屏入口 |
| 知识图谱 | 力导向布局、缩放/拖拽、实体搜索与类型筛选、点击查看详情与来源文档、邻接高亮；可新窗口打开 LightRAG 官方控制台（3D 图谱、文档流水线、实体编辑，需 `LIGHTRAG_CONSOLE=true`） |
| 学习路径 | 按教材章节展开知识点先修图（后端分层，非力导堆叠），点目标知识点给出反向先修闭包与学习顺序，问答命中过的知识点标"已触达"。数据由离线脚本 `scripts/build_learning_path` 物化，页面不触发 LLM 批量调用 |
| RAG 问答 | 基于课程课件的检索增强问答，流式输出、来源可溯源、多种检索模式 |
| ReAct 智能体 | 工具调用全过程时间线（子网计算结构化结果、路由匹配 trace、检索分块），复合问题多轮工具推进，历史回放 |
| 知识库管理 | md/txt/docx/pdf/pptx 上传、解析建库状态跟踪、增量重建索引 |
| 数据大屏 `/screen` | 独立深色页面（非工作台 Tab）：1920×1080 等比缩放、7 张指标卡 + 6 张统计图 + 实时动态跑马灯，总览 30s / 图谱 5min 双周期轮询，单字段取数失败只降级自己 |

## 技术栈

- **后端**：Python 3.12 + FastAPI，依赖由 [uv](https://docs.astral.sh/uv/) 管理
- **RAG / 知识图谱**：[LightRAG](https://github.com/HKUDS/LightRAG)（本地文件存储，无需 Neo4j）
- **智能体**：LangChain/LangGraph 1.x 预构建 ReAct（`create_agent`），SQLite 检查点支撑人工审批中断续跑
- **前端**：Vue 3 + ECharts（CDN 引入，无 npm 构建），SSE 流式渲染
- **LLM**：任意 OpenAI 兼容接口（默认 DeepSeek），密钥仅存于本地 `.env`

## 快速开始

环境要求：Windows 10/11（macOS/Linux 等价）、可访问 LLM API 的网络；**不需要** Docker / MySQL / Redis / Node.js。

```powershell
# 1. 安装 uv（仅首次；已装可跳过）
irm https://astral.sh/uv/install.ps1 | iex

# 2. 创建虚拟环境并安装依赖（Python 3.12 缺失时 uv 自动下载）
uv sync

# 3. 配置密钥：复制 .env.example 为 .env，填入 LLM / Embedding 的 key 与基址
Copy-Item .env.example .env
notepad .env

# 4. 启动
uv run python main.py
```

浏览器打开 <http://127.0.0.1:8000> → 进入"知识库管理"上传课程材料建库 → 到"知识图谱"和"RAG 问答"查看效果。要看"学习路径"页与大屏的"知识点触达覆盖率"，建库后还需手动跑一次 `uv run python -m scripts.build_learning_path --all --nodes-only`（零额度；抽先修边要去掉 `--nodes-only`，会调 LLM），跑完重启服务。

> 完整安装步骤、演示前自检清单、六分钟演示脚本与常见问题见 [docs/08-部署手册与演示脚本.md](docs/08-部署手册与演示脚本.md)。

## 目录结构

```
├─ main.py            # 应用入口（FastAPI 单进程，同源托管前端）
├─ app/
│  ├─ agent/          # ReAct 智能体：builder / runner / 工具注册表 / 审批与多轮中间件
│  ├─ api/            # REST 与 SSE 端点（documents / graph / rag / agent / approval / screen / path / health）
│  ├─ parsers/        # md / txt / docx / pdf / pptx 解析器
│  ├─ rag/            # LightRAG 工厂与查询封装
│  ├─ services/       # 业务服务（建库流水线、RAG、Agent 会话、大屏聚合、学习路径、触达埋点）
│  └─ storage/        # SQLite 仓储（会话 / 消息 / trace / 文档元数据 / 知识点物化）
├─ scripts/           # 离线脚本：build_learning_path（知识点与先修边构建）、validate_lightrag
├─ static/            # 前端（Vue 3 CDN 全局构建，FastAPI 同源托管；screen.html 为独立大屏页）
├─ docs/              # 全套设计与部署文档
└─ data/              # 运行时数据：知识存储、上传文件、SQLite（app.db / langgraph.db）
```

## 运行测试

```powershell
uv run pytest
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.md](docs/README.md) | 文档索引、术语表、全局约定 |
| [01 需求规格](docs/01-需求规格说明书.md) | 背景、功能/非功能需求、验收标准 |
| [02 架构设计](docs/02-架构设计说明书.md) | 架构决策、技术选型、存储策略 |
| [03 详细设计](docs/03-详细设计说明书.md) | 模块职责、ReAct 状态机、SQLite 表结构 |
| [04 API 设计](docs/04-API接口设计.md) | REST 端点、SSE 事件协议 |
| [05 Agent 与工具](docs/05-Agent与网络工具设计.md) | ReAct 循环、工具接口规范、安全边界 |
| [06 前端规范](docs/06-前端设计规范.md) | 六个视图 + 独立大屏页、交互流程、双主题设计令牌 |
| [07 开发计划](docs/07-开发计划与任务拆解.md) | M0–M5 里程碑、任务清单与交付状态 |
| [08 部署手册](docs/08-部署手册与演示脚本.md) | 安装配置、演示脚本、FAQ |
| [09 数据大屏与学习路径](docs/09-数据大屏与学习路径设计.md) | M5 方案与任务拆解：`/screen` 设计、知识点物化与先修边、触达埋点 |
| [10 作业批改与用户体系](docs/10-作业批改与用户体系设计.md) | M6 设计稿（**尚未实现**）：注册登录、图片上传、多模态批改 |

## 安全提示

- `.env` 中的 API 密钥**不提交 git、不发给别人、不截图**，日志中不打印 key 与 Authorization 头；
- 真实网络工具（DNS/HTTP 探测）执行前需人工审批，系统禁止网段扫描与端口批量探测；
- LightRAG 官方控制台（`LIGHTRAG_CONSOLE`）默认关闭：它含删文档、清缓存、改写图谱的写接口，
  未配 `AUTH_ACCOUNTS` 或 `LIGHTRAG_API_KEY` 时**不鉴权**，公网服务器上必须先配凭据再开启。
