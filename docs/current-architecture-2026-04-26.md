# Current Architecture Snapshot - 2026-04-26

This document records current implementation facts for the knowledge-base RAG/Agent system. It is not a roadmap promise.

## System shape

The repository is a brownfield quasi-product with three primary applications:

1. `app/`: FastAPI backend and background workers.
2. `front/client/`: user-facing chat frontend.
3. `front/admin/`: administrator console.

Local infrastructure is provided by `docker-compose.yml`:

- PostgreSQL 16 with pgvector.
- Redis for cache, Celery broker/result backend, interrupt signals, and SSE coordination.
- MinIO for uploaded files and generated preview artifacts.

## Backend module map

| Area | Main paths | Current responsibilities |
|---|---|---|
| API routes | `app/api/*.py` | Auth, conversations, chat runs, admin ingestion, admin questions, admin analytics, admin users, health/readiness. |
| Schemas | `app/schemas/*.py` | Pydantic v2 request/response DTOs. |
| Models | `app/models/*.py` | SQLAlchemy async ORM entities for users, conversations, messages, runs, events, ingestion, questions, vector jobs, retrieval logs. |
| Repositories | `app/repositories/*.py` | Data access and query ordering/pagination. |
| Services | `app/services/*.py` | Business workflows: auth, chat run lifecycle, stream persistence, playback, document processing, ingestion, retrieval, questions, admin analytics/users. |
| Agent runtime | `app/agents/*.py`, `app/agents/runtime/*.py` | LangGraph-native runtime, checkpoint access, DashScope streaming model adapter, memory writeback, trace projection helpers currently concentrated in `native_agent_runner.py`. |
| Tools | `app/tools/*.py` | Knowledge retrieval, web search, math, runtime context, result protocol sanitation. |
| Tasks | `app/tasks/*.py` | Celery ingestion/vectorization background work. |
| Tests | `app/tests/*.py` | API, service, unit, runtime, security, RAG/document boundary tests. |

## Frontend map

### User frontend: `front/client`

Current visible responsibilities:

- Auth pages: `LoginPage.tsx`, `RegisterPage.tsx`.
- Chat shell: `ChatPage.tsx`.
- Chat components: `front/client/src/pages/chat/components/*`.
- Stream/session logic: `front/client/src/pages/chat/streaming-session.ts`.
- Trace regression type/test entry: `front/client/src/pages/chat/streaming-session.trace.test.ts` via `npm run test:trace`.

`ChatPage.tsx` is still a hotspot. This slice does not authorize broad hook extraction or visual redesign.

### Admin frontend: `front/admin`

Current visible responsibilities:

- Login: `AdminLoginPage.tsx`.
- Dashboard: `DashboardPage.tsx`.
- Knowledge management: `KnowledgeManagementPage.tsx`.
- Question management: `QuestionManagementPage.tsx`.
- Knowledge graph: `KnowledgeGraphPage.tsx`.
- User account/session audit: `UserAccountManagementPage.tsx`, `UserSessionAuditPage.tsx`.

Admin task/quality MVP and full RBAC/multitenancy remain backlog, not first-slice implementation.

## API route map

All user APIs except `/health` and `/ready` are mounted under `/api/v1`.

| Area | Routes | Source |
|---|---|---|
| Health | `GET /health`, `GET /ready` | `app/api/health.py` |
| Auth | `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout` | `app/api/auth.py` |
| Conversations | `GET/POST /api/v1/conversations`, `GET/PATCH/DELETE /api/v1/conversations/{conversation_id}`, `GET /api/v1/conversations/{conversation_id}/messages` | `app/api/conversations.py` |
| Chat runs | `POST /api/v1/conversations/{conversation_id}/runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/events`, `GET /runs/{run_id}/stream`, `POST /interrupt`, `POST /retry`, `POST /resume`, `POST /regenerate` | `app/api/chat_runs.py` |
| Admin ingestion | `/api/v1/admin/uploads/*`, `/api/v1/admin/knowledge-points*`, `/api/v1/admin/ingestion-jobs*` | `app/api/ingestion.py` |
| Admin questions | `/api/v1/admin/question-banks*`, `/api/v1/admin/questions*`, vectorize jobs, question-KP links | `app/api/questions.py` |
| Admin analytics | `GET /api/v1/admin/dashboard`, `GET /api/v1/admin/knowledge-graph` | `app/api/admin_analytics.py` |
| Admin users | `GET /api/v1/admin/users`, `GET /api/v1/admin/users/{user_id}`, `PATCH /status`, conversations/messages audit | `app/api/admin_users.py` |

Detailed route table: `docs/API_DOCUMENTATION.md`.

## Agent/RAG runtime flow

1. User creates a conversation and chat run.
2. `ChatRunStreamService` validates run state and prepares streaming.
3. `NativeAgentRunner` invokes the LangGraph-native agent with a thread id tied to the conversation.
4. LangGraph checkpoint persists runtime continuation state through Postgres checkpointer.
5. Streaming emits `SSEEvent` objects for generation, reasoning summary/progress, trace, HITL, final answer, error, and done.
6. `RunStreamPersistenceService` persists emitted SSE events to `run_events` for replay/audit.
7. `ConversationMemoryService.persist_run_messages` writes sanitized user/assistant messages to `messages` once a run reaches terminal success.
8. Frontend rehydrates user-visible history from `messages` and can replay run transcript from `/events` or stream replay after `Last-Event-ID`.

## Three-truth source boundary

| Truth source | Owns | Does not own |
|---|---|---|
| LangGraph checkpoint | Runtime continuation state, pending interrupts, resumable graph messages. | User-visible durable history or audit transcript semantics. |
| `run_events` | Append-only transcript for SSE playback, audit, retry/HITL diagnosis. | Runtime continuation or canonical user history. |
| `messages` | Final visible conversation history and sanitized assistant answer/trace summaries. | Raw event streams, checkpoint continuation, raw chain-of-thought. |

The executable B1 helper for replay normalization/leak detection is `app/services/agent_trace_contract.py`; tests live in `app/tests/test_unit_agent_trace_contract.py`.

## Known hotspots and first-slice limits

| Hotspot | Current risk | First-slice boundary |
|---|---|---|
| `app/agents/native_agent_runner.py` | Many runtime, stream, trace, and memory responsibilities in one file. | No broad rewrite. B1 only adds contract tests/helpers. Optional later B2 may extract pure trace projection only after B1 passes. |
| `app/services/document_processing.py` | Parser/chunker/preview/quality concerns in one large service. | No split in this slice; only small type/lint fixes required by P0. |
| `front/client/src/pages/ChatPage.tsx` | Chat controller/UI responsibilities remain concentrated. | No hooks extraction or visual redesign in this slice. |
| Admin pages | Feature-rich pages with growing responsibility. | No admin task/quality platform in this slice. |

## Validation entry points

- Static lint: `python -m ruff check app scripts`.
- Production typing: `python -m mypy app`.
- B1 unit contract: `pytest app/tests/test_unit_agent_trace_contract.py -q`.
- Chat/Trace targeted backend: `pytest app/tests/test_api_chat_runs.py app/tests/test_unit_trace_consistency.py -q` when DB/test environment is available.
- Client trace: `cd front/client; npm run test:trace`.
- Client/Admin typecheck: `npm run typecheck` in each frontend app.

Full matrix: `docs/validation-matrix-2026-04-26.md`.
