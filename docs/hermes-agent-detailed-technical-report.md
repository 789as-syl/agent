# Hermes-Agent 技术深度报告

> 文档目标：基于 `hermes-agent` 当前代码库的实际实现，抽象出可迁移到业务 Agent 系统中的工程方案。本文既分析 Hermes 现状，也补充面向业务场景的详细技术设计，重点覆盖：Agent 框架、工具调用、记忆管理、用户聊天管理、Prompt 管理、RAG、向量检索、数据切分、文档解析、文档清洗。

---

# 1. 结论先行

## 1.1 对 Hermes-Agent 的核心判断

Hermes-Agent 的主架构不是显式状态图编排，也不是 LangGraph 式节点流，而是一个：

- **单 Agent 工具调用内核**
- 叠加 **多入口会话层（CLI / Gateway / ACP / API）**
- 叠加 **工具注册层 / Memory Provider 层 / Context Engine 层 / Prompt 拼装层**
- 辅以 **子 Agent delegation** 能力

其核心范式可概括为：

> **Tool-Centric Conversational Agent Runtime**

即：
- 由 `AIAgent.run_conversation()` 驱动单轮或多轮推理
- 模型自主决定工具调用
- Runtime 负责消息组织、工具执行、重试恢复、上下文压缩、会话持久化、安全守卫

关键代码依据：
- `run_agent.py:8107-11255`：主对话循环
- `model_tools.py:196-315, 421-533`：工具 schema 获取与 dispatch
- `gateway/run.py:8545-8600`：Gateway 对 Agent 实例缓存与复用
- `hermes_state.py:36-112, 355-500, 791-931`：会话持久化与消息回放

---

## 1.2 哪些思想最值得迁移

Hermes 最值得复用的不是它的巨型 runtime 文件，而是以下工程思想：

1. **`session_key` 与 `session_id` 分离**：逻辑会话与物理 transcript 分离
2. **稳定 system prompt + 动态上下文侧注入**：保护 prompt cache
3. **长期记忆分层**：偏好记忆、情节记忆、插件记忆分开
4. **工具统一注册总线**：Built-in / MCP / Plugin / Memory tools 同层挂接
5. **上下文压缩是系统能力，而不是简单截断**
6. **工具安全是 runtime 的一部分，不是外围补丁**
7. **辅助模型承担低价值高频任务**：压缩、检索摘要、审批、标题生成等

---

## 1.3 哪些部分不适合直接照搬

不建议直接照搬的部分：

1. `run_agent.py` 过于集中，属于 **God Runtime**
2. Planning / Retry / Fallback / Compression 主要靠 **隐式状态变量** 组织
3. Prompt 层虽然有分层，但仍主要是 **字符串拼装**
4. Memory surface 很丰富，但缺少统一 recall orchestrator
5. 工具 handler 统一返回 JSON string，工程上偏弱类型

如果你的目标是复杂业务 Agent，推荐：

> **保留 Hermes 的会话层 / 工具层 / 记忆思想 / 压缩思想，重构为显式状态图编排架构。**

---

# 2. Hermes-Agent 的整体架构设计

## 2.1 模块分层

可抽象成如下结构：

```text
Interface Layer
├─ CLI (cli.py)
├─ Gateway (gateway/run.py)
├─ ACP / API / Batch

Session Layer
├─ SessionSource / SessionContext / session_key
├─ SessionStore (sessions.json + transcript mapping)
└─ SessionDB (SQLite + FTS5 + lineage)

Agent Runtime Layer
└─ AIAgent (run_agent.py)
   ├─ Prompt Builder
   ├─ Memory Store / Memory Manager
   ├─ Context Compressor / Context Engine
   ├─ Provider Adapter
   └─ Tool Orchestration Loop

Capability Layer
├─ Tool Registry
├─ Toolsets
├─ Built-in Tools
├─ MCP Tools
├─ Plugin Tools
├─ Memory Provider Tools
└─ Context Engine Tools

Auxiliary LLM Layer
├─ Compression
├─ Session Search Summarization
├─ Smart Approval
├─ Title Generator
└─ Vision / Extraction
```

代码依据：
- `tools/registry.py:1-309`
- `model_tools.py:1-160`
- `toolsets.py:29-497`
- `run_agent.py:559-1632`
- `gateway/session.py:66-328, 498-1090`

---

## 2.2 架构性质

### 架构视角

Hermes 当前是：

- **单 Agent 主架构**
- **多 Agent 辅助能力**（`delegate_task`）
- **工作流逻辑主要在 runtime 控制流中**，而不是显式 graph

### 策略视角

它强调：

