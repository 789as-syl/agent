# Chat Run 三事实源契约（checkpoint / run_events / messages）

> 版本：2026-04-27（B1 契约收敛草案）
> 适用范围：`app/services/chat_run_stream_service.py`、`app/agents/native_agent_runner.py` 及其关联 repository/service。

## 1. 目标与非目标

### 1.1 目标
- 统一 Chat Run 在流式执行、回放、中断、重试、重新生成、HITL 场景下的**事实源边界**。
- 明确三个存储面的职责：
  - `checkpoint`：运行时可恢复状态。
  - `run_events`：可回放、可审计的事件流水。
  - `messages`：用户可见的最终会话历史。
- 让后续实现以**契约测试**为准，不再依赖“临时兜底逻辑”。

### 1.2 非目标
- 不在本文件中要求大规模重构 `native_agent_runner.py`。
- 不把 `messages` 升级为 token 级事件源。
- 不把 `checkpoint` 直接暴露为前端产品态 API。

---

## 2. 三事实源职责契约

| 存储面 | 主责（owns） | 非主责（does_not_own） | 主要读写入口 |
|---|---|---|---|
| `checkpoint` | LangGraph 运行时 continuation、pending interrupt、可续跑 message state | 用户可见历史、审计回放语义 | `app/agents/runtime/native_checkpoint.py`、`native_agent_runner.py` |
| `run_events` | SSE 事件 append-only transcript，用于 replay / audit / 诊断 | 运行时 continuation、最终会话历史 | `RunEventRepository`、`RunEventPlaybackService`、`RunStreamPersistenceService` |
| `messages` | 用户可见问答历史（已脱敏），含可展示 trace 摘要 | 原始流事件、checkpoint continuation、原始 CoT | `ConversationMemoryService.persist_run_messages`、`MessageRepository` |

### 2.1 读优先级（Read Precedence）
1. **续跑与中断恢复**：先读 `checkpoint`。
2. **断线回放（SSE replay）**：读 `run_events`（可按 `after_event_id` 增量切片）。
3. **会话历史展示**：读 `messages`。
4. **冲突时优先级**：
   - 运行控制问题：`checkpoint` > `run_events` > `messages`
   - 用户可见历史问题：`messages` > `run_events` > `checkpoint`

---

## 3. 写入时机契约（When to Write）

## 3.1 `checkpoint`
- 写入主体：LangGraph runtime（由 native runtime/checkpointer 管理）。
- 写入时机：图执行推进、节点推进、HITL pending/resume。
- 业务层约束：业务层不得把 checkpoint 当作“产品历史”直接下发给客户端。

### 3.2 `run_events`
- 写入主体：`ChatRunStreamService` + `RunStreamPersistenceService`。
- 写入时机：
  - `generation_delta` / `reasoning_delta`：允许批量缓冲后 append。
  - 非增量事件（trace/final_answer/hitl_resolved 等）：先 flush 缓冲，再单条 append。
  - `done` / `error`：必须与 run 状态更新在同一隔离事务中完成“终态落盘”。
  - `hitl_requested`：作为本轮终止事件落盘，run 状态保持可恢复语义（等待 resume）。

### 3.3 `messages`
- 写入主体：`NativeAgentRunner` 在 run 成功收敛后调用 `ConversationMemoryService.persist_run_messages`。
- 写入时机：仅在业务语义成功完成后写入 user/assistant 双 message。
- 写入内容：脱敏后的 query/answer + execution_trace 摘要；禁止写入原始 reasoning text。

---

## 4. 失败补偿契约（Compensation）

## 4.1 统一原则
- 允许“至少一次（at-least-once）事件持久化”，不允许破坏顺序语义。
- `run_events` 与 run 状态更新必须保证**最终可解释一致性**：
  - 若终态事件已持久化，则 run 状态必须最终收敛到对应终态。
  - 若 run 状态已终态但终态事件缺失，需触发修复任务（补事件或标记异常）。

### 4.2 典型失败与补偿动作
1. **流式中途 DB 短暂失败（写 `run_events` 失败）**
   - 动作：当前连接返回 `error` 事件（如可发送），run 置 `FAILED/INTERRUPTED`。
   - 补偿：依赖回放修复任务核对“终态事件↔run 状态”一致性。

2. **`done` 已生成但终态事务失败**
   - 动作：不得向客户端宣称成功完成（除非终态持久化成功）。
   - 补偿：下次读取 run 状态时按 `FAILED` 或待修复状态处理。

3. **`messages` 写入失败但 run 成功**
   - 动作：不回滚已完成 run（`run_events` 与 run 状态仍为 `SUCCESS`）。
   - 补偿：异步/重试写回消息；若多次失败，标记为“history lagging”告警。

4. **HITL resolve 后清理 pending_resume 失败**
   - 动作：run 可继续，但 shell_state 可能残留。
   - 补偿：成功继续执行后再次尝试 clear；后台巡检清理脏 pending_resume。

---

## 5. 行为一致性清单（重点组件）

> 覆盖：`chat_run_stream_service.py`、`native_agent_runner.py`、`run_stream_persistence_service.py`、`run_event_playback_service.py`、`chat_run_service.py`、`run_event_repo.py`、`conversation_memory_service.py`。

