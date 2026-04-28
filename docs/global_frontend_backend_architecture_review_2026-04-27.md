# 全局前后端代码与功能架构审查报告

审查日期：2026-04-27  
审查对象：`app/` 后端服务、`front/client` 用户端、`front/admin` 管理端、`front/shared` 前端共享层，以及 Agent/RAG、学习、题库、文档解析与向量化入库链路。  
排除范围：部署、安全合规、生产运维、基础设施高可用与密钥治理不在本次审查范围内。  
报告原则：以下发现均视为需要处理的问题；报告只做问题定位、风险分析、遗漏识别与更简单稳定的产品/架构方向，不直接修改业务代码，不设置延期或排序类结论。

---

## 0. 代码库能力基线与总体判断

### 0.1 当前可见能力

- 用户端只有登录/注册、聊天页与学习中心：`front/client/src/App.tsx:27-39`。`/` 与 `/:id` 都进入 `ChatPage`，`/learning` 进入 `LearningCenterPage`。
- 管理端覆盖 Dashboard、知识库、题库、知识图谱、运维中心、Trace Lab、RAG Eval、审计日志、用户管理和用户会话：`front/admin/src/App.tsx:45-63`。
- 后端注册了 auth、conversation、chat run、learning、feedback、admin ingestion/questions/analytics/users/trace/operations/rag-eval/audit/feedback：`app/main.py:154-168`。
- 聊天采用 Chat Run 模型，支持 create/get/events/stream/interrupt/retry/resume/regenerate：`app/api/chat_runs.py:88-333`。
- 文档入库主链路是 Docling 解析、本地规范化、HybridChunker、自定义表格切片、预览 artifact、向量化和入库：`app/services/document_processing.py:157-263`、`app/tasks/ingestion_tasks.py:52-182`。
- 检索主链路包括 dense search、keyword search、question vector search、证据扩展、rerank、日志和 cache：`app/services/retrieval/retrieval_service.py:128-257`。
- Agent 运行层基于 LangGraph/LangChain `create_agent`，但 `NativeAgentRunner` 承担了 SSE 适配、Trace、HITL、记忆、工具结果清洗与 intent 分类：`app/agents/native_agent_runner.py:85-562`、`app/agents/native_agent_runner.py:590-1460`。

### 0.2 总体判断

当前系统已经有“知识库上传 → 文档解析切片 → 向量检索 → Agent 聊天 → Trace/反馈 → 管理端诊断 → 用户学习练习”的雏形，但产品闭环和技术边界没有完全对齐：

1. **用户端更像 RAG/Agent 技术演示，不是完整学习产品。** 聊天页强调 SSE、Trace、Markdown；学习中心提供练习、错题、掌握度、复习卡片列表，但缺少材料阅读、知识点导航、学习目标、错因诊断、AI 教练、记忆控制、证据跳转。
2. **管理端覆盖面广但工作流割裂。** 知识库、题库、Trace Lab、RAG Eval、反馈、质量雷达分散存在，没有形成“反馈/评测失败 → Trace → 证据 → 文档/切片/题目 → 修复 → 重测”的治理闭环。
3. **前端复杂度集中在页面层。** `ChatPage.tsx`、`KnowledgeManagementPage.tsx`、`QuestionManagementPage.tsx` 分别承担状态机、API 编排、轮询、错误恢复、业务规则和渲染，页面已成为业务控制器。
4. **后端虽然有 router/service/repository 分层，但核心域仍是大文件大服务。** 题库、文档处理、Agent Runner、检索编排等模块职责过多，变更影响面大。
5. **Agentic RAG 能力存在，但缺少业务策略显式化。** 工具调用、记忆、Trace、HITL 都已实现，但用户无法控制检索范围/证据来源/题库答案暴露/引用严格度，管理员也无法把反馈闭环到评测和内容修复。
6. **Docling 链路过重且有重复抽象。** 上游 DoclingDocument、本地 `DoclingDocument`、cache path、HybridChunker、自定义表格切片、preview artifact、truth signature 和 chunk metadata 之间重叠，带来缓存路径不统一、表格语义损失、质量门禁无效、旧 API 残留等问题。

---

## 1. 用户端功能与真实学习流程问题

### 1.1 缺少材料浏览、原文阅读与证据跳转

**依据**：用户端路由只有聊天和学习中心：`front/client/src/App.tsx:27-39`。聊天空态文案强调“知识库问答、多轮对话、SSE、检索过程追踪、Markdown”：`front/client/src/pages/chat/components/ChatEmptyState.tsx:16-17`。证据卡片只从执行轨迹里抽取 `source/label/detail`，没有文档、页码、切片预览、表格定位或原文跳转：`front/client/src/pages/chat/components/AssistantEvidencePanel.tsx:5-45`。

**问题**：真实学习流程需要先浏览课程资料、查看章节、定位原文、围绕段落提问、收藏或做笔记。当前知识库在用户端几乎只表现为聊天背后的检索源，用户无法直接阅读材料，也无法从答案进入证据原文。

**风险**：用户无法复核答案来源；后端保存的 provenance、页码、表格、chunk metadata 无法转化为可信学习体验；RAG 证据成为不可操作的摘要。

**遗漏能力**：资料库/课程材料页、文档目录、章节与页码预览、证据卡片跳转、表格原文视图、段落收藏/划线/笔记、从原文段落发起追问。

### 1.2 聊天输入缺少学习任务和检索控制

**依据**：`ChatComposer` 只是 textarea、发送、重试/继续、停止：`front/client/src/pages/chat/components/ChatComposer.tsx:32-72`。聊天页只显示“AI 知识检索已启用”：`front/client/src/pages/ChatPage.tsx:900-906`。

**问题**：用户无法选择资料范围、题库是否参与、是否隐藏答案、回答难度、引用规则、是否只用上传资料、是否生成题目、是否进入错题辅导。所有控制都被压缩成自然语言提示，让 Agent/检索层猜测。

**风险**：同类任务可能因 phrasing 不同而触发不同工具；学生练习时可能被题库 evidence 泄露答案；管理员诊断和学生学习共用同一聊天入口策略，边界不清。

**遗漏能力**：聊天模式（资料问答/概念讲解/错题辅导/生成练习/批改答案/文档总结）、检索范围（全部知识库/指定文档/指定知识点/排除题库答案）、引用策略（必须引用/只用资料/允许常识补充/证据不足提示）、学习参数（难度、目标、考试日期、讲解风格）。

### 1.3 用户端建议问题混入管理员/运营视角

**依据**：`ChatPage` 静态建议问题包含“列出最近一周检索命中率变化原因”：`front/client/src/pages/ChatPage.tsx:26-31`。

**问题**：检索命中率变化属于管理端分析/运营诊断，不符合普通学生或用户端学习入口。静态 prompt 也没有基于当前知识库、学习进度、错题、最近对话生成。

**风险**：产品角色边界混乱；用户端暴露内部运营心智；推荐入口不能真正引导学习行为。

**遗漏能力**：基于用户状态的动态建议，例如“继续昨天未完成练习”“复习到期卡片”“解释最近错题知识点”“阅读最近上传资料并生成摘要”。

### 1.4 学习中心是练习原型，不是学习闭环

**依据**：学习中心一次性拉取练习会话、错题、掌握度、复习卡片、学习路径：`front/client/src/pages/LearningCenterPage.tsx:49-68`。开始练习只传 `limit`：`front/client/src/pages/LearningCenterPage.tsx:96-110`。后端 `PracticeSessionCreate` 只有 title、question_ids、knowledge_point_id、limit：`app/schemas/learning.py:11-15`。未指定题目/知识点时只取最新 clean 题：`app/repositories/learning_repo.py:29-44`。错题、复习卡片、学习路径只是被动列表：`front/client/src/pages/LearningCenterPage.tsx:211-309`。