- 尽量少建显式编排节点，更多依赖模型 + runtime 守卫
- 尽量让系统前缀稳定，减少 prompt cache 失效
- 尽量让工具层统一，provider 差异下沉到 API adapter

### 工程视角

优点：
- 扩展点多
- 会话恢复强
- provider 兼容性强
- 本地开发 Agent 体验成熟

不足：
- 运行时复杂度过高
- 状态转移不可视化
- 文件过大，后续维护门槛高

---

# 3. 核心运行流程

## 3.1 主链路

请求进入系统后的主流程：

1. **入口层解析来源与会话**
   - Gateway 构造 `SessionSource`
   - 计算 `session_key`
   - 获取或创建 `session_id`
   - 加载历史 transcript
   - 代码：`gateway/session.py:439-495, 686-771`、`gateway/run.py:3412-3548`

2. **构造 Session Context Prompt**
   - 平台、用户、线程、home channel、delivery options 注入
   - 代码：`gateway/session.py:186-328`

3. **初始化或复用 `AIAgent`**
   - Gateway 对同 session 的 agent 做缓存，避免每轮重建 frozen system prompt
   - 代码：`gateway/run.py:7735-7766, 8545-8600`

4. **`run_conversation()` 启动**
   - sanitize 用户输入
   - 恢复 todo store
   - 追加 user message
   - 构建或复用 cached system prompt
   - 代码：`run_agent.py:8149-8313`

5. **动态上下文准备**
   - memory provider prefetch
   - plugin pre_llm_call context
   - 注入到当前 user message，而不是 system prompt
   - 代码：`run_agent.py:8446-8467, 8538-8555`

6. **构造 provider-specific API 请求**
   - Chat Completions / Codex Responses / Anthropic Messages / Bedrock Converse 分支
   - 代码：`run_agent.py:6364-6665`

7. **模型响应归一化**
   - 提取 reasoning
   - 标准化 assistant message
   - 处理 tool calls
   - 代码：`run_agent.py:2182-2247, 6727-6843`

8. **工具执行**
   - 顺序或并行
   - 结果回灌为 `role="tool"`
   - 代码：`run_agent.py:267-308, 7163-7913`

9. **重试 / fallback / compression / continuation**
   - invalid tool / invalid JSON / truncated output / context overflow / provider fallback
   - 代码：`run_agent.py:5843-5985, 7956-8105, 9125-9260, 9837-9965, 10393-10531`

10. **持久化与收尾**
   - session log
   - SQLite transcript
   - token/cost
   - memory sync / background review
   - 代码：`run_agent.py:2436-2495, 2979-3039, 11138-11253`

---

# 4. Agent 框架详细方案分析

## 4.1 Runtime 设计

`AIAgent` 是 Hermes 的总控对象，构造时挂载：

- provider/client 状态
- 工具 schema 列表
- SessionDB
- TodoStore
- MemoryStore
- MemoryManager
- ContextCompressor / ContextEngine
- callbacks
- token / cost / retry / interrupt 状态

代码依据：`run_agent.py:559-1632`

### 优点

- 对外只暴露一个统一 runtime 抽象
- CLI/Gateway/Batch 可复用
- 所有安全、记忆、压缩、fallback 都能在一个地方统一治理

### 问题

- 单类承担过多职责
- 不适合业务流程型 Agent 的显式节点编排
- 代码阅读与回归测试成本高

### 对业务系统的建议

建议拆成：

- `ConversationRuntime`
- `PromptAssembler`
- `MemoryOrchestrator`
- `ToolExecutor`
- `ProviderAdapter`
- `RecoveryPolicy`
- `SessionPersistence`

---

## 4.2 任务状态与生命周期

Hermes 没有显式 graph state，而是依靠多个 runtime counter/flag：

- `api_call_count`
- `compression_attempts`
- `length_continue_retries`
- `_invalid_tool_retries`
- `_invalid_json_retries`
- `_budget_grace_call`
- `_interrupt_requested`
- `_turns_since_memory`
- `_iters_since_skill`

代码依据：`run_agent.py:8174-8187, 8420-8428`

### 评价

这属于 **隐式状态机**：
- 快速开发时很高效
- 但后续引入复杂业务流程会越来越难维护

### 建议

业务 Agent 中应显式维护：

```text
AgentState
├─ session_meta
├─ message_state
├─ active_plan
├─ retrieved_context
├─ tool_execution_state
├─ retry_state
├─ safety_state
├─ completion_state
└─ observability_state
```

---

## 4.3 子 Agent 机制

`delegate_task` 把 subagent 设计成一种工具：

- 默认继承父 Agent 工具集交集
- 禁止子 Agent 再无限 delegation（深度限制）
- 默认 `skip_context_files=True`、`skip_memory=True`
- 批量任务可并发执行

