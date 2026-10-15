# V2 API 与事件契约

日期：2026-10-15。状态：待实现的 v0.1 契约。前缀 `/api/v2`；接口实现负责人 A/B/C 对应 [09](./09-三人开发分工与交付计划.md)。当前未生成 OpenAPI，不把本文样例当已运行接口。

## 1. 通用协议

- JSON 使用 snake_case；ID 是 UUID 字符串，本文 `<...>` 为占位符；时间 UTC ISO 8601，例 `2026-10-15T08:00:00Z`。字段 nullable 必须在 Schema 中显式声明。
- 成功直接返回资源；分页为 `{ "items": [], "next_cursor": null }`。`limit` 默认 20，范围 1–100；cursor 不透明，排序 `created_at DESC,id DESC`，同一路径不得复用于不同过滤条件。
- 201 创建同步资源；202 已持久化异步任务；200 查询/更新/重复请求；204 退出/无响应体；错误格式固定如下。202 不代表工作已完成。
- Cookie 名 `cnrag_session`，HttpOnly、SameSite=Lax，生产 Secure；前端同源 `/api` 代理且 fetch 携带 credentials。默认会话有效 24 小时，退出立即撤销，禁用用户立即拒绝。
- `GET /auth/csrf` 设置/读取匿名或已登录 CSRF 上下文，返回 `csrf_token`；匿名态使用签名 CSRF Cookie，登录态绑定 auth_session 中的 token hash。登录及所有 POST/PUT/PATCH/DELETE 使用 `X-CSRF-Token`，服务端验证 Origin 和 token。登录成功轮换会话与 CSRF，返回新 csrf_token；CSRF token 不作为登录凭据。
- 账号密码仅登录请求使用，不写日志。M0 不提供公开注册；管理员创建用户。开发种子密码通过本地输入/环境传入，不写 fixture。
- 创建 run/attempt、提示、提交、续跑、取消、重评、接受计划、管理上传/建库/发布等写命令要求 `Idempotency-Key`（客户端 UUID，每次逻辑操作生成一次，重试沿用）。草稿 PUT 用 version CAS。登录/退出不使用持久去重。
- 去重作用域为 owner+operation+key，request_hash 包含路径资源 ID 和规范化 body。相同请求重放返回原响应和资源（HTTP 状态与原响应一致）；相同 key 不同请求 409 `IDEMPOTENCY_KEY_REUSED`。不把未提交事务前的 503 存成成功。
- 输入 DTO 拒绝多余字段；学生业务请求禁止 owner_id、role、score、graph_thread_id。管理员建号等显式 Schema 仍可包含声明的 role。ActorContext 一律服务端注入。隐藏字段使用独立输出 Schema，不靠前端删字段。

```json
{
  "error": {
    "code": "ACTIVE_RUN_EXISTS",
    "message": "当前会话已有活动任务",
    "request_id": "<request-id>",
    "details": { "active_run_id": "<run-id>" }
  }
}
```

| HTTP | code 示例 | 客户端处理 |
| --- | --- | --- |
| 401 | UNAUTHENTICATED | 登录，保留页面草稿 |
| 403 | FORBIDDEN / CSRF_FAILED | 提示权限/刷新 CSRF，不循环重试 |
| 404 | NOT_FOUND | 私人对象无权限也用该错误，避免枚举 |
| 409 | VERSION_CONFLICT / ACTIVE_RUN_EXISTS / ATTEMPT_SUBMITTED / RUN_NOT_WAITING / IDEMPOTENCY_KEY_REUSED | 展示当前版本/活动任务，不自动覆盖 |
| 410 | EVENTS_EXPIRED | 停止 SSE 重连，读取 details.history_url |
| 413 / 415 | FILE_TOO_LARGE / UNSUPPORTED_FILE_TYPE | 保留表单并说明限制 |
| 422 | VALIDATION_ERROR / ANSWER_INCOMPLETE | details.fields 为字段与错误；不含隐藏标准 |
| 429 | RATE_LIMITED | 尊重 Retry-After；不创建新逻辑请求 |
| 503 | DEPENDENCY_UNAVAILABLE / INDEX_NOT_READY | 可重试；同一逻辑操作沿用幂等键 |