**问题**：真实学习闭环应包含诊断、材料学习、练习、即时反馈、错因分析、相似题巩固、间隔复习、掌握度更新、路径调整。当前只是“最新题目练习 + 列表展示”。

**风险**：用户无法按薄弱知识点练习；错题本和复习卡片没有转化为可执行任务；学习路径只从错题生成，缺少课程目标、知识图谱、先修关系和时间计划。

**遗漏能力**：诊断测验、弱点驱动组卷、错因分类、相似题推荐、到期复习队列、每日目标、考试倒计时、AI 教练讲解与复盘。

### 1.5 掌握度模型不是知识掌握度

**依据**：`MasteryRecordResponse` 支持 question_id/knowledge_point_id：`app/schemas/learning.py:73-86`，但 `upsert_mastery` 实际按 question 维度更新并设置 `knowledge_point_id=None`：`app/repositories/learning_repo.py:111-138`。前端显示“记录 question_id/knowledge_point_id/id”：`front/client/src/pages/LearningCenterPage.tsx:311-325`。

**问题**：掌握度应表达用户对知识点、章节、能力项的掌握，而不是某个题目的正确率记录。当前 UI 甚至显示原始 ID，用户无法理解自己哪里薄弱。

**风险**：学习路径无法基于知识点掌握度推荐；管理端无法评估题库和资料对知识点的覆盖；AI 辅导无法利用稳定画像。

**遗漏能力**：题目到知识点的掌握度聚合、知识点名称/章节展示、趋势变化、依据说明（答题次数、最近错误、复习情况、相关对话）。

### 1.6 判题与题型能力不足

**依据**：答题判定是 `normalized_answer.casefold() == correct_answer.casefold()`：`app/services/learning_service.py:76-126`。题库规则限制单选/多选为 A/B/C/D、2-4 个连续选项：`app/services/question_rules.py:75-146`。管理端页面也提示仅支持 A/B/C/D、判断题 true/false：`front/admin/src/pages/QuestionManagementPage.tsx:332-365`。

**问题**：真实题库包含多选顺序差异、空格/标点差异、填空、简答、材料题、图片/公式题、组合题、部分得分。当前判题只适合最简单字符串答案。

**风险**：多选 `A,B` 与 `B,A`、`AB`、`A、B` 可能误判；开放题无法进入学习闭环；真实教学题库导入受限。

**遗漏能力**：按题型的答案标准化、集合比较、rubric 评分、关键词/语义评分、题型扩展、难度/标签/知识点权重。

### 1.7 聊天记忆与学习画像断开

**依据**：记忆服务按 conversation 读取短期消息与长期摘要：`app/services/conversation_memory_service.py:36-79`。Agent 启动注入当前 conversation 记忆：`app/agents/native_agent_runner.py:98-119`。学习中心独立更新错题、复习和掌握度：`app/services/learning_service.py:76-126`。

**问题**：学习产品需要用户级画像：目标、薄弱知识点、最近错题、偏好讲解、复习计划。当前记忆是单会话摘要，学习数据也没有进入 Agent 工具策略。

**风险**：用户换会话后个性化断裂；AI 不知道用户最近错在哪里；学习中心和聊天互相不能增强。

**遗漏能力**：用户可见/可编辑记忆、跨会话学习画像、错题/掌握度注入聊天、聊天回答转笔记/闪卡/练习/复习任务。

---

## 2. 管理员端功能与内容治理问题

### 2.1 管理端页面多，但治理闭环割裂

**依据**：管理端路由覆盖知识库、题库、图谱、Operations、Trace Lab、RAG Eval、审计和用户：`front/admin/src/App.tsx:45-63`。Operations 一次加载任务、质量雷达、反馈摘要和反馈列表：`front/admin/src/pages/OperationsCenterPage.tsx:24-43`。质量雷达只统计文档数、切片数、题目数、向量化和失败任务：`app/services/admin_operations_service.py:90-146`。

**问题**：管理员需要的是“负反馈/评测失败 → Trace → 检索证据 → 源文档/切片/题目 → 修复 → 重新入库/向量化 → 复测”的闭环。当前能力被拆散在多个页面，没有跨页面的问题定位路径。

**风险**：管理员能看到问题信号，但难以判断根因；反馈、Trace、RAG Eval、文档解析质量之间没有直接关联；内容治理成本高。

**遗漏能力**：从反馈跳转 Trace、从 Trace 跳转证据原文、从证据定位文档/切片/题目、从失败样本创建 Golden Query、修复后对比复测。

### 2.2 知识库管理页是页面级入库控制器

**依据**：`KnowledgeManagementPage.tsx` 约 798 行。页面内实现上传阶段模拟进度和轮询：`front/admin/src/pages/KnowledgeManagementPage.tsx:172-217`。页面内实现 presign、MinIO PUT、callback、poll ingestion job：`front/admin/src/pages/KnowledgeManagementPage.tsx:219-286`。页面内实现删除、批量删除、详情预览和切片过滤：`front/admin/src/pages/KnowledgeManagementPage.tsx:380-475`。

**问题**：文件校验、上传、进度模拟、任务轮询、批量任务、删除、详情预览、切片搜索和渲染都在页面内。页面承担了知识库入库流程控制器职责。

**风险**：上传/轮询逻辑不能与 Operations 任务中心复用；页面卸载、批量上传、任务超时、进度停滞容易产生竞态；新增解析质量、预览、重切策略时需要继续扩张大页面。

**更简单稳定的方向**：抽出 `useIngestionJobController` 或 ingestion domain service；列表、上传任务、文档详情、切片预览拆为独立组件；Operations 与 Knowledge 页面共享同一 job polling/refresh 模型。

### 2.3 题库管理页混合题目编辑、导入、映射和向量化

**依据**：`QuestionManagementPage.tsx` 约 750 行。创建题目直接带 `knowledge_point_ids`，编辑题目先 `updateQuestion` 再 `linkKnowledgePoints`：`front/admin/src/pages/QuestionManagementPage.tsx:171-258`。创建、编辑、映射三套知识点本地过滤重复：`front/admin/src/pages/QuestionManagementPage.tsx:260-276`。知识点候选只取第一页 200 条：`front/admin/src/hooks/useKnowledgeCandidates.ts:16-24`。向量化 polling 循环最多 120 次：`front/admin/src/hooks/useVectorizationJobPolling.ts:12-41`。

**问题**：题库页虽然拆出 hook，但核心编排仍在页面。编辑内容和关联知识点是两个请求，无法保证事务一致。知识点选择本地过滤且限制 200 条，不适合大型知识库。

**风险**：题目内容更新成功但知识点关联失败，形成部分更新；知识点数量大时无法准确映射；题库向量化任务体验与知识库入库任务割裂。

**更简单稳定的方向**：后端提供“题目内容 + 知识点关联”同事务更新接口；知识点选择改为远端搜索/分页；题库导入/向量化/重试复用统一 job controller；页面拆成题库列表、题目表格、编辑器、知识点映射器和任务面板。

### 2.4 RAG Eval Lab 不适合构建真实评测集

**依据**：Golden Query 创建时 `expected_source_ids` 是逗号分隔字符串：`front/admin/src/pages/RagEvalLabPage.tsx:49-77`。运行评测只支持选择 Golden Query 或临时问题：`front/admin/src/pages/RagEvalLabPage.tsx:79-112`。

**问题**：RAG 评测需要选择期望文档、切片、页码、表格、答案要点、禁止来源、评分规则、标签，并能从失败回答/用户反馈生成样本。当前让管理员手输 source id，缺少证据选择器和样本沉淀。

**风险**：Golden Query 构建成本高且容易填错；无法验证“是否引用正确页/表格/切片”；评测集与真实失败案例脱节。

