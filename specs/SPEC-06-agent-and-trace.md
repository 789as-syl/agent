# SPEC-06-agent-and-trace.md

## 1. 阶段目标
实现基于 LangGraph 的 ReAct Agent，对接检索 Tool，并通过 SSE 输出全链路 Trace 与最终回答。

## 2. 范围
- AgentState 设计
- LangGraph StateGraph 编排
- retrieval tool 接入
- web search tool 预留接口
- conversation memory 读取
- 流式回答生成
- 统一 Trace 事件协议
- SSE 推送
- 中断 / 重试 / 断线重连 / 断点续传基础支持

## 3. 事件协议
建议统一字段：
- event_id
- request_id
- conversation_id
- event_type
- step
- timestamp
- trace_data
- is_final

建议 event_type 枚举：
- agent_thought
- tool_start
- tool_progress
- tool_result
- rerank_result
- generation_delta
- final_answer
- error
- done

## 4. API
- POST /api/v1/chat/conversations/{id}/runs
- GET /api/v1/chat/conversations/{id}/runs/{run_id}/stream
- POST /api/v1/chat/conversations/{id}/runs/{run_id}/retry
- POST /api/v1/chat/conversations/{id}/runs/{run_id}/interrupt

可选简化：
- POST /api/v1/chat/stream 直接返回 text/event-stream

## 5. 设计要求
- Agent 决策与工具执行必须结构化输出
- 检索超时可降级为纯模型回答
- run 记录可恢复
- SSE 支持 Last-Event-ID 恢复

## 6. 验收标准
- 前端可消费稳定 SSE
- Trace 与最终回答分离
- 检索工具调用过程可见
- 断线重连可继续
- 错误事件结构统一
