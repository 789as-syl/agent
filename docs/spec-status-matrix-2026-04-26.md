# SPEC Status Matrix - 2026-04-27

This matrix reconciles `specs/SPEC-*.md` with current implementation evidence after the full-platform remediation slice. Statuses are intentionally conservative.

| SPEC | Status | Current evidence | Gaps / next slice |
|---|---|---|---|
| SPEC-01 Foundation | Complete / maintained | FastAPI app factory/lifespan, DB/Redis/MinIO startup, health/readiness, middleware, Alembic, pytest base exist. | Keep validation matrix current. |
| SPEC-02 Auth & Session | Mostly complete | `app/api/auth.py`, token service, JWT dependencies, user status checks, admin user management, admin-only surfaces. | Full RBAC/multitenancy is still excluded. |
| SPEC-03 Ingestion & Knowledge Base | Implemented V1 / still hotspot internally | Admin upload/callback, knowledge-point CRUD, MinIO, Celery ingestion, Docling parsing/preview/chunking, reindex, global ingestion console, quality radar warnings. | `document_processing.py` remains a large module and can still be split further later. |
| SPEC-04 Question Bank & Vectorization | Implemented V1 | Question banks/questions CRUD, import, dirty flag, vectorization jobs, question-KP links, question-bank retrieval integration, vectorization console/retry. | More sophisticated question quality analytics can be added later. |
| SPEC-05 Retrieval Engine | Implemented V1 with explicit follow-up lane | Retrieval services, embedding/rerank/fusion/vector search, retrieval cache invalidation, question-bank evidence, no-raw-payload result sanitation, RAG Eval Lab primitives. | Production-grade external web-search provider strategy remains deferred. |
| SPEC-06 Agent & Trace | Implemented V1.5 | Native LangGraph runtime, Postgres checkpoint, chat runs, SSE stream, run_events playback, HITL, retry/regenerate, message writeback, redacted admin trace lab, evidence projection. | Further runner decomposition can continue later without changing current contract. |
| SPEC-07 API Freeze for Frontend | Managed internal contract | Shared frontend API factories/types, route/schema tests, learning/admin/feedback contracts, migration-backed additions. | Still not a public backwards-compatibility promise. |
| SPEC-08 Frontend Integration | Implemented V1 | Client chat evidence panel, feedback controls, learning center, admin operations center, trace lab, RAG Eval Lab, audit log page, typecheck/build gates. | Broad visual redesign remains out of scope. |
| SPEC-09 Deployment | Local full-stack + production-shaped sample | `docker-compose.yml` infra compose, `docker-compose.full.yml`, `docker-compose.prod.sample.yml`, backend/frontend Dockerfiles, Nginx gateway template, env samples, deployment notes. | Real TLS / DNS / secret-manager / cloud rollout still requires environment-specific execution. |

## Current P0 gate relationship

- Ruff and mypy are configured as useful hard gates in `pyproject.toml`.
- Validation matrix lives at `docs/validation-matrix-2026-04-26.md`.
- Current architecture lives at `docs/current-architecture-2026-04-26.md`.
- Agent/RAG/Trace contract lives at `docs/agent-rag-trace-contract-2026-04-26.md`.

## Still-deferred roadmap candidates

1. Multi-tenant/org/full RBAC.
2. Production-grade `web_search` overhaul.
3. Real TLS / cert automation / secret manager rollout.
4. Broad frontend visual redesign.
5. Additional internal modularization of remaining hotspots (`document_processing.py`, `native_agent_runner.py`, large pages) beyond the current verified seams.