**遗漏能力**：文档/章节/切片 evidence picker、答案 rubric、从 Trace/反馈一键创建评测样本、解析/切分/检索/Agent 配置变更对比。

### 2.5 Trace Lab 是被动日志，不是调试工作台

**依据**：Trace Lab 列表按问题关键字查询最近 20 条：`front/admin/src/pages/TraceLabPage.tsx:15-37`。详情只渲染 title、step、kind、status、event_type 和 `detail_sanitized`：`front/admin/src/pages/TraceLabPage.tsx:91-127`。

**问题**：Trace Lab 缺少 run diff、失败聚类、工具输入输出结构化查看、证据原文跳转、重放/复现、转 RAG Eval 样本等诊断动作。

**风险**：管理员看到“发生了什么”，但很难判断“为什么错”；Agent/RAG 调试仍要回到日志或数据库；反馈和评测不能沉淀。

**遗漏能力**：Trace → evidence → 文档预览/切片 metadata 跳转；同 query 多 run 对比；错误归因标签（无证据、证据错、rerank 错、生成幻觉、题库泄漏、HITL 未触发）。

### 2.6 Operations 质量雷达偏计数，任务分页语义不可靠

**依据**：`quality_radar` 只统计知识点、切片、题目、dirty 题、失败任务：`app/services/admin_operations_service.py:90-146`。`list_tasks` 在 task_type 为 None 时分别取 ingestion page 1 和 vectorization page 1，再合并排序切片：`app/services/admin_operations_service.py:21-88`。

**问题**：质量雷达没有覆盖解析字符数、短 chunk、重复 chunk、表格保真、页码覆盖、空召回、RAG Eval 失败率等关键质量。全局任务分页不是数据库层统一排序，任务很多时会漏掉跨类型的全局结果。

**风险**：页面显示“没有质量告警”并不代表文档和检索质量正常；失败任务可能被分页合并逻辑隐藏。

**遗漏能力**：文档级质量报告、chunk 质量 drilldown、表格质量指标、检索质量指标、统一 job 表或 union/sort/page 查询。

### 2.7 用户反馈没有闭环到内容修复

**依据**：用户端反馈按钮只有“有帮助、帮助不足、证据不足、疑似幻觉”：`front/client/src/pages/chat/components/AssistantMessageFeedback.tsx:49-91`。Operations 只展示反馈计数和列表：`front/admin/src/pages/OperationsCenterPage.tsx:200-256`。后端 schema 支持 comment，但用户端没有评论输入：`app/schemas/feedback.py:15-38`。

**问题**：反馈只是标签，没有让用户说明原因，也没有自动关联 Trace、RAG Eval、文档切片、题目记录或内容修复任务。

**风险**：“证据不足”和“疑似幻觉”无法区分检索错、证据丢、生成错或用户期望不同；管理员只能看摘要，不能把反馈变成可验证样本。

**遗漏能力**：负反馈详情、原因选择/评论、打开对应 Trace、转 Golden Query、转内容修复任务、修复后复测与关闭。

---

## 3. 前端目录结构、模块边界与状态复杂度问题

### 3.1 shared API 泛型工厂复杂，同时 app wrapper 重复

**依据**：`front/shared/api/module-factories.ts` 约 402 行，覆盖 auth、conversation、chat run、admin ingestion/questions/users/analytics/operations/rag-eval/learning/feedback。`createAdminQuestionsApi` 有 15 个泛型参数：`front/shared/api/module-factories.ts:179-240`。client/admin/shared 三处都有几乎相同的 `admin-questions.ts`：`front/client/src/api/admin-questions.ts:1-61`、`front/admin/src/api/admin-questions.ts:1-61`、`front/shared/api/admin-questions.ts:1-61`。用户端还存在 `admin-ingestion.ts` 和 `admin-questions.ts`：`front/client/src/api/admin-ingestion.ts:1-49`、`front/client/src/api/admin-questions.ts:1-61`。

**问题**：共享层通过泛型工厂抽象请求，但实际又在不同 app 中复制 wrapper。抽象变厚、类型参数难读、模块边界变弱，用户端源码也包含管理员 API surface。

**风险**：DTO 改动需要多处同步；用户端与管理端边界不清；泛型工厂隐藏真实契约，阅读成本高于具体 typed API。

**更简单稳定的方向**：按后端 domain 维护具体 typed API；admin-only API 只进入 admin app；shared 层保留 ApiClient、错误处理、跨 app DTO，而不是海量泛型工厂。

### 3.2 `ChatPage.tsx` 混合聊天状态机、SSE、快照、HITL 与 UI

**依据**：`ChatPage.tsx` 约 1017 行。路由切换、SSE disconnect、快照恢复、playback 恢复在页面：`front/client/src/pages/ChatPage.tsx:554-604`。autosave snapshot 在页面：`front/client/src/pages/ChatPage.tsx:618-654`。发送消息时创建会话、pending message、snapshot、run、stream：`front/client/src/pages/ChatPage.tsx:656-706`。retry/resume/regenerate 在页面：`front/client/src/pages/ChatPage.tsx:721-856`。HITL 决策提交和 UI 在页面：`front/client/src/pages/ChatPage.tsx:831-871`、`front/client/src/pages/ChatPage.tsx:913-971`。

**问题**：页面同时承担运行控制器、事件回放器、快照持久化层、SSE 生命周期、会话创建、消息补偿、HITL 和渲染。`streaming-session.ts` 只抽出 reducer，完整 lifecycle controller 仍留在页面。

**风险**：route change、SSE reconnect、backend run status、localStorage snapshot、Zustand messages 之间存在竞态；新增学习模式/来源选择/题库防泄漏会继续扩大页面复杂度；错误恢复难以单测。

**更简单稳定的方向**：建立 `useChatRunController(conversationId)`，把 run 生命周期、SSE、snapshot、playback、HITL、retry/regenerate 收敛成明确状态机；页面只渲染状态和动作。

### 3.3 SSE 韧性逻辑分散在多层

**依据**：`SSEClient` 维护 lastEventId、terminalEventReceived、processedEventIds、reconnect guard：`front/shared/api/sse-client.ts:41-142`。ChatPage 也维护 snapshot lastEventId、playback、stream reconnect/error recovery：`front/client/src/pages/ChatPage.tsx:413-654`。后端还有 event persistence/playback 和 after_event_id：`app/services/run_event_playback_service.py:23-109`、`app/services/chat_run_stream_service.py:64-184`。

**问题**：事件已处理、terminal event、snapshot 清理、full/delta playback、live stream 接续等不变量分散在三层，没有单一协议文档或状态机实现。

**风险**：重复事件、丢 terminal event、快照过期、回放和 live stream 顺序冲突会导致 UI 错乱；修复一个恢复路径可能破坏另一个路径。

**更简单稳定的方向**：定义 Chat Run Event Log 协议：event id 单调、terminal event、last seen、snapshot schema version；前端只保留一个事件状态机。

### 3.4 聊天 store 不是单一事实源，pending 消息用内容匹配

**依据**：client ChatState 只有 `currentRunId/isRunning`：`front/client/src/store/index.ts:31-37`、`front/client/src/store/index.ts:187-197`。复杂 streaming state 在 ChatPage local state/ref/localStorage/SSEClient 中。`fetchMessages` 为保留 pending-user 消息用 role + content 文本匹配：`front/client/src/store/index.ts:134-167`。

**问题**：聊天事实源分裂在 Zustand、页面 state/ref、localStorage、SSEClient 和后端 run state 中。pending 消息按内容匹配，无法区分相同文本的不同用户轮次。

**风险**：连续发送相同问题可能合并/丢失 pending；调试状态需要检查多处；恢复逻辑容易产生幽灵消息。