request_id 由中间件生成/验证并写响应 `X-Request-ID`。details 仅白名单安全字段；无堆栈、SQL、凭据或私有 object_key。

## 2. 身份与课程（A）

| 方法与路径 | 请求 | 返回 |
| --- | --- | --- |
| GET /auth/csrf | 无 | 200 `{csrf_token}` |
| POST /auth/login | `{username,password}` + CSRF | 200 `{user:{id,username,role},csrf_token}` + Cookie |
| POST /auth/logout | CSRF | 204，撤销并清 Cookie |
| GET /auth/me | Cookie | 200 `{id,username,role}` |
| POST /admin/users | `{username,password,role}` | 201 UserPublic；只管理员 |
| GET /courses | cursor/limit | 已发布 CourseSummary 列表 |
| GET /courses/{id} | 无 | `{id,title,description,status,published_index_version_id}` |
| GET /courses/{id}/chapters | 无 | `{items:[{id,parent_id,title,sort_order}]}`，不分页树 |
| GET /courses/{id}/concepts | chapter_id 可选、cursor/limit | Concept 列表 |
| GET /concepts/{id} | 无 | `{id,course_id,code,title,description,prerequisites:[{id,title}]}` |
| POST /admin/courses | `{title,description}` | 201 草稿 Course |
| PUT /admin/courses/{id} | `{title,description,status,version}` | 200 更新的 Course；发布要求种子/章节存在 |
| POST /admin/courses/{id}/chapters | `{parent_id,title,sort_order}` | 201 Chapter |
| POST /admin/courses/{id}/concepts | `{code,title,description}` | 201 Concept |
| POST /admin/courses/{id}/prerequisites | `{prerequisite_id,target_id,review_status}` | 201 Edge；审核通过前做无环检查 |

M0 首版章节/知识点可先用幂等种子建立；以上最小管理写入在 M4 前完成。不要求首版任意树节点移动/批量编辑，避免超出范围。

## 3. 文档与来源（B；文件适配由 A 提供）

| 方法与路径 | 契约 |
| --- | --- |
| GET /courses/{id}/documents | 已发布文档列表；items 包含 id/title/chapter_id/current_version_id |
| GET /documents/{id} | 文档公开元数据及可读的版本信息；不返回内部存储路径 |
| GET /documents/{id}/versions/{version_id}/content | 200 `{items:[{chunk_id,section_path,text,page,slide}],next_cursor}`；按分块分页，limit 规则同通用列表；version_id 必须属于 document_id |
| POST /admin/documents | multipart：course_id、chapter_id 可选、title、file；默认最大 20 MiB，md/txt/pdf；202 `{document_id,document_version_id,file_id,job_id,status:"queued"}` |
| POST /admin/documents/{id}/versions | multipart file；同上传约束；202 新版本与建库 job |
| GET /admin/documents/{id}/versions | 含解析/失败状态的版本列表，仅管理员 |
| POST /admin/courses/{id}/indexes | `{document_version_ids:[...]}`；202 `{index_version_id,job_id,status:"building"}`；只可选择同课 ready 版本 |
| POST /admin/indexes/{id}/publish | `{version}`；200 `{index_version_id,status:"published"}`；检查 manifest 和产物，原子切指针 |
| GET /sources/{chunk_id} | 200 Evidence 加 text、previous_chunk_id、next_chunk_id；校验文档可读性，保留历史引用 |
| GET /files/{file_id}/download | 通过关联资源授权后流式下载，安全 Content-Disposition；不返回裸 object_key |
| GET /admin/jobs | kind/status/cursor/limit；脱敏任务列表 |
| GET /admin/jobs/{id} | `{job_id,kind,status,attempt_count,dispatch_seq,error_code,created_at,updated_at}`，不含用户答案/私聊 |
| POST /admin/jobs/{id}/retry | 仅 failed 且可重试的 ingest job；202 原 job 新 dispatch_seq；终态 Agent 由用户新建、评分通过 regrades 创建新 revision，不能后台复活终态破坏约束 |

