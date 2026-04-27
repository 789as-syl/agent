# API Documentation - Current Route Map 2026-04-26

## Base information

- Public health routes: `/health`, `/ready`.
- User API prefix: `/api/v1`.
- Admin API prefix: `/api/v1/admin`.
- Authentication: Bearer access token plus refresh-token cookie flow.
- Source of truth: route declarations in `app/api/*.py` and app mounting in `app/main.py`.

This document records currently mounted routes. It does not promise future freeze stability.

## Auth

Source: `app/api/auth.py`, mounted at `/api/v1/auth`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Register user and issue token response. |
| POST | `/api/v1/auth/login` | Login and issue token response. |
| POST | `/api/v1/auth/refresh` | Refresh access token using refresh token body/cookie. |
| GET | `/api/v1/auth/me` | Return current authenticated user. |
| POST | `/api/v1/auth/logout` | Revoke/logout refresh token. |

## Conversations

Source: `app/api/conversations.py`, mounted at `/api/v1/conversations`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/conversations` | List current user's conversations. |
| POST | `/api/v1/conversations` | Create conversation. |
| GET | `/api/v1/conversations/{conversation_id}` | Get one conversation. |
| PATCH | `/api/v1/conversations/{conversation_id}` | Update conversation title. |
| DELETE | `/api/v1/conversations/{conversation_id}` | Soft-delete conversation. |
| GET | `/api/v1/conversations/{conversation_id}/messages` | List sanitized user-visible messages. |

Message history is backed by `messages`, not by LangGraph checkpoint or raw `run_events`.

## Chat runs and Trace/SSE

Source: `app/api/chat_runs.py`, mounted at `/api/v1/conversations`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/conversations/{conversation_id}/runs` | Create a run for a query. |
| GET | `/api/v1/conversations/{conversation_id}/runs/{run_id}` | Get run status and resumable runtime state. |
| GET | `/api/v1/conversations/{conversation_id}/runs/{run_id}/events` | Return persisted run-event playback slice. |
| GET | `/api/v1/conversations/{conversation_id}/runs/{run_id}/stream` | Live SSE stream; supports `after_event_id` and `Last-Event-ID` replay. |
| POST | `/api/v1/conversations/{conversation_id}/runs/{run_id}/interrupt` | Interrupt an active run. |
| POST | `/api/v1/conversations/{conversation_id}/runs/{run_id}/retry` | Create retry run from an existing run. |
| POST | `/api/v1/conversations/{conversation_id}/runs/{run_id}/resume` | Resolve pending HITL decision. |
| POST | `/api/v1/conversations/{conversation_id}/runs/{run_id}/regenerate` | Create regenerate run from conversation history. |

Current `SSEEvent.event_type` values from `app/schemas/sse_event.py`:

- `execution_trace`
- `reasoning_delta`
- `hitl_requested`
- `hitl_resolved`
- `generation_delta`
- `final_answer`
- `error`
- `done`

Contract note:

- `run_events` owns replay/audit transcript.
- `messages` owns final user-visible conversation history.
- raw chain-of-thought and tool protocol payloads must not become durable message API contract.

## Admin ingestion / knowledge points

Source: `app/api/ingestion.py`, router prefix `/api/v1/admin`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/admin/uploads/presign` | Create MinIO presigned upload URL. |
| POST | `/api/v1/admin/uploads/callback` | Register upload completion and ingestion job. |
| GET | `/api/v1/admin/knowledge-points` | List knowledge points. |
| POST | `/api/v1/admin/knowledge-points` | Create knowledge point. |
| GET | `/api/v1/admin/knowledge-points/{kp_id}` | Get knowledge point. |
| PATCH | `/api/v1/admin/knowledge-points/{kp_id}` | Update knowledge point. |
| DELETE | `/api/v1/admin/knowledge-points/{kp_id}` | Delete knowledge point and associated artifacts/links. |
| GET | `/api/v1/admin/knowledge-points/{kp_id}/document-url` | Generate document download/preview URL. |
| POST | `/api/v1/admin/knowledge-points/{kp_id}/reindex` | Trigger reindex job. |
| GET | `/api/v1/admin/ingestion-jobs/{job_id}` | Get ingestion job. |
| POST | `/api/v1/admin/ingestion-jobs/{job_id}/retry` | Retry ingestion job. |

Docling/PDF support depends on runtime dependency readiness; `/ready` reports parser readiness.

## Admin question bank and vectorization

Source: `app/api/questions.py`, router prefix `/api/v1/admin`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/admin/question-banks` | List question banks. |
| POST | `/api/v1/admin/question-banks` | Create question bank. |
| PATCH | `/api/v1/admin/question-banks/{bank_id}` | Update question bank. |
| DELETE | `/api/v1/admin/question-banks/{bank_id}` | Delete question bank. |
| POST | `/api/v1/admin/questions` | Create question. |
| GET | `/api/v1/admin/questions` | List/filter questions. |
| GET | `/api/v1/admin/questions/{question_id}` | Get question. |
| PATCH | `/api/v1/admin/questions/{question_id}` | Update question. |
| DELETE | `/api/v1/admin/questions/{question_id}` | Delete question. |
| POST | `/api/v1/admin/questions/import` | Import questions from JSON or uploaded file payload. |
| POST | `/api/v1/admin/questions/vectorize` | Trigger vectorization. |
| GET | `/api/v1/admin/questions/vectorize-jobs/{job_id}` | Get vectorization job. |
| POST | `/api/v1/admin/questions/{question_id}/knowledge-points` | Link question to knowledge points. |
| DELETE | `/api/v1/admin/questions/{question_id}/knowledge-points/{knowledge_point_id}` | Remove question-KP link. |

## Admin analytics

Source: `app/api/admin_analytics.py`, router prefix `/api/v1/admin`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/admin/dashboard` | Dashboard metrics for selected range. |
| GET | `/api/v1/admin/knowledge-graph` | Knowledge graph data with range/node options. |

## Admin users and conversation audit

Source: `app/api/admin_users.py`, router prefix `/api/v1/admin`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/admin/users` | List users with paging/search/status filters. |
| GET | `/api/v1/admin/users/{user_id}` | Get user detail. |
| PATCH | `/api/v1/admin/users/{user_id}/status` | Enable/disable user. |
| GET | `/api/v1/admin/users/{user_id}/conversations` | List selected user's conversations. |
| GET | `/api/v1/admin/users/{user_id}/conversations/{conversation_id}/messages` | Read-only message audit for selected conversation. |

## Health and readiness

Source: `app/api/health.py`, mounted without `/api/v1` prefix.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness probe. |
| GET | `/ready` | Readiness probe for DB/Redis/MinIO/Celery/parser runtime. |

## Validation commands

```powershell
python -m ruff check app scripts
python -m mypy app
pytest app/tests/test_api_chat_runs.py app/tests/test_unit_trace_consistency.py app/tests/test_unit_agent_trace_contract.py -q
```

See `docs/validation-matrix-2026-04-26.md` for full command scope and environment requirements.