代码依据：
- `tools/delegate_tool.py:90-122`
- `tools/delegate_tool.py:238-397`
- `tools/delegate_tool.py:623-813`

### 优点

- 不把多 Agent 架构强行推到系统主线
- 保持“默认单 Agent，必要时 delegation”

### 风险

- subagent 结果仍以文本 summary 回到父 Agent，结构化程度不高
- 更像“外包工具”，不是显式多角色 workflow

---

# 5. 工具调用详细技术方案

## 5.1 工具注册与发现机制

Hermes 的工具总线以 `ToolRegistry` 为中心。

### 机制

- 工具模块顶层调用 `registry.register(...)`
- `discover_builtin_tools()` 用 AST 检测顶层注册语句，自动 import
- MCP / plugins 在 `model_tools.py` 初始化时自动发现

代码依据：
- `tools/registry.py:28-73`
- `tools/registry.py:176-225`
- `model_tools.py:128-145`

### 工程价值

- 不需要手工维护工具导入表
- 工具的 schema / handler / toolset / check_fn 全部在同一注册点描述
- 非常适合扩展型 Agent 平台

---

## 5.2 Toolset 与动态可用性

Hermes 不是“所有工具永远全开”，而是：

- 用 `toolsets.py` 管理逻辑工具集
- 用 `enabled_toolsets / disabled_toolsets` 做裁剪
- 再由 `check_fn` 过滤不可用工具

代码依据：
- `toolsets.py:66-497`
- `model_tools.py:196-315`

### 亮点

- Toolset 支持组合
- Plugin / MCP server 也能被映射成 toolset alias
- `execute_code` 等工具会动态重写 schema，仅暴露当前真可用能力

代码依据：`model_tools.py:272-303`、`tools/code_execution_tool.py:1295-1357`

---

## 5.3 工具协议与结果封装

Hermes 统一采用 function-calling 风格协议：

- schema 形态：OpenAI-compatible
- handler 返回：JSON string
- registry.dispatch 负责调用与异常兜底

代码依据：`tools/registry.py:258-309, 456-482`

### 优势

- provider 兼容广
- transcript replay 简单
- MCP / Plugin / Built-in 全部统一到同一执行协议

### 不足

- 工程上偏弱类型
- 缺少统一 typed envelope（如 `status/code/data/meta`）

### 建议

业务平台中建议升级为：

```json
{
  "ok": true,
  "code": "SUCCESS",
  "data": {...},
  "meta": {...},
  "warnings": []
}
```

然后再在最外层兼容 function calling 序列化。

---

## 5.4 Agent-level 工具与 Runtime 内部状态

Hermes 很务实地承认：并非所有工具都适合完全 registry-dispatch。

以下工具依赖 Agent 内部状态，因此在 `AIAgent._invoke_tool()` / `_execute_tool_calls_*()` 中拦截：

- `todo`
- `memory`
- `session_search`
- `clarify`
- `delegate_task`
- memory provider tools
- context engine tools

代码依据：`run_agent.py:7206-7265, 7653-7779`

### 评价

这是正确的工程妥协。

如果强行全部做纯函数式 handler，反而会让运行时状态在各处漂移。

---

## 5.5 并行工具调用方案

Hermes 对并发工具调用做了精细控制，而不是简单“有多个 tool_calls 就并行”。

### 并行条件

- `clarify` 永不并行
- 明确标记为 read-only 的工具可以并行
- `read_file/write_file/patch` 只有在路径不重叠时可并行

代码依据：
- `run_agent.py:214-240`
- `run_agent.py:267-308`
- `run_agent.py:7163-7535`

### 价值

- 降低互相踩状态的概率
- 保留并行提速收益
- 比很多 Agent 框架的“盲并行”更安全

---

## 5.6 工具失败恢复机制

Hermes 的工具失败恢复分多层：

### 1. Tool name hallucination 修复
- 大小写/下划线/模糊匹配自动修复
- 无法修复时把错误回灌给模型做自纠
- 代码：`run_agent.py:3590-3616, 10393-10440`

### 2. 参数 JSON 校验
- invalid JSON 会重试
- 多次失败则生成 tool error results，促使模型自修复
- 代码：`run_agent.py:10444-10531`

### 3. 大输出结果预算控制
- 超过阈值的 tool result 会被写入 sandbox 文件，仅回传 preview
- 整个 turn 还有 aggregate budget enforcement
- 代码：`tools/tool_result_storage.py:116-225`

### 4. 背景任务与长运行
- `terminal(background=true)` 启动后台进程
- `process` 工具可 list/poll/log/wait/kill/write/submit/close
- `ProcessRegistry` 可 checkpoint/recover
- 代码：`tools/terminal_tool.py:1348-1432`、`tools/process_registry.py:833-1175`

