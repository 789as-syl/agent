# Repository Guidelines

## Project Structure & Module Organization
This repository is a knowledge-base RAG/Agent system with a FastAPI backend and two Vite React frontends. Backend code lives in `app/`: `api/` for routes, `schemas/` for Pydantic DTOs, `models/` for SQLAlchemy entities, `repositories/` for data access, `services/` for business logic, `tasks/` for Celery jobs, `agents/` and `tools/` for LangGraph/runtime integrations, and `tests/` for pytest coverage. Database migrations are in `alembic/`, staged requirements are in `specs/`, docs and review artifacts are in `docs/`, examples live under `data_example/`, and frontend apps are split into `front/admin` and `front/client`.

## Build, Test, and Development Commands
- `docker compose up -d`: start PostgreSQL/pgvector, Redis, and MinIO for local development.
- `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev]"`: create a Windows PowerShell dev environment.
- `alembic upgrade head`: apply database migrations.
- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`: run the backend API locally.
- `pytest`: run backend tests from `app/tests` as configured in `pyproject.toml`.
- `ruff check .`, `black --check .`, `mypy app`: run linting, formatting checks, and strict typing.
- `cd front/admin; npm run dev|build|lint|typecheck` and the same in `front/client`; additionally use `npm run test:trace` in `front/client` for trace-stream tests.

## Coding Style & Naming Conventions
Use Python 3.12, Pydantic v2, SQLAlchemy 2.0 async patterns, and explicit FastAPI response models. Keep service/repository/task boundaries clear; avoid coupling retrieval logic to HTTP handlers. Ruff and Black use 120-character lines. Python modules and functions use `snake_case`; classes and Pydantic schemas use `PascalCase`; React components use `PascalCase`, hooks use `useXxx`, and shared frontend utilities stay close to their app unless genuinely reusable.

## Testing Guidelines
Prefer tests under `app/tests` named `test_*.py`; keep fixtures in `app/tests/fixtures` or `conftest.py`. Cover changed API contracts, services, async tasks, SSE/trace behavior, and migrations when touched. Use targeted runs such as `pytest app/tests/test_api_health.py -v` before broader `pytest`.

## Commit & Pull Request Guidelines
This checkout has no committed history to infer conventions from. Use intent-first commits: explain why the change exists, then add useful trailers such as `Tested: pytest app/tests/...` and `Not-tested: ...`. PRs should include scope, linked issue/spec, API or migration notes, verification output, and screenshots for frontend changes.

## Security & Configuration Tips
Copy `.env.example` to `.env`; do not commit secrets, tokens, MinIO credentials, or real DashScope keys. Keep external services configurable through Settings and document any new environment variable in `.env.example`.