### 5.1 中断（interrupt）
- [ ] `ChatRunStreamService` 能通过 Redis 中断信号及时停止流并触发 `AGENT_INTERRUPTED` 终态。
- [ ] `RunStreamPersistenceService.persist_terminal_error` 将 `AGENT_INTERRUPTED` 映射为 `RunStatus.INTERRUPTED`。
- [ ] `native_agent_runner` 中断后不写 `messages`。
- [ ] `run_events` 至少包含可解释的 error 终态事件（含可恢复标识）。

### 5.2 重试（retry）
- [ ] `ChatRunService.retry_run` 仅允许 `FAILED/INTERRUPTED` 触发，并建立 parent/retry_of 关系。
- [ ] retry run 使用同一 conversation thread（checkpoint 维度按 conversation_id），行为可预期。
- [ ] retry 流程不篡改原 run 的 `run_events`，只向新 run 追加事件。
- [ ] 成功 retry 仅写入新 run 对应 `messages`。

### 5.3 重新生成（regenerate）
- [ ] `ChatRunService.regenerate_run` 仅允许 `SUCCESS` 触发，且不标记为 retry_of。
- [ ] regenerate run 视作新一次回答尝试，事件与消息均归属于新 run_id。
- [ ] 前端历史展示层基于 `messages` 展示“最新有效回答”，不混淆旧 run token 流。

### 5.4 HITL（请求/恢复）
- [ ] `hitl_requested` 必须落 `run_events`，并作为本轮流结束锚点。
- [ ] resume 前先读 pending interrupt / checkpoint，resume 时发出 `hitl_resolved` 事件。
- [ ] resolve 后应清理 shell_state.pending_resume_value（失败需补偿清理）。
- [ ] HITL 场景下 `messages` 仅在最终成功后写入，不在请求阶段落盘 assistant 最终答复。

### 5.5 断线回放（replay）
- [ ] 支持 `after_event_id` 增量回放；anchor 不存在时回退全量并标记 `anchor_found=false`。
- [ ] 回放顺序严格按 `(step, sequence_no)` 单调递增。
- [ ] 回放语义来源于 `run_events`，不得混读 checkpoint 直接拼接 SSE。
- [ ] replay 仅负责“事件重放”，最终历史仍以 `messages` 为准。

---

## 6. 契约级测试用例列表（先文档化）

> 命名建议：`app/tests/contracts/test_chat_run_three_truth_contract.py`（可按主题拆分）。

### 6.1 三事实源边界
1. **test_checkpoint_not_used_as_history_source**
   - 给定 checkpoint 有 messages、`messages` 表为空。
   - 读取会话历史 API 时不得回退到 checkpoint。

2. **test_run_events_not_used_as_canonical_messages**
   - 给定 run_events 有 final_answer，messages 中无 assistant。
   - 会话历史 API 不应直接使用 run_events 伪造 assistant history。

3. **test_messages_excludes_forbidden_reasoning_fields**
   - `persist_run_messages` 后 metadata 不包含原始 CoT/forbidden keys。

### 6.2 写入时机
4. **test_delta_events_buffered_then_flushed_before_non_delta**
   - delta 事件批量写，遇到 non-delta 前自动 flush，顺序不乱。

5. **test_done_event_and_success_status_are_atomically_persisted**
   - `done` 与 `RunStatus.SUCCESS` 同事务成功或同失败。

6. **test_error_event_maps_to_failed_or_interrupted**
   - `AGENT_INTERRUPTED` => `INTERRUPTED`；其他 error_code => `FAILED`。

7. **test_messages_written_only_after_successful_terminal**
   - 非 success 终态不写 messages。

### 6.3 中断 / 重试 / 重新生成
8. **test_interrupt_emits_terminal_error_and_no_messages_writeback**
9. **test_retry_allowed_only_for_failed_or_interrupted**
10. **test_regenerate_allowed_only_for_success**
11. **test_retry_and_regenerate_create_new_run_without_mutating_old_events**

### 6.4 HITL
12. **test_hitl_requested_persisted_and_stream_returns**
13. **test_resume_emits_hitl_resolved_and_clears_pending_resume**
14. **test_pending_resume_clear_failure_is_eventually_compensated**（可先标记 xfail / todo）

### 6.5 断线回放
15. **test_replay_after_event_id_returns_incremental_slice**
16. **test_replay_missing_anchor_falls_back_full_slice_with_flag**
17. **test_replay_order_is_step_then_sequence**

### 6.6 失败补偿
18. **test_terminal_status_event_invariant_detectable_by_repair_job**
19. **test_messages_writeback_failure_does_not_revert_run_success**
20. **test_repair_job_can_backfill_or_flag_missing_terminal_event**（可先文档 + todo）

---

## 7. 落地建议（实施顺序）

1. 先补 **契约测试骨架**（可包含 xfail/todo），固化术语与断言。
2. 再按测试修正 `chat_run_stream_service` / `native_agent_runner` 的边界行为。
3. 最后引入巡检/修复任务，覆盖终态一致性与 pending_resume 清理。

> 验收标准：新增功能或修复不得绕过上述契约测试；若必须偏离，需同步更新本契约文档与测试断言。
