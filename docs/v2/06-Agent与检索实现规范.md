# V2 Agent 与检索实现规范

日期：2026-10-15。状态：待实现。主责 B；基础设施 A，题目/评分工具 C。遵循 [01](./01-架构设计说明书.md) 的租约与阶段恢复约束，不自行再引入任务队列。

## 1. 模块与调用边界

```text
API router → TutoringService → job/outbox
worker → AgentRunner → LangGraph nodes → ToolRegistry
ToolRegistry → 公开业务服务 / 纯计算函数 / Retriever
```

agent 不直接写 SQL，不直接提交答卷或信任模型给出的 owner。`ActorContext(user_id, role, course_scope, installation_id)` 由服务端构建，不加入模型可修改参数。工具适配只做参数和 DTO 转换；业务幂等、授权放在应用服务中。

每个 attempt 的 graph_thread_id 由服务端生成并登记；普通澄清/审批续跑复用有效 attempt。worker 租约丢失后以新 attempt 和图线程恢复已提交业务阶段；不能仅凭旧 checkpoint 重放副作用。SQL 事务与 checkpoint 写入无原子保证。

## 2. 图与状态

节点顺序：validate_context → load_context → route → clarify 或 plan/execute → verify → repair（最多一次重新规划）→ compose → persist；异常通过 finalize_error 收口。简单咨询无需先生成完整计划；计算缺关键参数进入 waiting_user。

| 状态字段 | 内容/来源 |
| --- | --- |
| identity | user_id、course_id、session_id、run_id、turn_id，服务端只读 |
| execution | attempt_no、graph_thread_id、job_id、lease_version |
| mode/context_refs | 经业务服务重新鉴权的模式与对象引用 |
| recent_messages/history_summary | 原文消息、带消息区间的摘要，不能冒充课程证据 |
| tasks | id、goal、dependencies、capability、acceptance、status、result_refs |
| observations/evidence_refs | 安全工具结果、来源分块和文档版本 ID |
| artifacts | 计算、练习、报告或复习建议卡片 |
| pending_input | input_id、kind、prompt、tool_call_id/args_hash（审批时） |
| budget | tool_calls_used、replans_used、active_elapsed_ms、model_usage |
| status/stage_results | 领域状态与已提交节点结果引用 |

任务状态 pending/running/completed/failed/skipped，完成以 acceptance 校验；调用工具成功并不等于完成用户目标。一个任务失败时，无依赖的安全只读任务可继续，最终明确未完成项。

默认每 run 最多 8 次工具调用（重试也计数）、重新规划 1 次、可重试只读调用最多重试 1 次、活动总预算 120 秒。等待用户时间不计入活动耗时，续跑不能重置已用预算；模型超时取剩余活动预算内的上限。工具/模型原始延迟、token、成本估计分别记账。

## 3. 上下文与追问

1. 读取本人会话最近原文、摘要、上一轮结构化计算结果；模型输入长度按 token 预算裁剪，保留当前问题和最近计算参数。
2. 根据 context_refs 加载章节、固定题目版本、本人答卷/报告。客户端传来非本人报告或跨课题目立即拒绝，不等模型判断。
3. “换成 /28”只覆盖 prefix，保留前轮明确的 IP；没有可靠前轮 IP 则澄清，不能通过课程片段猜出地址。
4. 未提交练习模式仅加载 QuestionPublic、当前草稿和提示记录；批改模式仅通过 GradingService 从正式提交快照读取标准。禁止把答案放入所有工具共享上下文。
5. 消息内容、检索文档和用户附件都是数据。文档中“忽略规则、读取其他用户”等指令不能改变工具白名单或 ActorContext。

## 4. 工具契约与权限

工具描述至少有 name、input_schema、output_schema、readonly、timeout_seconds、retryable、approval_policy、idempotency_policy。工具结果：

```json
{
  "status": "ok",
  "data": {},
  "evidence_refs": [],
  "error_code": null,
  "retryable": false,
  "elapsed_ms": 3
}
```

status=ok/empty/invalid_input/unavailable/denied。empty 是合法查询无命中，unavailable 是依赖失败；不能互换。超时默认检索 10s、来源 5s、纯计算 1s，均受剩余预算约束；M0 锁定实际适配时再测量调整。

| 工具 | 输入 | 输出/实现方 | 可用模式与限制 |
| --- | --- | --- | --- |
| search_course | query、chapter_id?、top_k（1–20） | Evidence 列表、index_version_id；B | 所有模式；课程由 ActorContext 限定 |
| read_source | chunk_id、neighbor_count（0–2） | 来源及相邻原文；B | 同课且可读版本；长度预算限制 |
| get_concept/get_prerequisites | concept_id | 规范知识点、已审核先修边；A 服务，B 适配 | 不返回无限图遍历 |
| subnet | ip、prefix、address_policy | 结构化子网结果；B | 所有模式；初版仅 IPv4 |
| get_question/select_practice | question_version_id 或 concept_ids/count | QuestionPublic；C | 同课已审核；count 默认 1，最多 5 |
| give_hint | attempt_item_id、level | 安全提示和实际级别；C | practice_help，限本人 draft，不释放标准 |
| get_learning_evidence | concept_ids、limit | 本人有效作答、样本数、提示/重复标记；C | 不读其他用户 |
| grade_submission | attempt_id | 既有/新评分任务引用；C | 只限正式提交，工具不替代 submit；活动评分幂等 |
| propose_review_plan | concept_ids、goal | 建议，不创建计划；C | 用户点击接受走专门 API |