---

## 5.7 工具安全方案

Hermes 的工具安全设计非常值得借鉴。

### A. 危险命令审批
- regex 检测危险命令
- 支持 CLI / Gateway 审批流
- 支持 smart approval（辅助 LLM 判定）
- 代码：`tools/approval.py:186-197, 534-659, 693-745`

### B. 文件陈旧性检测
- 读取后记录 mtime
- 写/patch 前检查文件是否在外部或并发 Agent 下被修改
- 代码：`tools/file_tools.py:492-619`

### C. 重复读取防循环
- 多次连续读取同一文件同一区间会警告甚至阻断
- 代码：`tools/file_tools.py:330-447`

### D. destructive 操作前 checkpoint
- 写文件/patch/危险 terminal 命令前创建 checkpoint
- 代码：`run_agent.py:7336-7355, 7623-7644`

---

# 6. 记忆管理详细方案

Hermes 的记忆体系可以拆成四层：

1. **短期窗口记忆**：当前 `messages`
2. **策展型长期记忆**：`MEMORY.md` + `USER.md`
3. **情节记忆**：SQLite transcript + `session_search`
4. **插件型语义记忆**：Honcho / Holographic / Mem0 等

---

## 6.1 短期记忆方案

### 当前实现

短期记忆以 `messages` 列表为主，不额外维护复杂工作记忆图。

增强机制包括：
- `todo` 工具维护活动计划
- context compression summary 维护 handoff 信息
- external memory provider prefetch 在 API 调用时侧注入

代码依据：
- `run_agent.py:8222-8258`
- `tools/todo_tool.py:90-122`
- `run_agent.py:8538-8555`
- `agent/context_compressor.py:571-669`

### 评价

优点：
- 简单、稳、与 function-calling 模型天然兼容
- 对 coding / task agent 非常实用

缺点：
- 工作状态主要还是文本化
- 没有显式机器状态对象
- summary 仍存在 LLM 漂移风险

### 迁移建议

在业务 Agent 中拆成：

- `conversation_messages`
- `working_summary`
- `active_plan`
- `execution_artifacts`
- `tool_state`

不要把所有工作记忆都塞在 message history 里。

---

## 6.2 内置长期记忆：MemoryStore

### 数据结构

- `MEMORY.md`：环境、约定、工具经验
- `USER.md`：用户画像、偏好、交流风格

代码依据：`tools/memory_tool.py:3-24, 105-140`

### 关键机制

1. session start 时 `load_from_disk()`
2. 生成 frozen snapshot，注入 system prompt
3. mid-session 写盘，但**不修改当前 system prompt**
4. `add/replace/remove` 三种动作维护条目
5. 写入前做注入/泄露扫描
6. 用 char limit 控制体积

代码依据：
- `tools/memory_tool.py:124-140`
- `tools/memory_tool.py:222-357`
- `tools/memory_tool.py:359-370`
- `tools/memory_tool.py:513-580`

### 核心设计动机

- 保护 prompt cache
- 让长期记忆保持人工可审阅、可编辑、可回退
- 避免把临时任务状态沉淀成长期污染

### 工程评价

适合作为：
- 偏好与环境事实存储
- 轻量个人助理 memory

不适合作为：
- 企业知识库
- 高规模事实库
- 多租户、强 schema、带版本演化的生产 memory system

---

## 6.3 情节记忆：SessionDB + session_search

### SessionDB

SQLite 持久化：
- `sessions` 表
- `messages` 表
- `messages_fts` FTS5 虚表
- parent_session_id lineage
- token/cost 字段

代码依据：`hermes_state.py:36-112, 355-500, 791-931, 990-1085`

### session_search 工作流

1. FTS5 搜消息
2. 聚合 session
3. 解析 parent chain，去掉当前 session lineage
4. 加载 transcript
5. 对命中片段附近截断
6. 辅助模型生成 focused summary

代码依据：`tools/session_search_tool.py:297-484, 500-560`

### 优点

- 把“过去做过什么”与“用户偏好”分离
- 保留完整历史，可审计
- recent mode 零 LLM 成本，体验好

### 局限

- 主要是全文检索，不是语义检索
- 检索召回质量受 query formulation 影响较大
- 大规模生产场景下 SQLite 不是最终方案

### 迁移建议

保留这套思想，但升级为：

- Transcript Store：Postgres / ClickHouse / Elasticsearch
- FTS + Embedding Hybrid Search
- Session Summary Table
- Lineage / parent-child conversation graph

---

## 6.4 插件记忆：MemoryProvider / MemoryManager