**更简单稳定的方向**：每次发送生成 client nonce，并由 backend 回传；store/controller 持有权威 ChatRunSession，localStorage 只作为恢复缓存。

### 3.5 管理端 store 多领域聚合

**依据**：`front/admin/src/store/index.ts` 约 458 行，同一文件包含 auth、knowledge、question、user management、global state，并直接导入 ingestion/questions/users API：`front/admin/src/store/index.ts:1-120`。

**问题**：多个管理域共用一个 store index 文件，状态、副作用和 API 调用混在一起，不利于领域测试和页面演进。

**风险**：题库、知识库、用户管理状态容易互相影响；新增 Operations/RAG Eval/Trace 领域时 store 继续膨胀。

**更简单稳定的方向**：按 domain 拆 store slice，或使用 React Query 管理服务端状态，Zustand 只保留认证和跨页面 UI 状态。

---

## 4. 后端服务边界、代码质量、性能与复杂度问题

### 4.1 Router/Service/Repository 分层存在，但核心域职责仍过宽

**依据**：`app/api/questions.py` 约 463 行，既手工构造 response，也处理 JSON/multipart/XLSX 导入分支：`app/api/questions.py:51-66`、`app/api/questions.py:279-360`。`QuestionService` 约 628 行，包含题库 CRUD、导入解析、Excel 解析、规则校验、向量化派发、知识点关联：`app/services/question_service.py:219-628`。`QuestionRepository` 混合题库 CRUD、问题 CRUD、导入 upsert、dirty 状态、向量搜索和 vectorization job：`app/repositories/question_repo.py:1-330`。

**问题**：目录结构表面清晰，但题库域内部仍是大 router、大 service、大 repository。导入格式、规则校验、业务状态、搜索和任务管理没有清晰拆分。

**风险**：修改导入、判题、向量化或知识点关联时会触碰题库主 CRUD；单测难以隔离；字段变更容易在 router/service/repo 中重复处理。

**更简单稳定的方向**：题库域拆成 question CRUD、import parser/service、question rules、vectorization service、knowledge mapping service；router 只做依赖注入和 schema 绑定；repository 按 aggregate 拆分。

### 4.2 题库向量化重试接口创建 job 但未派发 Celery

**依据**：正常触发向量化会创建 job 后调用 `batch_vectorize.apply_async(...)`：`app/services/question_service.py:511-561`。重试接口只创建 pending job、记录 audit、返回，没有派发任务：`app/api/questions.py:407-439`。Operations 页面重试 vectorization job 后提示“已重新提交任务”：`front/admin/src/pages/OperationsCenterPage.tsx:49-63`。

**问题**：失败重试路径看起来不完整。新 job 可能创建为 pending，但没有实际 Celery task 消费。

**风险**：管理员看到重试成功，任务却可能长期 pending；dirty 题持续存在；题库检索和学习练习受影响。

**更简单稳定的方向**：重试复用正常 vectorization dispatch service；明确重试原 job 范围还是重新计算 dirty candidates；router 不直接创建 job。

### 4.3 题目 dirty/hash 与实际 embedding input 不一致

**依据**：`compute_content_hash` 包含 question_text、options、answer：`app/repositories/question_repo.py:19-29`。`compute_embedding_text_hash` 只包含 question_text：`app/repositories/question_repo.py:32-35`。更新题目时只有 question_text 变化才清空 embedding/dirty：`app/repositories/question_repo.py:162-188`、`app/repositories/question_repo.py:249-278`。向量化只使用 `question.question_text`：`app/tasks/vectorization_tasks.py:41-79`。检索 evidence 却输出 options、answer、explanation：`app/services/retrieval/retrieval_service.py:345-375`。

**问题**：题库向量语义只代表题干，但 evidence 内容包含选项、答案、解析；答案或解析变化可能不触发向量更新。content hash 与 embedding hash 语义不一致。

**风险**：按答案/解析相关语义检索不到；题目内容变了但向量状态仍显示 clean；rerank/生成看到的 evidence 与向量表示不一致。

**更简单稳定的方向**：明确 embedding input 是题干、题干+选项、还是题干+选项+解析；dirty 判定基于实际 embedding input hash；答案/解析进入检索应受业务模式控制。

### 4.4 题库 evidence 混入知识库 evidence，默认暴露答案解析

**依据**：`RetrievalService.retrieve` 每次都会执行 question vector search 并把结果 extend 到 evidence candidates：`app/services/retrieval/retrieval_service.py:149-187`。`_question_results_to_evidence` 输出“题目、选项、答案、解析”：`app/services/retrieval/retrieval_service.py:345-375`。question evidence 用 synthetic `knowledge_point_id = question::{id}`，日志 `_unique_kp_ids` 会跳过非 UUID 的 question evidence：`app/services/retrieval/retrieval_service.py:407-479`。

**问题**：知识库材料证据和题库答案证据在同一 evidence list 中混合，但 observability 又跳过 question evidence。普通聊天默认可能拿到题库答案/解析。

**风险**：学生练习时答案泄漏；管理端检索日志低估题库 evidence 参与度；Agent 无法区分“生成练习”与“解释题库答案”。

**更简单稳定的方向**：检索请求带 evidence source policy（knowledge_only、question_stem_only、question_with_answer、admin_debug）；题库检索拆成独立 tool 或独立 evidence 字段；日志显式记录 source_type/question_id/kp_id。

### 4.5 学习服务与题库服务缺少事务级业务接口

**依据**：创建题目可带 `knowledge_point_ids`：`front/admin/src/pages/QuestionManagementPage.tsx:171-195`。编辑题目后再单独调用 `linkKnowledgePoints`：`front/admin/src/pages/QuestionManagementPage.tsx:235-258`。后端有独立 link endpoint：`app/api/questions.py:443-450`。

**问题**：题目内容与知识点关联是同一个编辑动作，但当前编辑路径拆成两个请求，业务原子性由前端串行调用模拟。

**风险**：内容更新成功、关联失败会产生部分更新；学习掌握度、知识图谱、检索过滤依赖不完整关联。

**更简单稳定的方向**：`PATCH /questions/{id}` 支持内容 + knowledge_point_ids 同事务更新，返回完整 QuestionResponse。

### 4.6 大文件集中承载核心复杂性

**依据**：`app/agents/native_agent_runner.py` 约 1520 行；`app/services/document_processing.py` 约 1332 行；`front/client/src/pages/ChatPage.tsx` 约 1017 行；`front/admin/src/pages/KnowledgeManagementPage.tsx` 约 798 行；`front/admin/src/pages/QuestionManagementPage.tsx` 约 750 行；`app/services/question_service.py` 约 628 行；`app/services/retrieval/retrieval_service.py` 约 511 行；`front/admin/src/store/index.ts` 约 458 行；`front/shared/api/sse-client.ts` 约 398 行。

**问题**：复杂度集中在高频变更域，而这些大文件不是单纯行数问题，是职责混合：页面做控制器、Runner 做策略/协议/持久化、document_processing 做解析/缓存/清洗/切分/预览/质量。

**风险**：局部功能修改影响整个领域；测试必须覆盖大量间接路径；新成员难以建立稳定 mental model。

**更简单稳定的方向**：按“状态机/领域服务/协议适配器/渲染组件/纯转换函数”拆分；优先提取无副作用纯函数和稳定协议边界。

### 4.7 检索链路串行，已有并行 helper 未进入主路径

**依据**：`retrieve` 先 `_has_vector_data`，再生成 embedding，再 dense search，再 lexical search，再 question search：`app/services/retrieval/retrieval_service.py:128-187`。`_has_vector_data` 每次 count vectorized chunks/questions：`app/services/retrieval/retrieval_service.py:104-110`。`VectorSearchService.parallel_search` 已实现 dense/question 并行，但主路径不用：`app/services/retrieval/vector_search_service.py:82-118`。