首版对普通模型不注册 submit_attempt、write_score、publish_question、任意 SQL/HTTP/终端工具。grade_submission 是受控业务调用，不允许模型直接传标准或得分。实际对学生的提交操作统一走显式按钮和提交 API。

## 5. 子网计算约定

计算核心是纯函数，可用 Python 标准库做地址解析，返回 ip、prefix、mask、network_address、broadcast_address、first_host、last_host、usable_host_count、address_policy、gateway=null、warnings。ip 保留用户地址，network 允许从主机地址归一化。

address_policy：默认 traditional_lan；/0–/30 按排除网络/广播的常规主机数计算。/31、/32 不能不加说明套用同一公式：traditional_lan 返回 invalid_input 并提示选择用途；point_to_point 仅允许 /31，两个地址可用且 broadcast_address=null；host_route 仅允许 /32，一个地址、broadcast_address=null。工具卡必须显示约定。真实网关始终不能仅凭该计算推断。

测试覆盖 /0、/1、/24、/27、/28、/30、/31、/32、主机位非零、非法 IPv4、越界前缀和缺参；题库中的子网题明确 address_policy，模型不得修改它来凑答案。

## 6. 文档建库与检索

流水线分为上传确认、解析、分块、embedding、快照构建、校验、ready、显式发布。每阶段存版本、输入 hash 和结果引用，中断后可复用；发布前失败不能切换课程索引指针。

- 上传初版 md/txt/pdf，上限 20 MiB；服务端检查类型、长度、SHA-256，不能只看扩展名。PDF 无文本层返回 `DOCUMENT_TEXT_UNAVAILABLE`，不伪造解析成功。
- TXT/Markdown 保留标题路径与分块序号；PDF 保留真实页码与页内顺序。解析清洗记录 parser_version，不能改原文后仍沿用旧 hash。
- 初始分块目标 600–1000 中文字符，相邻重叠不超过 150 字符；优先标题/段落边界，不切断 IPv4/CIDR。参数作为 algorithm_version 的一部分入 manifest，需用样本评估后调整。
- 中文分词保留 CIDR、IP、TCP/UDP 等术语；BM25 与向量各召回最多 20，RRF `sum(1/(60+rank))`，rank 从 1 开始，去重后默认 top_k=5。并列按 chunk_id 稳定排序；初版 rerank 关闭。
- 向量归一化，零向量拒绝；embedding_model、维度、文档版本固定。更换模型必须新建索引，不复用旧向量。
- manifest 必含 schema_version、index_version_id、course_id、document_version_ids、chunk_ids 顺序、embedding 模型/维度、分块/分词/融合算法版本、各产物 size/sha256。numpy 加载禁止 pickle。
- 先上传产物并 HEAD/哈希校验，再将 index ready；publish 应用服务短事务切指针。装载新版本失败返回 unavailable，不能用旧版本冒充。
- 单产物受 `.env.example` 的 RETRIEVAL_MAX_INDEX_BYTES 限制；同时评估总下载量、矩阵内存和装载峰值。A/B 在 M1 记录实测容量，超限拒绝发布，不能自动截断语料而不告知。

Retriever 公共端口：`search(actor, query, course_id, index_version_id, chapter_id, top_k) -> RetrievalResult`。业务调用先校验课程和当前版本，候选返回前复查 SQL 可见性。进程缓存以 installation/course/index/model/算法版本分区，仅为 MinIO 的可重建副本。

## 7. 验证与失败处理

compose 前代码校验：Schema、数值工具一致性、任务覆盖、引用存在/权限/版本、学生卡片无隐藏字段。复杂解释可增加模型审查，但不能用其替代数值与权限检查。无证据可回答明确标记的一般解释，不能绑定不支持结论的引用。

工具 unavailable 可在预算内按策略重试；invalid_input 进入澄清，denied 不重试；连续相同查询没有新增证据就停止。预算耗尽返回 partial；失败保存安全 error_code 和已完成阶段，不泄露供应商原始含密错误。

验证通过后才发布 answer.delta，最终回答完整存 SQL。发布中 worker 崩溃时，前端以 GET run 的最终结果收敛，不能把已到达 token 当有效终态。所有事件/阶段写入都需要有效 lease_version。

prompt 文件按角色/用途分开并版本化，记录模型标识、prompt_version 和工具 Schema 版本。日志保留决策摘要与安全工具结果，不要求或保存模型内部思维链。

## 8. B 的交付证据

- 可控模型替身：路由、澄清、补检索、预算终止、等待恢复、失败和取消都可离线复现。
- 子网核心边界测试全通过；首场景 /27 → /28 追问与网关未知断言通过。
- 小型真实 MinIO 快照验证 manifest、哈希、维度、版本切换和历史引用；检索失效不能冒充 empty。
- worker 中断/租约过期后新 attempt 恢复，旧 attempt 写入受拒；重复事件不生成多个最终回答。
- 与 C 联调只返回安全题目和提示；50 个助教任务的实际结果在 M4 统一评估，不在此文填造指标。