### 接口

`MemoryProvider` 抽象包括：

- `initialize()`
- `system_prompt_block()`
- `prefetch()`
- `queue_prefetch()`
- `sync_turn()`
- `get_tool_schemas()`
- `handle_tool_call()`
- `on_turn_start()`
- `on_session_end()`
- `on_pre_compress()`
- `on_delegation()`

代码依据：`agent/memory_provider.py:42-204`

### 管理器设计

- Built-in provider 始终可用
- 最多一个 external provider
- 防止 schema 膨胀与多 provider 冲突

代码依据：`agent/memory_manager.py:83-175, 210-373`

### 代表插件

#### Honcho
- 支持 context-only / tools-only / hybrid 三种 recall mode
- 支持 prefetch context + dialectic reasoning supplement
- 注重自动 recall 注入
- 代码：`plugins/memory/honcho/__init__.py:461-615, 631-677`

#### Holographic
- 结构化 fact store
- trust score
- entity probe / related / reason / contradict
- 偏向深层语义事实记忆
- 代码：`plugins/memory/holographic/__init__.py:37-73, 114-169`

### 工程评价

Hermes 这层设计已经很接近企业 Agent 的“可插拔记忆总线”。

建议在业务系统中继续保留，但补上：

- recall ranking
- provider fusion
- confidence/recency/source metadata
- explicit retrieval policy

---

# 7. 用户聊天管理详细方案

## 7.1 会话抽象

Hermes 的聊天管理不是单纯 conversation_history，而是三层抽象：

- `SessionSource`：消息来源、平台、用户、线程
- `session_key`：逻辑会话 key
- `session_id`：物理 transcript id

代码依据：`gateway/session.py:66-137, 439-495, 686-771`

### 价值

- 支持线程会话与群聊会话隔离策略
- 支持 reset policy
- 支持 `/resume`、会话分裂、压缩 continuation

---

## 7.2 Gateway 对多平台聊天的处理

Gateway 在进入 runtime 之前会注入：

- 当前来源平台
- 当前聊天上下文
- 是否多用户 thread
- connected platforms
- delivery options
- home channels
- 是否需要 PII redaction

代码依据：`gateway/session.py:186-328`

### 这意味着

Hermes 的“聊天管理”不仅仅是消息缓存，更是：

> **平台上下文管理 + 路由信息管理 + 交互边界管理**

---

## 7.3 Gateway 缓存 Agent 以保持前缀稳定

Gateway 会按以下信息计算 Agent 配置签名：

- model
- api_key fingerprint
- base_url
- provider
- api_mode
- enabled_toolsets
- ephemeral prompt

代码依据：`gateway/run.py:7735-7766`

如果签名不变，则复用上一轮 `AIAgent`：
- 保留 frozen system prompt
- 保留已加载工具 schema
- 提高 prompt cache 命中率

代码依据：`gateway/run.py:8545-8600`

### 这是 Hermes 聊天体验的关键工程点

它不是每轮都全量重建 Agent，这非常重要。

---

## 7.4 用户聊天策略特征

Hermes 没有独立 Intent Classifier，主要通过以下方式实现对话分流：

- system policy guidance
- tool schema guidance
- skills prompt
- session context prompt
- platform hints

代码依据：`run_agent.py:3291-3456`、`agent/prompt_builder.py:144-253, 583-808`

### 优点

- 泛化性强
- 对 task-oriented coding agent 很高效

### 局限

- 业务聊天场景（客服、营销、审批）缺少显式意图层
- 对复杂多目标会话不够结构化

### 业务化建议

增加一层显式 Chat Router：

- casual chat
- FAQ / QA
- workflow task
- tool execution task
- escalation / human handoff
- clarification needed

---

# 8. Prompt 管理详细方案

## 8.1 Prompt 分层设计

Hermes 的系统 Prompt 由 `_build_system_prompt()` 分层拼装：

1. SOUL.md 或默认身份
2. tool-aware behavioral guidance
3. subscription / tool-use discipline guidance
4. 调用方 system message
5. built-in memory snapshot
6. external memory provider block
7. skills index
8. project context files
9. 时间、session、model、provider 信息
10. environment hints
11. platform hints

代码依据：`run_agent.py:3291-3456`

---

## 8.2 Prompt 设计的核心原则：稳定前缀

Hermes 的 Prompt 管理最重要的思想：

> **能不改 system prompt，就不要改。**

具体做法：

- memory snapshot 只在 session start 冻结
- continuing session 尽量复用 SQLite 中保存的旧 system prompt
- dynamic recall / plugin context 注入到 user message
- ephemeral prompt 在 API-call time 注入，不写回缓存

