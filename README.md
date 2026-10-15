# ComputerNetworkRAG · 计算机网络智能学习工作台

面向计算机网络课程的智能学习项目，围绕 **课程学习 → 助教问答 → 在线答题 → 自动批改 → 错题复习 → 再次练习** 构建完整学习流程。

V2 将采用具有任务规划、课程检索、确定性计算和结果校验能力的 Agent，结合知识点与学习记录提供辅导。回答引用可定位的课程来源，计算结果由工具校验，评分与历史作答可追溯。

> **当前状态：V2 处于架构设计阶段。** 本分支已包含设计文档和配置模板，尚未创建后端、前端、迁移、测试或 Docker Compose 文件。下文功能与技术栈为建设目标，不代表已经实现；目前没有可执行的 V2 启动命令。

## 分支说明

| 分支 | 用途 |
| --- | --- |
| `v1` | 保存原版演示系统及其提交历史 |
| `v2` | 从零重建的工作台，使用独立代码与提交历史 |

旧版代码和部署说明请查看 `v1`。V1 的运行数据、凭据与数据库不会自动迁入 V2。

## 规划功能

| 模块 | 目标能力 |
| --- | --- |
| 课程学习 | 章节、资料、规范知识点与先修关系 |
| 智能助教 | 多轮上下文、按需任务拆解、工具调用、证据检查与引用 |
| 网络计算 | 子网划分、最长前缀匹配、时延等确定性计算 |
| 练习中心 | 按章节/知识点选题、草稿、分级提示、正式提交 |
| 自动批改 | 客观题规则评分、计算工具校验、简答题按评分项点评 |
| 错题复习 | 错因定位、关联课件、先修知识复习与同类再练 |
| 管理后台 | 文档建库、题目版本与审核、任务状态、运行与效果评估 |

首个实现场景是 **IPv4 子网划分咨询 → 连续追问 → 完成练习 → 提交批改 → 复习再练**。先打通这一流程，再扩展更多题型；图片识别和多模态批改安排在文本答题之后。

## 技术架构

采用模块化单体：API、worker、dispatcher 使用同一个后端代码库，按运行职责分进程。

```mermaid
flowchart TD
    Web[Vue 3 / TypeScript] --> API[FastAPI]
    API --> Services[业务模块 / 助教应用服务]
    Services --> DB[(SQLite 或 PostgreSQL)]
    Services --> Redis[(Redis：缓存 / 限流 / 通知)]
    Services --> MinIO[(MinIO：文件 / 报告 / 索引)]
    Dispatcher[Dispatcher / Reconciler] --> DB
    Dispatcher --> MQ[基于 Redis Streams 的消息队列]
    MQ --> Worker[Worker：Agent / 建库 / 批改]
    Worker --> Services
    Worker --> Models[LLM / Embedding]
    Worker -. 更新进度 .-> Redis
    API -. SSE .-> Web
```

图中的 Redis 缓存与 Streams 消息队列默认由同一个 Redis 服务提供。

| 层 | 选型与职责 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Pinia；Element Plus 与 ECharts |
| 后端 | Python、FastAPI、Pydantic |
| 数据库 | SQLAlchemy + Alembic；SQLite / PostgreSQL 由 `.env` 选择 |
| Agent | LangGraph 显式状态图，LangChain 模型与工具适配 |
| 消息队列 | **Redis Streams**：文档建库、Agent 执行、作业批改异步任务 |
| 缓存与通知 | Redis TTL 缓存、限流、Pub/Sub 唤醒；最终结果与回放事件存 SQL |
| 对象存储 | MinIO 私有存储：原始课件、解析产物、附件、报告和检索快照 |
| 检索 | 版本化快照、中文 BM25、向量召回、RRF 融合；两种数据库模式共用基线 |
| 部署 | 计划通过 Docker Compose 编排，并按所选数据库启动相应服务 |

SQL 是业务事实来源，Redis 承接消息与临时数据，MinIO 保存文件。任务使用 SQL jobs/outbox、消费确认、幂等和租约恢复；SSE 断线不取消后台任务。

## 配置准备

配置字段见 [`.env.example`](./.env.example)。这些字段当前是后续实现的配置契约，尚无运行代码读取。

在项目根目录执行以下 PowerShell 命令，仅在 `.env` 不存在时复制模板：

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

已有旧版 `.env` 时，请根据模板手动补齐 V2 字段。本地 `.env` 不提交 Git。

模板默认采用“本机运行后端 + 本机基础设施”，已填 IP、端口、开发账号、密码和数据库名：

| 服务 | 默认地址 | 默认账号 / 密码 | 数据库或 bucket |
| --- | --- | --- | --- |
| PostgreSQL（默认启用） | `127.0.0.1:5432` | `cnrag` / `cnrag_dev_password` | `cnrag` |
| Redis | `127.0.0.1:6379` | 本地默认不启用认证 | `0` |
| MinIO S3 API | `127.0.0.1:9000` | `cnrag_dev` / `cnrag_dev_minio_password` | `cnrag-v2` |
| SQLite（可切换） | `./runtime/app.db` | 不需要账号密码 | 本地文件 |

这些参数不是自动创建服务的指令。基础设施需安装并启动、创建对应 PostgreSQL 用户/数据库和 MinIO 服务凭据/bucket；已有服务配置不同才需要修改。默认凭据仅供本地开发，生产部署必须更换。

### 数据库选择

SQLite 模式适合单机开发和低负载演示：

```dotenv
DB_BACKEND=sqlite
DB_SQLITE_PATH=./runtime/app.db
CHECKPOINT_SQLITE_PATH=./runtime/checkpoints.db
WORKER_CONCURRENCY=1
```