内容读取使用分页平铺分块，前端自行按 section_path 分组，不返回另一套嵌套 sections 结构。

Evidence 固定形状：

```json
{
  "chunk_id": "<chunk-id>",
  "document_id": "<document-id>",
  "document_version_id": "<document-version-id>",
  "title": "IPv4 子网划分",
  "locator": { "section_path": ["IPv4", "CIDR"], "page": null, "slide": null },
  "excerpt": "<课程原文片段>",
  "channels": ["bm25", "vector"]
}
```

非检索来源允许 channels=[]。引用渲染为 `/sources/{chunk_id}` 页面，页面再调用 API。历史版本可读不代表草稿可公开；必须已发布过且仍保留，或管理员鉴权。

## 4. 助教与运行（B）

| 方法与路径 | 请求/返回 |
| --- | --- |
| POST /chat-sessions | `{course_id,title?}` → 201 `{id,course_id,title}` |
| GET /chat-sessions | course_id 可选、cursor/limit → 本人列表 |
| GET /chat-sessions/{id}/messages | cursor/limit → Message 列表，含 turn_no；前端按 turn_no 展示 |
| POST /chat-sessions/{id}/runs | 下方 RunCreate → 202 RunAccepted；同会话活动冲突 409 |
| GET /runs/{id} | 200 RunDetail，始终可读取持久结果 |
| GET /runs/{id}/events | SSE；见第 7 节 |
| POST /runs/{id}/inputs | `{input_id,run_version,answer:{text?,approved?}}` → 202 RunAccepted；input_id 必须匹配当前 pending_input；拒绝审批可终止对应任务 |
| POST /runs/{id}/cancel | `{}` → 202 `{run_id,status,cancel_requested:true}`；已终态 200 原状态，不能复活 |

```json
{
  "message": "计算 192.168.10.137/27，并推荐一道题",
  "mode": "course_qa",
  "context_refs": [{ "type": "chapter", "id": "<chapter-id>" }]
}
```

mode 枚举：course_qa/network_calc/practice_help/post_review/review_plan。message 长度 1–8000 字符；context_refs 最多 10 个，type=chapter/question_version/attempt/report/concept，id 由服务端重新验证课程、版本与 owner。切换客户端 mode 不能提高权限。新会话课程固定，跨课新建会话。

RunAccepted：`{run_id,job_id,session_id,status,events_url}`。

RunDetail：`{run_id,session_id,status,version,stage,cancel_requested,pending_input,result,error_code,latest_seq}`。pending_input=null 或 `{input_id,kind:"clarification"|"approval",prompt,tool_call_id?,args_hash?}`；审批记录额外绑定当前参数哈希，客户端不能自行更改工具参数。

result=null 或 `{answer_markdown,citations:[Evidence],cards:[Card],completed_tasks:[],incomplete_tasks:[]}`。Card 用 type 区分：calculation（工具名/结构化数值）、practice（安全题目版本 ID/题干）、report（本人答卷/报告 ID）、review_proposal（建议与依据）；禁止在卡片塞任意 ORM 对象。

## 5. 题目、草稿和报告（C）