代码依据：
- `run_agent.py:8267-8313`
- `run_agent.py:8538-8595`
- `tools/memory_tool.py:109-123, 359-370`

### 工程价值

这是一个很成熟的高缓存命中 Prompt 设计方案，建议强复用。

---

## 8.3 Skills Prompt 管理方案

Hermes 对 skills prompt 做了两层缓存：

1. 进程内 LRU cache
2. 磁盘 snapshot + manifest 校验

代码依据：`agent/prompt_builder.py:424-704`

### 优点

- skills 很多时不必每次全量扫盘
- prompt build 冷启动更快

### 对业务 Agent 的启发

任何“规则库 / playbook / operation guide”系统，都可以采用相同方案：

- 索引构建
- snapshot 缓存
- manifest 校验
- 仅按 availability / condition 做选择注入

---

## 8.4 Context Files 管理方案

Hermes 会按优先级加载：

1. `.hermes.md / HERMES.md`
2. `AGENTS.md`
3. `CLAUDE.md`
4. `.cursorrules`

代码依据：`agent/prompt_builder.py:921-1045`

并且会对这些 context file 做 prompt injection threat scan。

### 评价

对 coding agent 很有价值，适合作为项目内“局部操作规范”输入源。

### 业务场景迁移

可扩展为：

- tenant policy
- department policy
- workflow playbook
- compliance guide
- channel-specific response guide

---

# 9. RAG 详细方案：Hermes 当前实现与业务化升级

## 9.1 Hermes 当前是否有 RAG？

严格说，Hermes **没有完整标准 RAG pipeline**，但已经具备多个 RAG 原件：

1. **Session Search = Episodic Retrieval + Summarization**
2. **Memory Provider Prefetch = Query-time Recall Injection**
3. **Holographic / Honcho = 可选语义记忆层**
4. **Project context files / skills = 规则型检索上下文**

所以 Hermes 更像：

> **Hybrid Recall System**

而不是传统“文档向量库问答 RAG”。

---

## 9.2 面向业务 Agent 的推荐 RAG 架构

建议建设 5 段式 RAG：

```text
Ingestion Layer
├─ 文档解析
├─ 文档清洗
├─ 分块 / 切片
├─ 元数据提取
└─ 向量化 / 索引写入

Knowledge Store Layer
├─ 原文存储（Object Store / DB）
├─ Chunk Store
├─ Metadata Store
├─ Vector Store
└─ Knowledge Graph / Entity Store（可选）

Retrieval Layer
├─ Query Rewriter
├─ Hybrid Retriever (BM25 + Vector)
├─ Metadata Filter
├─ Reranker
└─ Context Assembler

Agent Integration Layer
├─ Session-aware recall
├─ Tool-call-time retrieval
├─ Prompt-time context injection
└─ Citation / traceability

Evaluation & Ops Layer
├─ Recall@K / MRR / NDCG
├─ Hallucination detection
├─ Grounding score
├─ Query analytics
└─ Ingestion quality monitor
```

---

# 10. 向量检索详细技术方案

## 10.1 索引分层

建议至少分 4 类索引：

1. **FAQ / 结构化问答索引**
2. **政策/制度/手册索引**
3. **业务文档索引**
4. **会话情节索引**

不要把所有内容混在一个大向量表里。

### 推荐元数据字段

```json
{
  "doc_id": "",
  "chunk_id": "",
  "tenant_id": "",
  "knowledge_type": "policy|manual|faq|conversation|ticket",
  "source_type": "pdf|docx|html|wiki|db|chat",
  "title": "",
  "section_path": ["", ""],
  "author": "",
  "version": "",
  "created_at": "",
  "updated_at": "",
  "language": "zh|en",
  "tags": [""],
  "security_level": "public|internal|restricted",
  "token_count": 0,
  "entity_refs": [""],
  "keyword_refs": [""],
  "checksum": ""
}
```

---

## 10.2 检索链路建议

### 推荐链路

1. **query normalization**
2. **query classification**
   - factual QA
   - procedure lookup
   - policy compliance
   - document location
   - conversational recall
3. **query rewrite / expansion**
4. **hybrid retrieval**
   - BM25 / keyword
   - vector retrieval
5. **metadata filter**
6. **rerank**
7. **context pack assembly**
8. **citation-aware prompt injection**

### 为什么要 hybrid retrieval

只做向量检索会在以下场景吃亏：
- 精确术语
- 编号条款
- 错误码
- API 名称
- 合同编号
- 文件路径

因此推荐：

> **Keyword/BM25 召回 + Vector 召回 + Rerank**

---

## 10.3 向量库选型建议

### 小中型业务
- PostgreSQL + pgvector
- 优点：一致性好、开发简单、事务友好