PostgreSQL 模式适合集成环境和多用户部署：

```dotenv
DB_BACKEND=postgresql
DB_POSTGRES_DSN=postgresql+asyncpg://cnrag:cnrag_dev_password@127.0.0.1:5432/cnrag
```

模板默认选择 PostgreSQL；本地服务使用上表参数时无需再修改连接字符串。改成 `DB_BACKEND=sqlite` 即选择文件数据库。相对路径统一按项目根目录解析。PostgreSQL 模式忽略 SQLite 路径；checkpoint 连接由工厂根据同一数据库配置派生。

数据库选择在 API、worker、dispatcher 启动时生效，修改后需统一重启。**修改配置只切换连接，不会自动搬迁原有数据。** 新库需要初始化，已有数据跨库转移需执行独立迁移流程。

两种模式均要求 Redis 和 MinIO。SQLite 模式限制同主机单 API、单 worker 且执行并发为 1；PostgreSQL 模式的扩容能力由实际实现与压测验证。

### Redis、MinIO 与模型

- `REDIS_URL`：连接 Redis；`REDIS_NAMESPACE` 隔离环境，运行时进一步加入数据库安装标识。
- `MINIO_ENDPOINT`：不含协议头的 `host:port`；填写服务账号的 access/secret key 和私有 bucket。
- `LLM_*` 默认填写 DeepSeek 地址与模型名，按 [DeepSeek API 文档](https://api-docs.deepseek.com/api/create-chat-completion/) 配置自己的 `LLM_API_KEY`。
- `EMBEDDING_*` 默认填写 SiliconFlow 地址与 `BAAI/bge-m3`，按 [Embedding API 文档](https://siliconflow.readme.io/reference/createembedding) 配置自己的 `EMBEDDING_API_KEY`。两个供应商的密钥不能混用，账号需有相应模型权限与额度。
- 本机运行默认使用 `127.0.0.1`。后续整套容器部署时，由 Compose 为容器注入 `postgres`、`redis`、`minio` 服务地址及 `/app/runtime/...` 路径，保留主机配置的账号、数据库等参数；容器内部不能用 `127.0.0.1` 连接其他服务。同一 SQLite 部署的进程必须访问同一个数据库文件。

当前尚未提供容器和启动脚本，配置准备不代表已经可以启动 V2。

## 开发路线

- [ ] M0：前后端骨架、双数据库适配与迁移、Redis、MinIO、身份与课程种子。
- [ ] M1：消息队列任务链路、会话上下文、课程检索与计算、Agent 首场景、事件恢复。
- [ ] M2：题目版本、答题与提交、确定性和模型评分、批改报告。
- [ ] M3：错题、知识点学习证据、复习计划与再次练习。
- [ ] M4：双数据库集成测试、故障恢复演练、效果评测、界面与部署材料。

验证将覆盖用户数据隔离、隐藏答案隔离、重复提交、重复投递、worker 中断、事件补发、数据库迁移与文件一致性。模型效果通过固定题集评估任务完成率、引用支持、评分偏差、延迟与成本。

## 目录

当前已创建：

```text
README.md
.env.example
.gitignore
docs/v2/
  README.md
  00-重构总设计.md
  01-架构设计说明书.md
  02-合作开发规范.md
  03-需求规格与验收标准.md
  04-数据模型与事务设计.md
  05-API与事件契约.md
  06-Agent与检索实现规范.md
  07-前端页面与交互规范.md
  08-开发环境与测试交付规范.md
  09-三人开发分工与交付计划.md
```

后续代码布局规划为 `backend/`、`frontend/`、`evals/` 和 `deploy/`，详细职责见架构设计。已有本地旧版资料与数据不属于 V2 源码。

## 设计文档

三位新开发者从 [开发文档入口](./docs/v2/README.md) 开始，按 [三人分工与交付计划](./docs/v2/09-三人开发分工与交付计划.md) 领取任务。建议 A 负责底座与身份课程，B 负责知识检索与 Agent，C 负责练习批改与学习反馈；每人同步交付对应页面和测试。

- [重构总设计](./docs/v2/00-重构总设计.md)：产品场景、Agent 能力、练习与评分、数据模型和阶段验收。
- [架构设计说明书](./docs/v2/01-架构设计说明书.md)：双数据库、Redis 消息队列、MinIO、任务一致性、部署与故障恢复。
- [合作开发规范](./docs/v2/02-合作开发规范.md)：分支协作、Git 提交格式、提交检查、审查合并与敏感文件规则。
- [需求规格与验收标准](./docs/v2/03-需求规格与验收标准.md)：角色、需求编号、完整验收脚本与异常表现。
- [数据模型与事务设计](./docs/v2/04-数据模型与事务设计.md)：字段、约束、状态机、事务和迁移顺序。
- [API 与事件契约](./docs/v2/05-API与事件契约.md)：认证、请求响应、幂等、错误码、SSE 和联调规则。
- [Agent 与检索实现规范](./docs/v2/06-Agent与检索实现规范.md)：工具、上下文、子网计算、索引与恢复。
- [前端页面与交互规范](./docs/v2/07-前端页面与交互规范.md)：路由、归属、页面状态、组件和草稿/重连处理。
- [开发环境与测试交付规范](./docs/v2/08-开发环境与测试交付规范.md)：工程交付、环境、公共接口、种子与测试矩阵。
- [三人开发分工与交付计划](./docs/v2/09-三人开发分工与交付计划.md)：A/B/C 责任、首批任务卡、依赖、评审和里程碑退出条件。

基础设施细节以架构设计说明书为准；实际能力随代码、迁移和验证结果交付后更新本文。