**问题**：检索主路径仍串行等待多个 IO/DB 操作，并且每次查询前做 count。已有并行 helper 与主流程脱节。

**风险**：Agent 工具调用延迟变长；高并发聊天时 count 和串行 search 增加 DB 压力；unused helper 造成“已经优化”的错觉。

**更简单稳定的方向**：embedding 后并发 dense/keyword/question search；用 corpus health/version cache 代替每次 count；检索计数写入异步化。

### 4.8 检索缓存缺少语料版本

**依据**：cache key 只包含 query、context、config hash：`app/services/retrieval/retrieval_service.py:43-60`。入库任务会删除旧 chunks 并创建新 chunks：`app/tasks/ingestion_tasks.py:156-182`，但 cache key 没有 document/vectorization/corpus revision。

**问题**：文档重建索引、题库重向量化后，同 query/config/context 仍可能命中旧 retrieval cache，直到 TTL 过期。

**风险**：用户看到已删除/已修改文档的旧证据；管理员重建索引后评测结果被 cache 污染；RAG Eval 无法准确验证解析/切分策略变更。

**更简单稳定的方向**：cache key 加 corpus version 或 vectorization revision；入库/重向量化成功后 bump namespace/version。

### 4.9 表格证据扩展不围绕命中行

**依据**：`_expand_anchor_candidates` 找到同 group 的 related chunks：`app/services/retrieval/retrieval_service.py:295-342`。`_build_evidence_content` 对 table 直接取 `ordered_chunks[: table_neighbor_rows * 2 + 1]`：`app/services/retrieval/retrieval_service.py:377-405`。

**问题**：表格检索命中某一行/某一 chunk 时，证据扩展取的是表格开头若干 chunk，不是 anchor 前后邻居。

**风险**：长表格中最终证据可能不包含真正命中行，表格问答准确性下降。

**更简单稳定的方向**：在 anchor metadata 保留命中 chunk index/row range；table evidence 以 anchor 为中心取邻居，并附带表头、caption、页码。

### 4.10 检索读路径内联写 retrieval_count

**依据**：`KnowledgePointRepository.vector_search` 查询后调用 `_increment_retrieval_counts`：`app/repositories/knowledge_point_repo.py:147-215`。`_increment_retrieval_counts` 更新 chunks 和 knowledge_points 并 flush：`app/repositories/knowledge_point_repo.py:268-299`。

**问题**：检索读路径包含统计写操作。

**风险**：高并发问答下计数写入成为热点；读查询事务与统计写入耦合；失败/回滚复杂度增加。

**更简单稳定的方向**：计数通过 retrieval log 聚合、异步事件或批处理更新，不阻塞检索读路径。

### 4.11 前后端契约重复且响应手工组装

**依据**：前端 shared/admin/client 多处 API wrapper 重复；后端 question response 手工构造：`app/api/questions.py:51-66`；shared factory 又以泛型隐藏实际 DTO：`front/shared/api/module-factories.ts:179-240`。

**问题**：契约不是由单一来源生成或维护，而是在 schema、router response builder、前端 wrapper、shared factory 之间同步。

**风险**：字段新增/重命名容易漂移；泛型层使契约阅读成本上升。

**更简单稳定的方向**：使用 OpenAPI 生成前端 DTO/API，或维护单一 shared DTO 包；后端尽量由 Pydantic schema 负责序列化，减少 router 字段复制。

---

## 5. Agent 功能架构与产品体验问题

### 5.1 `NativeAgentRunner` 是过重的 Agent 中枢

**依据**：`NativeAgentRunner.run` 包含 query intent 分类、短路、memory bootstrap、LangGraph stream 适配、reasoning delta、generation delta、Trace、HITL、tool call/result、final answer、错误处理：`app/agents/native_agent_runner.py:98-562`。同一文件还包含 direct answer trace、clarification trace、tool trace、tool protocol 清洗、intent classifier、大量关键词常量：`app/agents/native_agent_runner.py:590-1460`。

**问题**：Runner 同时是运行控制器、产品策略层、Trace projector、协议清洗器、记忆写回器和 intent classifier。它不是单一 adapter，而是多个中间层混合体。

**风险**：新增学习模式、检索策略、HITL 场景或 Trace 展示都可能修改同一大文件；业务策略硬编码在运行层；测试面过大。

**更简单稳定的方向**：拆成 intent policy、agent runtime adapter、stream event projector、trace builder、tool result sanitizer、memory writeback。Runner 只编排稳定接口。

### 5.2 Agent 域路由硬编码为“创新创业”

**依据**：BASE_SYSTEM_PROMPT 写死“你是创新创业知识问答助手”：`app/agents/middleware/defaults.py:18-33`。retrieval tool description 写死 innovation/entrepreneurship：`app/tools/retrieval_tool.py:160-173`。intent classifier 关键词围绕创新/创业/商业模式/融资/路演：`app/agents/native_agent_runner.py:1239-1460`。

**问题**：项目本身是通用知识库 RAG/学习系统，用户端建议问题已经包含机器学习、题库、检索命中率等泛化场景，但底层 prompt/tool/classifier 被固定到创新创业。

**风险**：上传非创新创业资料时，Agent 可能错误短路、错误引导或错误选择工具；评测和用户体验被隐藏领域关键词污染。

**更简单稳定的方向**：系统 prompt 从知识库/课程配置、用户学习场景和当前检索范围动态生成；intent policy 根据可用工具、知识库 metadata、用户选择模式判断，而不是写死学科关键词。

### 5.3 ReAct + Agentic RAG 有技术形态，但缺业务策略控制

**依据**：默认工具包括 knowledge_retrieval、math_calculator、web_search，默认启用前两者：`app/tools/catalog.py:40-69`。Agent prompt 要求创新创业相关问题优先 `knowledge_retrieval`：`app/agents/middleware/defaults.py:18-33`。检索 tool 返回 JSON evidence_blocks，并由 result protocol 再格式化：`app/tools/result_protocol.py:103-179`。

**问题**：ReAct/工具调用/RAG 已存在，但工具策略主要由 prompt 和关键词驱动，没有结合学习业务的显式参数：资料范围、题库答案是否隐藏、是否处于练习、是否允许 web、是否必须引用、是否要求生成题目。

**风险**：Agent 对同类输入可能因措辞不同而选择不同工具；学生练习、管理员诊断、普通知识问答共用同一个 retrieval policy，容易泄漏或误用证据；Agentic RAG 的自主性没有被业务边界约束。

**更简单稳定的方向**：前端显式传入 `chat_mode`、`retrieval_scope`、`evidence_policy`、`learning_context`；后端 tool policy 根据结构化参数选择工具和 evidence source；题库工具拆成练习生成/题干检索/答案解析等受控能力。

### 5.4 Direct-answer Trace 后端生成、前端隐藏

**依据**：后端未调用工具时构造 direct answer trace：`app/agents/native_agent_runner.py:843-856`。前端 `ExecutionTraceDisplay` 过滤 `decision_code === 'direct_answer'`：`front/client/src/components/ExecutionTraceDisplay.tsx:58-64`。

**问题**：系统内部知道“本轮未调用外部工具”，但产品层隐藏这个事实。用户无法区分回答来自知识库证据还是模型已有上下文。

**风险**：用户误以为所有回答都经过知识库检索；无证据回答的信任边界不清。

**更简单稳定的方向**：展示用户可理解的“已检索/未检索/证据不足”状态，不展示 raw reasoning；direct answer 应明确提示“本回答未使用知识库证据”。

### 5.5 reasoning delta 存在，但没有形成产品化解释

