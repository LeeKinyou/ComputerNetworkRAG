# 智网系统 前端

计算机网络智能助教的展示层。Vue 3 + TypeScript + Vite + Tailwind CSS 4 + ECharts 6。

产品逻辑：**一个任务一个任务地做**，而不是按数据实体堆页面。问答、图谱、计划、知识库、学情都围绕 Task / Artifact 组织。

## 快速开始

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

开发服务器把 `/api` 代理到 `http://127.0.0.1:8000`，后端起来后无需改前端配置。

## 构建

```bash
npm run build        # vue-tsc 类型检查 + vite build
```

产物直接输出到 `../backend/app/static`，由 FastAPI 单进程托管，部署时只需运行一个进程、暴露一个端口。

## 页面

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| `/` | 工作台 | 今日任务、待审批、继续学习、最近产物、本周节奏 |
| `/chat` | 智能问答 | 任务工作台：任务列表 / 对话与内联步骤卡 / 计划·产物·来源三栏 |
| `/chat?mode=rag` | 快速检索模式 | 同一工作台的检索模式（`/rag` 会重定向到这里） |
| `/graph` | 知识图谱 | 按掌握度着色，右侧知识点面板可直接起任务 |
| `/path` | 学习计划 | 今日任务 + 章节主线 + 节奏调整 |
| `/documents` | 知识库 | 文档、覆盖章节、切片预览与索引状态 |
| `/progress` | 学习报告 | 学生视角：掌握度、近 7 天、薄弱点、错题本 |
| `/insights` | 学情分析 | 教师视角：高频问题、薄弱点、错因、一键出题 |
| `/profile` | 我的 | 产物、资产统计、最近活动与偏好 |
| `/screen` | 大屏演示 | 全屏深色，展示「一个任务正在发生」 |

## 主题与交互

- 浅色 / 深色双主题，语义色令牌集中在 `src/style.css`；`src/composables/useTheme.ts` 负责切换与持久化（`localStorage` 键 `cnrag-theme`）。
- 首次进入跟随系统 `prefers-color-scheme`，之后以用户选择为准。顶栏右上角可切换。
- 全局搜索提示统一为 `Ctrl K`（不展示 macOS 符号）。
- 大屏页 `/screen` 强制深色，不随全局主题变化。

## 目录

```
src/
  components/
    AppShell.vue         左侧导航 + 顶栏（主题切换、搜索、头像入口）
    GraphCanvas.vue      ECharts 知识图谱画布（掌握度配色、forceDark）
  composables/
    useTheme.ts          主题单例与持久化
  pages/
    OverviewPage.vue     工作台
    ChatPage.vue         智能问答任务工作台（含子网计算卡）
    GraphPage.vue        知识图谱
    PathPage.vue         学习计划
    DocumentsPage.vue    知识库
    ProgressPage.vue     学习报告（学生视角）
    InsightsPage.vue     学情分析（教师视角）
    ProfilePage.vue      我的
    ScreenPage.vue       大屏演示
  mock/
    data.ts              课程、图谱、文档、章节等基础数据
    workbench.ts         任务、步骤、产物、掌握度、学情（本轮新增）
  style.css              设计令牌（颜色、圆角、阴影、动效）
```

## 接后端时改什么

| 现在 | 之后 |
| --- | --- |
| `mock/workbench.ts` 的 tasks / steps / artifacts | 请求 `/api/v2/runs`，产物落 `artifact` 表 |
| 任务步骤与耗时 | 订阅 `/api/v2/runs/{id}/events` 的 SSE 事件流 |
| 掌握度 `masteryMap` | 请求 `/api/v2/graph/mastery`（按用户/班级） |
| 学情 `insights` | 请求 `/api/v2/insights?class=&range=` |
| 图谱 `graphNodes` / `graphLinks` | 请求 `/api/v2/graph` |
| `documents` / 切片预览 | 请求 `/api/v2/documents`、`/api/v2/documents/{id}/chunks` |
| 上传区 | `POST /api/v2/documents`（md / txt / docx / pdf / pptx） |

事件契约沿用 `docs/v2/05`：`meta` / `step_start` / `thought` / `action` / `observation` / `token` / `final` / `interrupt`。

人工审批对应 `interrupt`：前端展示 `ApprovalCard`，确认后调用 resume 接口。

## 截图

```bash
node _shots.cjs      # 需要 127.0.0.1:5173 已启动，输出 shots/*.png（浅色 + 深色）
```
