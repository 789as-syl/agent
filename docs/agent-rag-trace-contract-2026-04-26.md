# Agent / RAG / Trace Contract - 2026-04-26

This document is the B1 contract-first boundary for Agent/Trace and RAG flow. It defines current responsibilities and first-slice constraints; it is not a broad runtime rewrite plan.

## Current high-level flow

1. User calls `POST /api/v1/conversations/{conversation_id}/runs` with a query.
2. Backend creates a `chat_runs` row with pending/running state.
3. User calls `GET /api/v1/conversations/{conversation_id}/runs/{run_id}/stream`.
4. `ChatRunStreamService` validates ownership/status and prepares persistence/replay.
5. `NativeAgentRunner` invokes the LangGraph-native agent.
6. The runtime may call tools such as knowledge retrieval, web search, math, or runtime context.
7. Streamed `SSEEvent` objects are yielded to the client.
8. `RunStreamPersistenceService` persists emitted events to `run_events`.
9. On terminal success, `ConversationMemoryService.persist_run_messages` writes sanitized user/assistant messages to `messages`.
10. Frontend history reads from `/messages`; replay/audit reads from `/runs/{run_id}/events` or stream replay.

## Three truth sources

| Source | Owns | Does not own | Primary code paths |
|---|---|---|---|
| LangGraph checkpoint | Runtime continuation state, pending interrupts, graph message state needed to resume a conversation thread. | User-visible durable history, audit transcript, final chat-history semantics. | `app/agents/runtime/native_checkpoint.py`, `app/agents/native_agent_factory.py`, `app/agents/native_agent_runner.py` |
| `run_events` | Append-only transcript of emitted SSE events for playback, replay, audit, and retry/HITL debugging. | Runtime continuation and final user-visible conversation history. | `app/models/run_event.py`, `app/repositories/run_event_repo.py`, `app/services/run_event_playback_service.py`, `app/services/run_stream_persistence_service.py` |
| `messages` | Final user-visible conversation history and sanitized assistant answers/trace summaries. | Raw event stream, raw checkpoint state, raw chain-of-thought or tool protocol payload/provider response. | `app/models/message.py`, `app/repositories/message_repo.py`, `app/services/conversation_memory_service.py`, `app/api/conversations.py` |

Executable constants and helper functions live in `app/services/agent_trace_contract.py`.

## SSE event contract

Current event types are defined by `app/schemas/sse_event.py`:

- `execution_trace`
- `reasoning_delta`
- `hitl_requested`
- `hitl_resolved`
- `generation_delta`
- `final_answer`
- `error`
- `done`

Replay equivalence must ignore volatile transport/runtime fields:

- `event_id`
- `timestamp`
- generated `step_id`
- generated `generated_step_id`

Replay equivalence must preserve semantic fields:

- `request_id` and `conversation_id` when comparing events from the same run context;
- `event_type`;
- `step` ordering;
- terminal state (`done`, `error`, HITL interrupt equivalent);
- final answer text/content blocks;
- visible execution trace summary;
- HITL requested/resolved semantics.

`normalize_sse_event_for_replay()` in `app/services/agent_trace_contract.py` encodes the B1 volatile-field exclusion rule.

## Durable history redaction contract

`messages` and message-history APIs must not expose raw model reasoning or internal tool protocol envelopes as stable product contract.

Forbidden durable-history keys include:

- `raw_cot`
- `raw_chain_of_thought`
- `chain_of_thought`
- `raw_reasoning`
- `reasoning_content`
- `protocol_version`
- `protocol_path`
- `payload`
- `evidence_blocks`
- `error_code`
- `provider_response`
- `tool_call_payload`

`find_durable_history_contract_leaks()` in `app/services/agent_trace_contract.py` is a test helper for this boundary. The existing message serializer also sanitizes assistant content and content blocks through `app/api/conversations.py` and `app/agents/runtime/memory_writeback.py`.

## RAG contract in this slice

RAG is present but not the first implementation focus.

Current relevant paths:

- Retrieval orchestration: `app/services/retrieval/*`.
- Knowledge retrieval tool: `app/tools/retrieval_tool.py`.
- Tool result protocol sanitation: `app/tools/result_protocol.py`.
- Document parsing/chunking: `app/services/document_processing.py`.
- Question-bank vectorization: `app/services/question_service.py`, `app/tasks/vectorization_tasks.py`.

First-slice constraints:

- Do not introduce corpus-version cache invalidation in this slice.
- Do not implement question-bank retrieval expansion in this slice.
- Do not replace `web_search` or add external search providers.
- Do not split `document_processing.py` broadly.
- Preserve protocol sanitation: tool payloads are for runtime control, not user-facing message history.

Future RAG slice candidates:

1. Corpus version/truth signature in cache invalidation.
2. Query rewrite stage visibility.
3. Question-bank vector retrieval tests.
4. Golden retrieval set and quality report.

## HITL / retry / regenerate expectations

| Scenario | Contract expectation |
|---|---|
| HITL requested | Runtime checkpoint can resume; `run_events` records `hitl_requested`; `messages` is not finalized as a successful answer yet. |
| HITL resolved | Runtime consumes pending decision; `run_events` records `hitl_resolved`; stream/replay remains coherent. |
| Retry | Creates a new run transcript; does not corrupt the original `run_events` or unrelated messages. |
| Regenerate | Creates a new run from conversation context; final visible history is written through `messages` only on terminal success. |
| Refresh/reconnect | Frontend can hydrate user history from `messages` and replay transcript from `run_events` after an event id. |

## Tests

B1 contract tests:

```powershell
pytest app/tests/test_unit_agent_trace_contract.py -q
```

Related existing tests:

```powershell
pytest app/tests/test_unit_run_event_playback_service.py -q
pytest app/tests/test_api_conversations.py -q
pytest app/tests/test_api_chat_runs.py app/tests/test_unit_trace_consistency.py -q
cd front/client; npm run test:trace
```

## Optional B2 boundary

Only after B1 passes, a later optional B2 may extract pure trace projection logic. The first slice does not approve:

- stream adapter extraction;
- persistence layer extraction;
- HITL runtime redesign;
- native runtime replacement;
- `native_agent_runner.py` broad rewrite.