**依据**：后端处理 reasoning delta，并限制 persisted chars：`app/agents/native_agent_runner.py:259-337`、`app/agents/native_agent_runner.py:1230-1234`。前端对 reasoning_delta 只记录 `reasoningTruncated`：`front/client/src/pages/chat/streaming-session.ts:97-101`。消息 metadata 只记录 reasoning redacted：`app/services/conversation_memory_service.py:125-154`。

**问题**：传输/处理 reasoning 事件有复杂度，但用户实际没有获得稳定的决策解释。Trace 有工具事件，却缺少明确表达“为什么检索/为什么不检索/为什么请求澄清/为什么证据不足”的产品化摘要。

**风险**：维护了 reasoning 管道，却没有转化为可信透明体验；如果未来误展示 raw reasoning，会带来额外风险。

**更简单稳定的方向**：不传 raw reasoning；由后端生成结构化 decision trace：检索原因、检索范围、证据数量、缺证据原因、是否使用题库/资料。

### 5.6 工具协议泄漏依赖多层补丁清洗

**依据**：Runner 检测 pending tool protocol JSON 并跳过：`app/agents/native_agent_runner.py:590-634`。前端用 marker 清洗 visible text 和 content blocks：`front/client/src/pages/chat/message-utils.ts:128-183`。result protocol 负责隐藏 debug/protocol 字段：`app/tools/result_protocol.py:103-179`。

**问题**：工具协议边界不够硬，导致后端 Runner、tool result protocol、前端 message utils 都在防止 JSON/protocol 泄漏给用户。

**风险**：新增工具或协议字段时可能没有被所有清洗层覆盖；用户可见回答混入内部 JSON 会破坏体验；多层清洗掩盖根因。

**更简单稳定的方向**：工具结果永远作为 structured artifact 进入 Trace/evidence，不进入 assistant visible text；模型可见 tool message 与用户可见 assistant message 使用不同 schema；前端清洗只作为最后防线。

### 5.7 HITL 是通用审批，不是学习澄清

**依据**：后端遇到 `__interrupt__` 后发出 `hitl_requested`：`app/agents/native_agent_runner.py:343-372`。前端 HITL UI 只有 respond/approve/edit/reject：`front/client/src/pages/ChatPage.tsx:913-971`。

**问题**：学习中常见澄清是选择资料范围、题目难度、是否显示答案、知识点、题型、是否只基于资料。当前 HITL 文案和操作偏通用技术审批。

**风险**：用户看到的操作语义不贴合学习；HITL 难以成为学习引导体验。

**遗漏能力**：结构化澄清卡片：选择文档、知识点、难度、题型、是否显示答案、引用规则；澄清结果进入 Chat Run request 的结构化参数，而不是纯文本拼回模型上下文。

### 5.8 记忆机制缺少用户可见控制和学习画像

**依据**：长期记忆以 conversation summary 存储：`app/services/conversation_memory_service.py:36-79`。如果 `conversation_memories` 表缺失，会在 service instance 内禁用长期记忆：`app/services/conversation_memory_service.py:177-203`。记忆写回失败只记录 warning：`app/agents/native_agent_runner.py:526-562`。

**问题**：当前记忆是后端内部上下文优化，不是用户可控制的产品能力，也不是跨会话学习画像。

**风险**：用户不知道系统记住了什么，无法纠正错误画像；记忆失败对体验影响隐蔽；学习数据不能进入聊天个性化。

**遗漏能力**：用户记忆中心、学习目标/偏好/薄弱点、禁止记忆项、对话总结与 learner profile 分离、记忆状态的安全 Trace 摘要。

### 5.9 反馈机制与 Agent 调试闭环不足

**依据**：用户端反馈只提交 rating/evidence_quality/hallucination_flag：`front/client/src/pages/chat/components/AssistantMessageFeedback.tsx:49-91`。管理端只展示反馈摘要和列表：`front/admin/src/pages/OperationsCenterPage.tsx:200-256`。

**问题**：反馈没有进入 Agent/RAG 的调试闭环，也没有与 run event、检索证据、RAG Eval 样本绑定为可处理问题。

**风险**：负反馈无法驱动 prompt、检索策略、文档质量或题库证据的修复；Agent 能力迭代缺少真实样本闭环。

**更简单稳定的方向**：负反馈自动关联 run_id、trace、evidence、retrieval config、文档版本；管理员可一键转评测样本或内容修复项。

---

## 6. 文档解析、Docling、清洗、切分、向量化与入库链路问题

### 6.1 Docling cache 配置与实际实现不统一

**依据**：配置中有 `ingestion_cache_dir`：`app/core/config.py:125-131`。`document_processing.py` 硬编码 `_CACHE_DIR = Path(".omx/cache/docling")`：`app/services/document_processing.py:33-41`。

**问题**：缓存目录同时存在配置项和代码硬编码，实际解析缓存使用硬编码路径，settings 不生效。

**风险**：环境隔离、测试目录、缓存清理和迁移不可控；维护者修改配置后行为不变。

**更简单稳定的方向**：解析服务只从 settings 获取 cache dir；cache key/schema/version 和目录封装为 `DoclingCache`，避免散落在解析函数中。

### 6.2 本地 `DoclingDocument` 与上游 DoclingDocument 概念冲突

**依据**：本地定义 `DoclingDocument`/`DoclingBlock` dataclass：`app/services/document_processing.py:67-115`。`_load_upstream_docling_document` 又从 cache path 读取 JSON 并 validate 为 `docling_core.types.doc.DoclingDocument`：`app/services/document_processing.py:640-649`。`build_chunk_bundle` 传入本地对象，但 HybridChunker 依赖 cache 中的上游对象：`app/services/document_processing.py:233-263`。

**问题**：本地类名与上游对象同名，职责却不同。解析结果、chunking 输入、preview 输入、metadata 输入在本地 wrapper 和上游 JSON 之间来回转换。

**风险**：维护者容易误以为传入的 `DoclingDocument` 就是 Docling 上游对象；cache path 丢失时本地 document 有 blocks 也无法 chunk；metadata 可能漂移。

**更简单稳定的方向**：本地对象改名为 `NormalizedDocument` 或 `ParsedDocumentArtifact`；artifact 中明确包含 upstream doc 和 normalized blocks，不通过 cache path 隐式重载。

### 6.3 PDF 接入绕开完整 Docling converter

**依据**：非 PDF 使用 Docling backend convert：`app/services/document_processing.py:841-884`。PDF 使用 `DoclingParseDocumentBackend`，逐页 `get_text_cells()` 后 `doc.add_text(label=PARAGRAPH, ...)`：`app/services/document_processing.py:886-934`。

**问题**：PDF 路径没有使用完整 Docling pipeline 的布局、表格、标题、OCR/结构识别能力，而是把 text cells 手工加入 paragraph。

**风险**：表格、标题层级、列表、图片、阅读顺序在进入 HybridChunker 前已经丢失；后续表格切分无法恢复结构；“Docling 接入”名义与实际 PDF 保真度不一致。

**更简单稳定的方向**：PDF 走完整 Docling converter；如果使用 text-cell fallback，必须标记为低保真并进入质量门禁。

### 6.4 HybridChunker 与自定义表格切片竞争

**依据**：`build_chunk_bundle` 先运行 `HybridChunker`：`app/services/document_processing.py:233-251`，然后用本地 table blocks 构建自定义 table chunks，并删除 block_type=table 的 HybridChunker chunks：`app/services/document_processing.py:253-263`。表格内容被 `_build_table_content` 扁平化为“表标题/表头/表行”：`app/services/document_processing.py:717-754`、`app/services/document_processing.py:1188-1198`。

**问题**：同一文档先交给 HybridChunker，再对表格另起一套规则替换。表格结构由 Docling TableItem → 本地 rows/header → 扁平文本，丢失坐标、合并单元格、列类型、跨页关系等语义。

**风险**：表格检索和问答很难精确定位行/列/单元格；HybridChunker 上下文和自定义表格上下文不一致；表格 chunk 与普通 chunk 质量指标不可比。