| 方法与路径 | 请求/返回 |
| --- | --- |
| GET /questions | course_id 必填，chapter_id/concept_id/type 可选；只返回已审核发布的 QuestionPublic 列表 |
| GET /questions/{id} | 当前已发布 QuestionPublic；历史答卷通过 attempt 读取固定版本 |
| POST /admin/questions | `{course_id,chapter_id?,version:QuestionAdminInput}` → 201 逻辑题目和草稿版本 |
| POST /admin/questions/{id}/versions | QuestionAdminInput → 201 新草稿版本，不能原地改已发布题 |
| POST /admin/question-versions/{id}/publish | `{}` → 200 已审核版本；可解性和标准完整性检查后发布 |
| GET /admin/questions/{id}/versions | 管理员私有列表，包含标准/rubric；学生禁止 |
| POST /attempts | `{course_id,question_version_ids:[...],origin}`，origin 为 practice 或 review → 201 AttemptDetail；1–20 题，同课、可见且已发布 |
| GET /attempts | course_id/status/cursor/limit → 本人列表 |
| GET /attempts/{id} | AttemptDetail，固定题版本、已保存答案、version；不返回标准快照 |
| PUT /attempts/{id}/answers | `{version,answers:[{attempt_item_id,answer:Answer}]}` → 200 `{attempt_id,version,saved_at}`；全量替换本次列出的 item，未列出项不改；字段原子保存 |
| POST /attempts/{id}/hints | `{attempt_item_id,level}`，level 为 1、2、3 → 200 `{level,hint_markdown,hint_level_used}`；只限本人 draft，模型慢调用不占 SQL 事务 |
| POST /attempts/{id}/submit | `{version}` → 202 `{attempt_id,status:"submitted",grading_run_id,job_id}`；已提交无论新旧 key 返回首次提交引用，不重新批改 |
| GET /attempts/{id}/report | revision_no 可选；200 ReportEnvelope，未完成也返回明确状态 |
| GET /grading-runs/{id} | 200 本人 ReportEnvelope，历史版本可读取 |
| POST /attempts/{id}/regrades | `{reason}`，限本人已提交答卷且无活动批改；202 新 revision；评分策略由服务端选择，需限流，不能传入分数/标准；跨用户人工复核另设计授权 |

QuestionPublic：`{id,question_version_id,course_id,type,stem_markdown,options,answer_schema,max_score_units,concept_ids}`。options 为 `[{id,text}]` 或空数组。answer_schema 仅含公开作答字段/类型/单位，不能包含正确值或判分阈值。

QuestionAdminInput：`{type,stem_markdown,options,answer_schema,answer_key,rubric,max_score_units,grading_policy_version,concept_ids}`。创建后为 draft，publish 执行人工审核；首版不允许模型自动审核发布。

Answer 判别联合（不匹配题型 422）：

```json
{
  "type": "subnet",
  "fields": {
    "network_address": "192.168.10.128",
    "broadcast_address": "192.168.10.159",
    "first_host": "192.168.10.129",
    "last_host": "192.168.10.158",
    "usable_host_count": 30
  },
  "explanation": "按 /27 的块大小计算"
}
```

其他类型：single_choice=`{type,option_id}`；true_false=`{type,value:boolean}`；short_answer=`{type,text}`。草稿允许 answer=null 或公开字段尚不完整，submit 必须完整且格式有效。提示 1 指方向、2 给方法、3 给局部步骤；未提交均不得提供完整标准答案。

AttemptDetail：`{id,course_id,status,version,submitted_at,items:[{id,ordinal,question:QuestionPublic,answer,hint_level_used}],initial_grading_run_id,latest_valid_grading_run_id}`。

ReportEnvelope：`{attempt_id,grading_run_id,revision_no,status,report}`；status=queued/running/completed/needs_review/failed。未完成或需复核时 report=null，并提供 error_code/review_reason 安全文本；completed 才有 `{total_score_units,max_score_units,items:[{attempt_item_id,score_units,max_score_units,criteria:[{code,score_units,max_score_units,feedback}],feedback,error_tags,evidence_refs,reference_answer}],provenance:{policy_version,model_id,prompt_version}}`。reference_answer 仅正式提交且有效报告可释放；未提交的任何 DTO 均无该字段。

## 6. 学习反馈与复习（C）