### 大规模检索
- Milvus / Qdrant / Weaviate
- 适合多租户和高吞吐 ANN

### 搜索+向量一体
- Elasticsearch / OpenSearch
- 适合同时强依赖 keyword/filter/vector 混合检索

### 建议

如果你的系统已有业务库：
- 先 **Postgres + pgvector + BM25/tsvector**
- 后续再按规模迁移

---

# 11. 数据切分详细技术方案

## 11.1 切分目标

切分不是为了“平均长度”，而是为了同时满足：

- 语义完整
- 检索可命中
- prompt 可装配
- rerank 有足够上下文
- 引用定位清晰

---

## 11.2 推荐切分策略

### A. 结构优先切分（首选）

按文档结构切：
- 标题
- 章节
- 小节
- 表格
- 列表
- 代码块
- FAQ item

### B. 语义窗口切分（次级）

当结构不足时：
- 按段落聚合
- 按句子边界扩缩
- 控制 token 区间

### C. 滑窗 overlap

推荐：
- chunk 400~800 tokens
- overlap 50~120 tokens

### D. 特殊内容独立切分

- 表格独立切块
- 代码块独立切块
- Q/A 对独立切块
- 标题与正文绑定切块

---

## 11.3 不同文档类型的切分建议

### 政策制度类
- 按“条/款/项”切
- 保留层级路径
- chunk 偏小，引用精准优先

### 产品手册/知识库
- 按标题+段落切
- 中等 chunk
- 保留前后文 overlap

### FAQ
- 一问一答一块
- 不要打散

### 技术文档/API 文档
- endpoint/参数/示例分块
- 代码样例单独切
- 错误码表单独切

### 会话/工单/邮件线程
- 按 turn group 或主题段切
- 同时保留 sender、时间、主题、状态等 metadata

---

# 12. 文档解析详细技术方案

## 12.1 解析目标

目标不是把文件转成纯文本，而是尽量保留：

- 结构层级
- 表格
- 列表
- 标题路径
- 代码块
- 链接
- 图片 OCR / caption（如需要）
- 页码 / section 定位信息

---

## 12.2 推荐解析管线

### PDF
推荐两级：

1. **版面感知解析**
   - pdfplumber / pymupdf / unstructured / mineru / nougat（视场景）
2. **结构恢复**
   - 标题检测
   - 表格识别
   - 页码保留
   - block 合并

### Word / PPT / Excel
- docx: python-docx / mammoth
- pptx: python-pptx
- xlsx: openpyxl / pandas

### HTML / Wiki / CMS 页面
- readability + boilerplate removal
- 保留 DOM heading path
- 保留表格与列表结构

### 图片 / 扫描件
- OCR（PaddleOCR / Tesseract / 云 OCR）
- 页面布局还原
- 表格 OCR 与正文 OCR 分流

---

## 12.3 解析输出中间格式建议

建议定义统一中间文档结构：

```json
{
  "doc_id": "",
  "title": "",
  "source": "",
  "blocks": [
    {
      "block_id": "",
      "type": "heading|paragraph|table|list|code|image_caption",
      "text": "",
      "page": 1,
      "section_path": ["", ""],
      "bbox": null,
      "metadata": {}
    }
  ]
}
```

先有中间结构，再做清洗与切分。不要直接“原始文件 -> chunk”。

---

# 13. 文档清洗详细技术方案

## 13.1 清洗目标

文档清洗的目标不是“越干净越好”，而是：

- 去掉噪音
- 保留结构
- 保留检索价值
- 保留引用定位能力

---

## 13.2 推荐清洗步骤

### 1. 编码与字符标准化
- Unicode normalize
- 去除非法字符、零宽字符
- 标准化空格、换行、全角半角

### 2. Boilerplate 去除
- 页眉页脚
- 导航菜单
- 面包屑
- 广告、版权、分享区
- 重复页脚声明

### 3. 结构噪音清洗
- 连续空行压缩
- OCR 重复行合并
- 目录页与正文分离
- 重复标题去重

### 4. 内容级清洗
- 表格列对齐修正
- 列表编号标准化
- 代码块缩进修正
- 错误分词/断词修复

### 5. 语义增强
- 提取标题路径
- 提取关键词
- 提取实体
- 提取日期、版本、编号
- 标记 FAQ / Policy / Procedure / API 等文档类型

---

## 13.3 清洗质量控制

建议为每批文档输出质量指标：

- parse_success_rate
- structure_recovery_rate
- table_recovery_rate
- duplicate_block_rate
- average_chunk_token
- empty_chunk_rate
- OCR_noise_rate

并保留原文与清洗后 diff 抽样检查。

---