**更简单稳定的方向**：chunk planning 阶段明确表格策略，不先产再删；表格 chunk 保留 headers、rows、row_range、cell provenance、caption、page；embedding input 可以是 contextualized text，但 metadata 保留结构化表格。

### 6.5 旧解析/切分 API 残留且参数被忽略

**依据**：`parse_document_sections` 返回旧式 `ParsedSection`：`app/services/document_processing.py:208-230`。`build_chunk_payloads` 接收 chunk_size/overlap 参数但直接 `_ = (...)` 忽略：`app/services/document_processing.py:596-619`。该旧函数仍被单元测试覆盖。

**问题**：旧 API 留在主服务文件中，且签名保留无效参数，容易误导调用者以为配置会影响 chunk 结果。

**风险**：新旧链路同时存在，文档处理模块边界不清；调整 `ingestion_chunk_size_*` 对旧函数无效。

**更简单稳定的方向**：废弃旧 API 并移出主链路，或放到 compatibility module；删除无效参数或让参数真正进入 chunk strategy。

### 6.6 质量门禁只是指标，不阻断低质量入库

**依据**：`_clean_blocks` 做基础清洗：`app/services/document_processing.py:1173-1186`。`_build_document_metrics` 计算 avg_chunk_chars、short_chunk_ratio、duplicate_chunk_ratio、quality_status：`app/services/document_processing.py:1201-1218`。`_mark_duplicate_chunks` 只标记 duplicate/short：`app/services/document_processing.py:1221-1230`。入库任务即使 quality_status 为 warn 也继续生成 embedding 并 create chunks：`app/tasks/ingestion_tasks.py:134-182`。

**问题**：质量判断没有成为门禁。短 chunk、重复 chunk、warn 文档仍进入向量库。指标也过粗，缺少结构保真、页码覆盖、表格质量、解析丢失率等。

**风险**：低质量切片污染检索结果；管理端质量雷达无法发现；质量指标“存在但不生效”。

**更简单稳定的方向**：定义文档入库 quality gate：失败阻断，警告进入待审核；chunk 级过滤短空重复块；质量指标进入 Knowledge Management 和 Operations drilldown。

### 6.7 duplicate 检测只做文档内精确重复

**依据**：`_mark_duplicate_chunks` 对当前 chunks 做 normalized hash 计数：`app/services/document_processing.py:1221-1230`。入库时删除当前知识点旧 chunks 后创建新 chunks，没有跨知识点重复检查：`app/tasks/ingestion_tasks.py:156-182`。

**问题**：重复检测只看同一次构建的精确 hash，不覆盖跨文档重复、版本重复、近重复、模板页眉页脚。

**风险**：重复语料提高某些内容检索权重，污染相关性；管理员无法识别重复上传或版本冗余。

**更简单稳定的方向**：计算跨文档 near-duplicate signature；重复 chunk 去重或降权；保留多来源 provenance 映射。

### 6.8 token 估算粗糙，中文切片质量不可控

**依据**：`_make_static_tokenizer` 使用 `_estimate_token_count`：`app/services/document_processing.py:622-637`；估算函数在 `app/services/document_processing.py:1312-1316`。

**问题**：HybridChunker 的 tokenizer 是静态近似，中文、表格、代码、公式、英文混排误差较大。

**风险**：chunk 可能过碎或过长；embedding input 长度分布不可控；质量指标不能准确反映模型实际 token 成本。

**更简单稳定的方向**：使用与 embedding/model 接近的 tokenizer，或制定中文友好的字符/语义结构切分；质量报告记录实际 embedding input 长度分布。

### 6.9 embedding input 与展示 content 分离但缺少一致性策略

**依据**：`_docling_chunk_to_payload` 返回 `content=text` 与 `embedding_input=contextualized`：`app/services/document_processing.py:652-702`。入库前 `embedding_input` 被 pop，只把 embedding 放回 payload：`app/tasks/ingestion_tasks.py:156-157`。检索证据展示主要使用 `chunk.content`：`app/services/retrieval/retrieval_service.py:377-405`。

**问题**：向量语义基于 contextualized text，但用户/模型看到的 evidence content 可能是非 contextualized chunk text。metadata 里虽有 `contextualized_text`，但证据构造没有稳定使用它。

**风险**：向量命中来自标题路径/上下文，答案生成却看不到这些上下文；用户看到的证据与检索语义不一致。

**更简单稳定的方向**：明确 display_content 与 embedding_content/hash；evidence content 使用 contextualized text 或结构化拼接标题路径、caption、原文。

### 6.10 metadata/artifact 分散重复

**依据**：document metadata 保存 parser/chunker/cache/content hash 等：`app/services/document_processing.py:1068-1090`。入库任务生成 preview metadata、docling artifact metadata、truth signature 并 merge：`app/tasks/ingestion_tasks.py:134-181`、`app/tasks/ingestion_tasks.py:309-450`。chunk metadata 也保存 parser、chunker、contextualized_text、provenance、document_title：`app/services/document_processing.py:652-754`。

**问题**：同一事实在 document metadata、knowledge point metadata、preview artifact、docling artifact、truth signature、chunk metadata 中重复出现，缺少单一 manifest。

**风险**：解析、切分、预览、入库之间 metadata 易不一致；排查 chunk 来源需要跨多个字段和 artifact 拼接。

**更简单稳定的方向**：定义 `DocumentIngestionManifest`：source file、parser artifact、normalized artifact、chunk plan、preview、quality report、embedding revision。KnowledgePoint metadata 存 manifest id/summary，详细信息由 manifest 管理。

### 6.11 Docling runtime 依赖隐式 sys.path 注入

**依据**：`ensure_docling_runtime_on_path` 会把 `.vendor/docling_runtime` 和 `~/.codex/memories/docling_runtime*` 加入 `sys.path`：`app/core/docling_runtime.py:9-30`。

**问题**：Docling runtime 可用性依赖隐式本地目录和 sys.path 注入，而不是明确依赖或配置化 runtime path。

**风险**：开发者机器行为不一致；解析问题可能由不同 runtime 版本引起；capability 判断难以解释。

**更简单稳定的方向**：通过显式依赖、settings runtime path 或 adapter factory 管理 Docling runtime；capabilities 页面展示 runtime 来源、版本、支持格式。

---

## 7. 产品创新与关键能力缺口

以下能力不是装饰性增强，而是当前学习、问答、知识管理、题库管理、运营管理与 AI 辅助学习场景中已经暴露出的产品缺口。

### 7.1 用户端学习创新能力

1. **AI 学习教练**  
   当前聊天和学习中心断开，记忆按 conversation 而非 learner profile。系统需要用户级学习画像：目标、考试时间、薄弱点、最近错题、偏好讲解方式，并据此生成每日学习建议、错因解释、相似题、复习提醒。

2. **资料阅读 + 边读边问**  
   用户端没有材料阅读路由，证据卡片不可跳转。需要文档目录、章节/页码预览、划线笔记、段落追问、从材料生成摘要/题目/闪卡。

3. **知识图谱驱动学习路径**  
   管理端有知识图谱入口，但用户端没有图谱学习体验。需要概念地图、先修依赖、掌握状态高亮、从节点进入资料/题目/AI 讲解。

4. **题库练习防泄漏模式**  
   当前检索会把题库答案/解析放入 evidence。练习态需要隐藏答案，只给提示或分步引导，提交后再展示解析。

5. **答案转学习资产**  
   聊天回答应能一键转笔记、闪卡、练习题、复习任务、错题解释，而不是只保存在消息列表。

6. **个性化动态入口**  
   空态 prompt 不应固定，而应由最近学习状态生成：继续未完成练习、复习到期卡片、解释最近错题、阅读新资料、补齐薄弱知识点。