| 方法与路径 | 契约 |
| --- | --- |
| GET /learning/summary | course_id 必填；本人近期练习、待复习数、样本数、继续练习入口 |
| GET /learning/concepts | course_id 必填；列表含 concept_id、sample_count、recent_summary、last_practiced_at、evidence_insufficient |
| GET /mistakes | course_id/concept_id/error_tag/cursor/limit；最新有效报告的未满分项 |
| GET /review-proposals | course_id 必填；200 `{origin_key,concept_ids,reason,evidence_refs,suggested_stages:[1,3,7]}`，不写计划 |
| POST /review-plans | `{course_id,origin_key,concept_ids}`；服务端重算合法范围；201 `{id,status,items}` |
| GET /review-plans | status/course_id/cursor/limit；本人计划 |
| GET /review-plans/{id} | 本人计划和各 item 到期时间 |
| POST /review-plans/{id}/items/{item_id}/complete | `{version}`；200 完成项与新建后续阶段；重复不重复加阶段 |
| POST /review-plans/{id}/cancel | `{version}`；200 cancelled；保留历史 |

复习 D05：接受计划以 accepted_at+1 天创建 stage=1；完成该项后以 completed_at+3 天创建 stage=2；再完成后 +7 天创建 stage=3，全部完成则计划 completed。这里“天”是 UTC 时长 24h，页面转换本地时间。完成阅读与再次练习分别记事件，阅读完成不算答对。推荐同类题优先其他题版本；没有其他题就明确标记重复练习。客户端不能直接写 concept_state。

## 7. SSE 协议与恢复（B，A 提供持久事件能力）

`GET /runs/{run_id}/events`，Cookie 鉴权，`Content-Type: text/event-stream`，代理关闭缓冲。每条持久事件包含 `id: <seq>`，seq 只在当前 run 内递增，JSON data 固定 envelope：

```text
id: 12
event: run.stage
data: {"schema_version":1,"run_id":"<run-id>","seq":12,"type":"run.stage","created_at":"2026-10-15T08:00:00Z","payload":{"stage":"verifying","message":"正在核验计算与引用"}}

```

| type | payload |
| --- | --- |
| run.queued / run.started | status |
| run.stage | stage、message（简短可公开摘要） |
| task.updated | task_id、goal、status；不含思维链 |
| tool.completed | tool_call_id、name、status、elapsed_ms、safe_summary；不返回内部参数/隐藏答案 |
| answer.delta | text；仅验证通过后将最终回答分批发布，完整回答仍落 SQL |
| artifact.created | type、artifact_id、安全 card |
| input.required | pending_input |
| run.completed / run.partial | status、result_url（GET run 地址） |
| run.failed / run.cancelled | status、error_code、安全 message |

连接时先从 SQL 读取 seq 大于游标的记录，Pub/Sub 只唤醒补读。每 15 秒发 `: heartbeat` 注释，不持久化、不占 seq。SSE 关闭不取消 job。

浏览器原生 EventSource 首次刷新不能自设 Last-Event-ID，因此支持 `?after_seq=N`；重连有 Last-Event-ID 时优先该头，无头才用 after_seq，默认 0。游标须非负整数且不超过 latest_seq，否则 422。客户端按 (run_id,seq) 去重并维护连续游标，不能因收到较大 seq 跳过缺口。

事件已过保留窗口时，握手返回 410 `EVENTS_EXPIRED`，details.history_url 指向 GET run；不伪装无事件。终态事件发送完关闭连接，前端收到终态主动 close 并 GET run。若连接后领域失败，用持久 `run.failed` 事件，不尝试改成 HTTP 500。

## 8. 联调最小清单

A 先交付认证、错误体与 ActorContext；B/C 各用独立 Schema 返回安全数据。三人共同固定：Course、QuestionPublic、AttemptDetail、RunDetail、Evidence、ReportEnvelope 和所有状态枚举。

首次接口 PR 同时提交 OpenAPI 导出和 mock fixture（包含正常、空、冲突、越权、等待、失败、partial）。前端生成类型只作类型来源；生产逻辑不能依赖手写 mock。契约测试检查路径、状态、必填字段和禁止字段；API 改动同 PR 更新生成类型和 mock。不得把上述占位符当有效 UUID 写入实际测试数据。