# 14. RAG 在 Agent Runtime 中的集成方案

## 14.1 推荐不要把 RAG 只做成 prompt 前置步骤

更好的做法是三层接入：

### A. Pre-turn Retrieval
在用户消息进入后先做 recall，适合：
- FAQ
- 规章制度
- 知识问答

### B. Tool-time Retrieval
把检索做成工具，允许 Agent 在执行过程中按需再次检索，适合：
- 多跳问题
- 任务型文档查阅
- 动态 narrowing

### C. Post-tool Verification Retrieval
在生成最终回答前再次拉相关证据做 grounded verification，适合：
- 高风险业务
- 合规/政策类问答

---

## 14.2 推荐的 RAG Tool 设计

建议至少设计以下工具：

1. `kb_search`
   - keyword + vector hybrid recall
2. `kb_fetch_chunk`
   - 根据 chunk_id 拉完整原文
3. `kb_browse_doc`
   - 按 doc title/section 浏览结构化文档
4. `kb_cite_verify`
   - 检查回答是否由现有 chunk 支撑
5. `kb_upsert_job_status`
   - 文档入库任务状态跟踪

如果业务复杂，再扩展：
- `entity_search`
- `policy_lookup`
- `faq_lookup`
- `ticket_recall`

---

## 14.3 Context Assembler 方案

把召回结果注入模型前，建议做一个 context assembler：

输入：
- query
- topK chunks
- rerank scores
- chunk metadata
- token budget

输出：
- `evidence_bundle`
- `citation_map`
- `compressed_context`

### 组装原则

1. 先保留高分 chunk
2. 再保留跨文档多样性
3. 同文档相邻 chunk 合并
4. 保留 citation metadata
5. 超预算时优先保留高分 + 高覆盖 chunk

---

# 15. 业务 Agent 的推荐总体技术蓝图

## 15.1 建议的目标分层

```text
Client / Channel Layer
├─ Web / IM / API / Workflow

Conversation Orchestrator
├─ Session Loader
├─ Intent Router
├─ Planner
├─ Executor
├─ Verifier
└─ Response Builder

State Layer
├─ Conversation Messages
├─ Working Memory
├─ Plan State
├─ Tool State
└─ Safety State

Knowledge Layer
├─ Profile Memory
├─ Episodic Memory
├─ Semantic RAG
└─ Structured Business Data

Tool Layer
├─ Internal Tools
├─ Business Tools
├─ Search / KB Tools
├─ External API Tools
└─ Human Handoff / Approval Tools

Observability Layer
├─ Logs
├─ Trace
├─ Prompt Snapshot
├─ Tool Span
├─ Retrieval Span
└─ Eval Metrics
```

---

## 15.2 建议从 Hermes 直接继承的模块思想

优先复用 Hermes 的以下思想或实现方式：

- Session 抽象：`SessionSource / session_key / session_id`
- transcript 持久化与 episodic recall
- tool registry / toolset / MCP 接入思想
- context compression handoff summary
- built-in memory + external provider 双层设计
- approval / staleness / output budgeting 安全体系
- stable prompt prefix 策略

---

## 15.3 建议重构的模块

建议重构：

- `run_agent.py` → 显式状态图 orchestrator
- Prompt 拼装 → typed prompt layers
- Memory recall → unified recall orchestrator
- Tool results → typed envelope + standardized error model
- Recovery policy → 独立 policy engine

---

# 16. 最终建议

## 16.1 如果你的目标是自研业务 Agent

最优策略不是“复制 Hermes”，而是：

> **以 Hermes 作为能力设计样板，以 LangGraph/显式状态机作为业务编排骨架。**

### 推荐路线

1. 保留 Hermes 的：
   - 会话分层
   - 工具注册
   - memory 分层思想
   - context compression
   - tool safety

2. 重构为：
   - 明确 AgentState
   - 明确节点流
   - 明确 retrieval pipeline
   - 明确 typed tool protocol
   - 明确 trace/eval 框架

3. 构建业务级 RAG：
   - 结构解析
   - 文档清洗
   - hybrid retrieval
   - rerank
   - context assembler
   - grounded answer/citation

---

## 16.2 一句话总评

Hermes-Agent 是一个**非常强的本地工具型 Agent 工程底座**，尤其擅长：

- 多 provider 兼容
- 工具调用 runtime
- 上下文压缩
- 会话恢复
- 多入口平台集成

但如果你的目标是：

- 高可扩展业务 Agent
- 显式工作流编排
- 标准化 RAG / 知识系统
- 强可观测与可审计

那么最合理的方式是：

> **保留 Hermes 的子系统思想，重构其 runtime 为显式分层的业务 Agent 平台。**
