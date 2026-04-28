# Validation Matrix - 2026-04-27

This matrix is the current hard gate for the full-platform remediation slice. It intentionally separates hard gates, scoped gates, and environment-dependent gates so failures remain actionable.

## Static checks

| Lane | Command | Required when | Expected result | Notes |
|---|---|---|---|---|
| Backend lint | `python -m ruff check app scripts` | Always | Pass | Ruff enforces `E/F/W/I/B/RUF`, excluding CJK punctuation noise (`RUF001/RUF002/RUF003`) and E501 line-length noise. |
| Backend typing | `python -m mypy app` | Always | Pass for production code | `app/tests` is excluded by config; third-party stub gaps are centralized in `pyproject.toml`. |
| Black format check | `python -m black --check app scripts` | Before release or broad Python formatting work | Pass or documented deferred | Not the primary P0 gate for this slice; Ruff/Black must not be mixed with broad unrelated churn. |

## Backend tests

| Lane | Command | Required when | Expected result | Notes |
|---|---|---|---|---|
| B1 contract unit | `pytest app/tests/test_unit_agent_trace_contract.py -q` | Always after B1 changes | Pass | Does not require DB if pytest environment can import app dependencies. |
| Chat/Trace targeted | `pytest app/tests/test_api_chat_runs.py app/tests/test_unit_trace_consistency.py -q` | Agent/Trace API/runtime touched | Pass, or environment blocker documented | Requires declared Python runtime deps and `TEST_DATABASE_URL` pointing to a dedicated test DB. |
| Playback service | `pytest app/tests/test_unit_run_event_playback_service.py -q` | Replay ordering/slice behavior touched | Pass | Covers append-only replay ordering and legacy event payload validation. |
| Message/history API | `pytest app/tests/test_api_conversations.py -q` | Message serialization/history touched | Pass | Covers sanitized content blocks and legacy trace fallback behavior. |
| Full backend suite | `pytest app/tests -q` | Release candidate or broad backend changes | Pass or environment-dependent blocker documented | Must never run against primary `DATABASE_URL`; use `TEST_DATABASE_URL`. |

## Frontend checks

| Lane | Command | Required when | Expected result | Notes |
|---|---|---|---|---|
| Client typecheck | `cd front/client; npm run typecheck` | Client touched or release check | Pass | Review report said this previously passed; refresh after client edits. |
| Client build | `cd front/client; npm run build` | Client touched or release check | Pass | May be slower; run before final release handoff. |
| Client trace tests | `cd front/client; npm run test:trace` | Stream/replay/HITL/client trace touched | Pass | Required for ChatPage or streaming-session changes. |
| Admin typecheck | `cd front/admin; npm run typecheck` | Admin touched or release check | Pass | Review report said this previously passed. |
| Admin build | `cd front/admin; npm run build` | Admin touched or release check | Pass | Required before UI release. |

## Runtime and integration checks

| Lane | Command | Required when | Expected result | Notes |
|---|---|---|---|---|
| Local services | `docker compose ps` | Running API/integration tests locally | DB/Redis/MinIO healthy | Existing infra compose remains the fastest dependency bootstrap. |
| Migrations | `alembic upgrade head` | DB schema changed or fresh environment | Pass | No destructive migration without explicit approval. |
| Test DB migration | `alembic -c alembic.test.ini upgrade head` or documented equivalent | Running DB-backed pytest | Pass | Use dedicated test DB. |
| Health/readiness | `curl http://localhost:8000/health`, `curl http://localhost:8000/ready` | Backend server started | Health ok; readiness reports dependency status | Parser readiness may be degraded if Docling/PDF deps missing. |
| Full-stack compose config | `docker compose -f docker-compose.full.yml config` | Deployment artifacts changed | Pass | Verifies local full-stack compose syntax. |
| Production sample compose config | `docker compose --env-file deploy/.env.production.sample -f docker-compose.prod.sample.yml config` | Deployment artifacts changed | Pass | Validates sample deployment YAML and placeholder wiring; not a production rollout proof. |
| RAG/parser golden checks | Existing parser/retrieval unit tests or future golden set | RAG/document slice selected | Pass | Representative retrieval/eval paths are now part of the broader V1 remediation. |

## Ruff policy

Current hard gate is:

```powershell
python -m ruff check app scripts
```

Configuration intent:

- Keep correctness and maintainability signal: `F`, `I`, `W`, selected `E`, `B`, `RUF`.
- Exclude CJK punctuation ambiguity rules because Chinese comments/product copy intentionally use full-width punctuation.
- Exclude E501 because current long SQL strings, HTML/CSS literals, and CJK prose make it noisy; Black remains the formatter.
- Do not disable all linting and do not use mass unrelated formatting to hide root-cause issues.

## Mypy policy

Current hard gate is:

```powershell
python -m mypy app
```

Configuration intent:

- Production code is the first useful signal.
- `app/tests` is excluded from the production gate so mock/fixture noise does not hide real production issues.
- Third-party import gaps are centralized in `pyproject.toml` overrides (`docling`, `docling_core`, `dashscope`, `langchain`, `minio`, `pgvector`, `pypdf`, `psycopg`, `psycopg_pool`, `redis`, etc.).
- If test typing is added later, it should be a separate command/gate rather than weakening the production gate.

## Agent/Trace pass criteria

B1 passes only if all of the following are true:

1. Three-truth source contract is documented:
   - checkpoint = runtime continuation;
   - `run_events` = append-only replay/audit transcript;
   - `messages` = sanitized user-visible history.
2. Normalized replay equivalence ignores volatile identifiers:
   - `event_id`;
   - `timestamp`;
   - generated `step_id` / equivalent runtime IDs.
3. Replay equivalence preserves semantic content:
   - event ordering where relevant;
   - terminal state;
   - final answer;
   - HITL requested/resolved semantics;
   - visible trace summary.
4. Durable history rejects raw CoT and protocol leaks:
   - no `raw_reasoning` / `chain_of_thought` as message API contract;
   - no tool `payload`, `protocol_version`, `protocol_path`, provider response, or raw error protocol in visible history.

Executable B1 unit tests:

```powershell
pytest app/tests/test_unit_agent_trace_contract.py -q
```

## Boundary checks

Before final handoff, review changed files and dependency manifests:

- No multi-tenant/org/full RBAC.
- No raw chain-of-thought / provider payload / tool protocol exposure.
- No production-grade `web_search` overhaul.
- No broad visual redesign.
- No false claim that sample deployment equals real production verification.

## Final report evidence checklist

Any execution final report must include:

1. Changed files.
2. Completed PRD milestones.
3. Commands run with exact pass/fail outputs.
4. Commands not run and why.
5. Whether P0 hard gate passed.
6. Whether B1 tests passed.
7. Whether optional B2 was attempted.
8. API/DB/UI behavior changes, if any.
9. Confirmation that non-goals were not violated.
10. Remaining risks and next recommended slice.
