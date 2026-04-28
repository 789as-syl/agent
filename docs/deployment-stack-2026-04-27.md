# Deployment Stack Notes - 2026-04-27

This document describes the deployment artifacts added during the full-platform remediation slice. It is intentionally honest:

- `docker-compose.full.yml` is a **local full-stack compose** for API + worker + two frontends + Postgres + Redis + MinIO.
- `docker-compose.prod.sample.yml` is a **production-shaped sample**. It is configuration scaffolding, not proof of a real production rollout.
- No real TLS certificate, domain ownership, cloud firewall, or secret manager was verified in this workspace.

## 1. Local full-stack compose

File: `docker-compose.full.yml`

### What it starts

- `postgres`
- `redis`
- `minio`
- `api`
- `worker`
- `client-web`
- `admin-web`
- `gateway`

### Access model

The gateway is published on port `8080`. Use wildcard `localtest.me`, which resolves to `127.0.0.1` without editing the hosts file:

- User site: `http://app.localtest.me:8080`
- Admin site: `http://admin.localtest.me:8080`
- Storage endpoint for presigned upload/download: `http://storage.localtest.me:8080`
- FastAPI health/docs direct access: `http://localhost:8000/health`, `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

### Why the `localtest.me` gateway matters

The frontend uses relative `/api/v1` calls, and ingestion relies on browser-accessible MinIO presigned URLs. Using one published Nginx gateway lets the browser and the API container agree on:

- app domain
- admin domain
- storage domain

without adding a second MinIO public-endpoint setting just for local compose.

### Start / stop

```powershell
docker compose -f docker-compose.full.yml up -d --build
docker compose -f docker-compose.full.yml ps
docker compose -f docker-compose.full.yml down
```

## 2. Production-shaped sample compose

File: `docker-compose.prod.sample.yml`

Companion env sample: `deploy/.env.production.sample`

### Intended shape

- `app.example.com` -> user frontend through Nginx gateway
- `admin.example.com` -> admin frontend through Nginx gateway
- `storage.example.com` -> MinIO S3 API through the same gateway
- API and worker stay private on the Docker network
- Postgres / Redis / MinIO stay private on the Docker network

### What you must replace before real use

1. `POSTGRES_PASSWORD`
2. `MINIO_ROOT_PASSWORD`
3. `JWT_SECRET_KEY`
4. `PROD_*_DOMAIN`
5. `PROD_CORS_ORIGINS`
6. `DASHSCOPE_API_KEY`
7. any LangSmith keys if tracing is enabled

### Current boundary

The sample binds only port `80`. It does **not** claim TLS is finished. Before internet exposure you still need:

- HTTPS termination
- explicit firewall rules
- secure `MINIO_SECURE=true` once TLS is actually in place
- non-default secrets
- backup / restore strategy
- log shipping / monitoring

## 3. Readiness expectations

The API container executes `alembic upgrade head` before `uvicorn` starts. Readiness remains `http://<api-host>/ready`.

Healthy startup means:

- Postgres reachable
- Redis reachable
- MinIO reachable
- schema at head revision

## 4. Verification boundary used in this remediation

Verified locally in this workspace:

- compose YAML parses are expected to be checked with `docker compose ... config`
- existing local dependency stack health checked with `docker compose ps`
- backend/frontend gates still run outside the containerized path

Not verified locally in this workspace:

- image builds against a clean external registry cache
- HTTPS certificates
- public DNS
- cloud networking
- production traffic / load