### 7.2 管理端创新能力

1. **内容质量工作台**  
   Docling 和 chunk metadata 已经产生质量信息，但管理端没有产品化。需要解析质量、chunk 质量、表格保真、重复率、短 chunk、页码覆盖、RAG Eval 失败 drilldown。

2. **反馈到评测的闭环**  
   负反馈应自动关联 run、Trace、evidence、文档版本、检索配置，并可一键生成 Golden Query，修复后复测。

3. **题库质量治理**  
   需要导入预检、题型质量报告、知识点覆盖率、答案格式检测、重复题检测、难度分布、题目-知识点图谱。

4. **检索配置实验室**  
   RAG Eval 应支持 dense/keyword/question source 权重、rerank、chunk strategy、cache version、Docling parser 版本对比，而不是只运行当前配置。

5. **Trace Debugger**  
   Trace Lab 应具备工具输入输出结构化查看、证据原文跳转、run 对比、错误聚类、重放、转评测样本。

---

## 8. 发现问题索引

### 8.1 用户端

- 资料浏览/阅读/证据跳转缺失：`front/client/src/App.tsx:27-39`、`front/client/src/pages/chat/components/AssistantEvidencePanel.tsx:5-45`。
- 聊天缺少检索范围、学习模式、引用策略、题库防泄漏控制：`front/client/src/pages/chat/components/ChatComposer.tsx:32-72`。
- 静态建议问题混入管理员分析场景：`front/client/src/pages/ChatPage.tsx:26-31`。
- 学习中心只支持 limit 练习，弱点驱动不足：`front/client/src/pages/LearningCenterPage.tsx:96-136`、`app/repositories/learning_repo.py:29-44`。
- 掌握度按题目而非知识点聚合：`app/repositories/learning_repo.py:111-138`、`front/client/src/pages/LearningCenterPage.tsx:311-325`。
- 判题只做 casefold 字符串比较：`app/services/learning_service.py:76-126`。
- 记忆与学习画像断开：`app/services/conversation_memory_service.py:36-79`、`app/agents/native_agent_runner.py:98-119`。

### 8.2 管理端

- 知识库/题库/Trace/RAG Eval/反馈未形成治理闭环：`front/admin/src/App.tsx:45-63`。
- KnowledgeManagementPage 过大且承担上传/轮询/预览/删除：`front/admin/src/pages/KnowledgeManagementPage.tsx:172-475`。
- QuestionManagementPage 过大且编辑/关联非原子：`front/admin/src/pages/QuestionManagementPage.tsx:171-258`。
- 知识点候选只取 200 条：`front/admin/src/hooks/useKnowledgeCandidates.ts:16-24`。
- RAG Eval 手输 source ids：`front/admin/src/pages/RagEvalLabPage.tsx:49-77`。
- Trace Lab 只是被动日志：`front/admin/src/pages/TraceLabPage.tsx:91-127`。
- 质量雷达指标过浅：`app/services/admin_operations_service.py:90-146`。
- Operations 全局任务分页可能漏任务：`app/services/admin_operations_service.py:21-88`。

### 8.3 前端架构

- shared API 泛型工厂复杂且 wrapper 重复：`front/shared/api/module-factories.ts:179-240`、`front/client/src/api/admin-questions.ts:1-61`、`front/admin/src/api/admin-questions.ts:1-61`。
- 用户端包含 admin API surface：`front/client/src/api/admin-ingestion.ts`、`front/client/src/api/admin-questions.ts`。
- ChatPage 集中 run controller/SSE/snapshot/HITL/UI：`front/client/src/pages/ChatPage.tsx:554-899`。
- SSE 韧性逻辑多层分散：`front/shared/api/sse-client.ts:41-142`、`front/client/src/pages/ChatPage.tsx:413-654`。
- pending user message 用内容匹配：`front/client/src/store/index.ts:134-167`。
- admin store 多领域聚合：`front/admin/src/store/index.ts:1-120`。

### 8.4 后端与检索

- question router/service/repo 边界过宽：`app/api/questions.py:51-360`、`app/services/question_service.py:219-628`、`app/repositories/question_repo.py:1-330`。
- vectorization retry 未派发 Celery：`app/api/questions.py:407-439` 对比 `app/services/question_service.py:511-561`。
- 题库 dirty/hash 与 embedding input 不一致：`app/repositories/question_repo.py:19-35`、`app/repositories/question_repo.py:162-188`、`app/tasks/vectorization_tasks.py:41-79`。
- question evidence 默认带答案/解析：`app/services/retrieval/retrieval_service.py:345-375`。
- retrieval 串行、count-heavy、cache 缺语料版本：`app/services/retrieval/retrieval_service.py:43-187`。
- 表格证据扩展取表格开头而非 anchor 邻域：`app/services/retrieval/retrieval_service.py:377-405`。
- retrieval_count 写入读路径：`app/repositories/knowledge_point_repo.py:147-299`。

### 8.5 Agent/RAG

- NativeAgentRunner 过重：`app/agents/native_agent_runner.py:85-562`、`app/agents/native_agent_runner.py:590-1460`。
- prompt/tool/classifier 写死创新创业：`app/agents/middleware/defaults.py:18-33`、`app/tools/retrieval_tool.py:160-173`、`app/agents/native_agent_runner.py:1239-1460`。
- Direct answer trace 被隐藏：`app/agents/native_agent_runner.py:843-856`、`front/client/src/components/ExecutionTraceDisplay.tsx:58-64`。
- reasoning delta 没有转化为产品化决策解释：`front/client/src/pages/chat/streaming-session.ts:97-101`。
- tool protocol 清洗分散：`app/agents/native_agent_runner.py:590-634`、`front/client/src/pages/chat/message-utils.ts:128-183`、`app/tools/result_protocol.py:103-179`。
- HITL 不适配学习场景澄清：`front/client/src/pages/ChatPage.tsx:913-971`。

### 8.6 Docling/入库链路

- cache dir 配置未使用：`app/core/config.py:125-131`、`app/services/document_processing.py:33-41`。
- 本地 DoclingDocument 与上游 DoclingDocument 混用：`app/services/document_processing.py:67-115`、`app/services/document_processing.py:640-649`。
- PDF 手工 text-cell 转 paragraph：`app/services/document_processing.py:886-934`。
- HybridChunker 与自定义表格切片竞争：`app/services/document_processing.py:233-263`、`app/services/document_processing.py:717-754`。
- 旧 API 残留且忽略 chunk 参数：`app/services/document_processing.py:208-230`、`app/services/document_processing.py:596-619`。
- 质量指标不阻断入库：`app/services/document_processing.py:1201-1230`、`app/tasks/ingestion_tasks.py:134-182`。
- embedding input 与展示 content 分离：`app/services/document_processing.py:652-702`、`app/tasks/ingestion_tasks.py:156-157`。
- metadata/artifact 分散：`app/services/document_processing.py:1068-1090`、`app/tasks/ingestion_tasks.py:134-181`。

---

## 9. 结语

当前系统的问题不是单一页面、单一接口或单一 bug，而是学习产品、管理端治理、Agentic RAG 策略和 Docling 入库链路之间的边界没有完全建立。用户端需要从“聊天入口”升级为“学习闭环”；管理端需要从“多个控制台”升级为“内容质量治理闭环”；Agent/RAG 需要从“prompt 和关键词驱动”升级为“结构化业务策略驱动”；Docling 链路需要减少重复包装、统一 artifact/metadata，并让质量门禁真正影响入库。

本报告列出的发现均属于需要处理的问题。处理这些问题时，应以减少链路、明确边界、显式产品状态、让质量指标进入用户/管理员工作流为判断标准，避免继续通过页面级状态、补丁式清洗、重复抽象或隐式策略增加复杂度。

