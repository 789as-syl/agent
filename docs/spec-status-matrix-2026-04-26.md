# SPEC Status Matrix - 2026-04-26

This matrix reconciles `specs/SPEC-*.md` with current implementation evidence. Statuses are intentionally conservative.

| SPEC | Status | Current evidence | Gaps / next slice |
|---|---|---|---|
| SPEC-01 Foundation | Complete / maintained | FastAPI app factory/lifespan, DB/Redis/MinIO startup, health/readiness, middleware, Alembic, pytest base exist. | Keep validation matrix current. |
| SPEC-02 Auth & Session | Mostly complete | `app/api/auth.py`, token service, JWT dependencies, user status checks, admin user management. | Full RBAC/multitenancy is not in scope; status/permission docs should stay explicit. |
| SPEC-03 Ingestion & Knowledge Base | Partial / advanced but still hotspot | Admin upload/callback, knowledge-point CRUD, MinIO, Celery ingestion, Docling parsing/preview/chunking, reindex. | `document_processing.py` needs future seam extraction; parser quality/golden checks remain future work. |
| SPEC-04 Question Bank & Vectorization | Partial / implemented core | Question banks/questions CRUD, import, dirty flag, vectorization jobs, question-KP links. | Question-bank retrieval integration and quality gates are future P1/RAG work. |
| SPEC-05 Retrieval Engine | Partial | Retrieval services, embedding/rerank/fusion/vector search, retrieval tool, result protocol sanitation. | Corpus version/cache invalidation, query rewrite visibility, golden retrieval evaluation deferred. |
| SPEC-06 Agent & Trace | Partial / active B1 focus | Native LangGraph runtime, Postgres checkpoint, chat runs, SSE stream, run_events playback, HITL, retry/regenerate, message writeback. | Three-truth contract and replay/no-raw-CoT tests are the current B1 deliverable; no broad runner extraction yet. |
| SPEC-07 API Freeze for Frontend | Partial | Current API surface exists and is documented in `docs/API_DOCUMENTATION.md`. | Not frozen as a public compatibility contract; changes require route/schema tests and documentation. |
| SPEC-08 Frontend Integration | Partial | `front/client` and `front/admin` apps exist; client trace test target exists. | ChatPage remains hotspot; evidence sidebar and broad UX redesign deferred. |
| SPEC-09 Deployment | Local-dev only / not production | `docker-compose.yml`, env example, local startup docs. | Production compose/Nginx/secret manager/full ops stack explicitly deferred. |

## Current P0 gate relationship

- Ruff and mypy are configured as useful hard gates in `pyproject.toml`.
- Validation matrix lives at `docs/validation-matrix-2026-04-26.md`.
- Current architecture lives at `docs/current-architecture-2026-04-26.md`.
- Agent/RAG/Trace contract lives at `docs/agent-rag-trace-contract-2026-04-26.md`.

## Deferred roadmap candidates

The following are intentionally not part of the first P0+B1 implementation slice:

1. Full learning loop, wrong-question book, mastery model, review cards, learning path.
2. Multi-tenant/org/full RBAC.
3. Full production deployment stack.
4. Production-grade `web_search` overhaul.
5. Broad frontend visual redesign.
6. Broad rewrites of `native_agent_runner.py`, `document_processing.py`, `ChatPage.tsx`, or admin pages.
7. New dependency/infrastructure without explicit approval.
8. Destructive irreversible data changes without explicit approval.
