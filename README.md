# Knowledge Base Agent

知识库 RAG / Agent 系统，包含 FastAPI 后端、用户端 Vite React 应用、管理员端 Vite React 应用，以及 PostgreSQL/pgvector、Redis、MinIO、Celery、LangGraph checkpoint 等本地与部署样例依赖。

> 当前 README 反映 2026-04-27 全平台修复后的实际代码状态。完整边界与验收标准以 `.omx/plans/prd-full-platform-remediation-20260426.md` 和 `.omx/plans/test-spec-full-platform-remediation-20260426.md` 为准。

## 当前能力概览

- 用户认证与会话：注册、登录、刷新、登出、当前用户查询。
- 用户端：会话列表、消息历史、Agent Chat 流式输出、SSE 断线回放、HITL resume、retry/regenerate 入口。
- 用户学习闭环：练习会话、错题本、掌握度、复习卡片、学习路径 MVP、回答反馈。
- 管理端：知识点/文档入库、题库/题库向量化、用户管理、用户会话只读审阅、Dashboard、知识图谱、运维与质量中心、Trace Lab、RAG Eval Lab、审计日志。
- RAG/文档：文档解析、预览、切片、向量化、检索、重排/融合、题库证据接入、质量雷达与任务控制台。
- Agent/Trace：LangGraph 原生运行时、Postgres checkpoint、`run_events` 持久回放、`messages` 用户可见历史写回、脱敏 trace 投影、证据卡片、管理员重放视图。
- 部署样例：本地 full-stack compose、production-shaped compose sample、前后端 Dockerfile、Nginx gateway 模板。

## 关键文档入口

- 当前架构：`docs/current-architecture-2026-04-26.md`
- API 路由：`docs/API_DOCUMENTATION.md`
- Agent/RAG/Trace 契约：`docs/agent-rag-trace-contract-2026-04-26.md`
- 部署说明：`docs/deployment-stack-2026-04-27.md`
- SPEC 状态矩阵：`docs/spec-status-matrix-2026-04-26.md`
- 验证矩阵：`docs/validation-matrix-2026-04-26.md`
- 本轮修复 PRD：`.omx/plans/prd-full-platform-remediation-20260426.md`
- 本轮测试规格：`.omx/plans/test-spec-full-platform-remediation-20260426.md`

## 技术栈

### Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0 async
- Alembic
- PostgreSQL 16 + pgvector
- Redis
- MinIO
- Celery
- DashScope
- LangChain / LangGraph / LangGraph checkpoint Postgres
- Docling / pypdf / BeautifulSoup 文档解析链路

### Frontend

- `front/client`: Vite + React + TypeScript + Zustand + React Router
- `front/admin`: Vite + React + TypeScript + Ant Design + TanStack Query + ECharts

## 本地开发

### 1. 启动依赖服务

```powershell
docker compose up -d
docker compose ps
```

### 2. 创建 Python 环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
```

关键变量：

- `DATABASE_URL`
- `TEST_DATABASE_URL`，运行 pytest 时必须指向专用测试库，不能指向主库
- `REDIS_URL`
- `MINIO_*`
- `DASHSCOPE_API_KEY`
- `AGENT_CHECKPOINT_DATABASE_URL`，未设置时默认使用 `DATABASE_URL`

### 4. 数据库迁移

```powershell
alembic upgrade head
```

### 5. 启动后端

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

接口文档：

- `http://localhost:8000/docs`
- `http://localhost:8000/health`
- `http://localhost:8000/ready`

### 6. 启动前端

```powershell
cd front/client
npm install
npm run dev
```

```powershell
cd front/admin
npm install
npm run dev
```

## Full-stack compose（新增）

### 本地全栈

```powershell
docker compose -f docker-compose.full.yml up -d --build
docker compose -f docker-compose.full.yml ps
```

访问入口：

- 用户端：`http://app.localtest.me:8080`
- 管理端：`http://admin.localtest.me:8080`
- 存储域名：`http://storage.localtest.me:8080`
- MinIO Console：`http://localhost:9001`

### Production-shaped sample

```powershell
docker compose --env-file deploy/.env.production.sample -f docker-compose.prod.sample.yml config
```

该文件是部署脚手架，不代表已完成真实生产验证。详细边界见 `docs/deployment-stack-2026-04-27.md`。

## 验证门槛

本仓库当前的最低验收不是“页面能打开”，而是后端、前端、迁移、Trace 和部署样例都有可复现验证。

```powershell
python -m ruff check app scripts
python -m mypy app
$env:TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@localhost:5432/knowledge_base_test'
.\.venv\Scripts\python.exe -m pytest app/tests -q
cd front/client; npm run typecheck; npm run test:trace; npm run build
cd front/admin; npm run typecheck; npm run build
docker compose ps
```

完整矩阵和环境依赖见：`docs/validation-matrix-2026-04-26.md` 与 `.omx/plans/test-spec-full-platform-remediation-20260426.md`。

### Ruff 策略

- 保留：`E`, `F`, `W`, `I`, `B`, `RUF`。
- 忽略：`RUF001/RUF002/RUF003`，因为中文产品文案与注释会正常使用全角标点。
- 忽略：`E501`，由 Black 与人工 review 管控；当前长 SQL、HTML/CSS 字符串和中文文本不适合作为硬阻断。

### Mypy 策略

- `python -m mypy app` 是生产代码信号。
- `app/tests` 暂不进入生产 mypy gate，避免 mock/test fixture 噪音遮蔽真实生产错误。
- 第三方无 stub 包通过集中 override 处理，不在业务代码中散落动态 ignore。

## Agent/Trace 三类真相源

| 真相源 | 负责 | 不负责 |
|---|---|---|
| LangGraph checkpoint | 运行时续跑、pending interrupt、图状态消息 | 用户可见历史、审计回放、产品 transcript |
| `run_events` | append-only SSE 回放、审计、retry/HITL 诊断 | runtime continuation、最终用户历史语义 |
| `messages` | 用户可见对话历史、净化后的答案和 trace summary | 原始事件流、checkpoint 状态、raw CoT |

更详细契约见：`docs/agent-rag-trace-contract-2026-04-26.md`。

## 项目结构

```text
app/
  api/             FastAPI routers
  agents/          LangGraph/native Agent runtime
  core/            settings, middleware, Redis, MinIO, security, schema guard
  models/          SQLAlchemy entities
  repositories/    data access layer
  schemas/         Pydantic DTOs
  services/        business/domain services
  tasks/           Celery tasks
  tests/           pytest tests
alembic/           migrations
front/client/      user frontend
front/admin/       admin frontend
docs/              current docs, reports, review artifacts
specs/             original staged specs
```

## 明确边界

当前仍然明确排除：

- 完整 RBAC / 多租户 / 组织空间模型；
- 原始 chain-of-thought、provider payload、tool protocol 在 API/UI/Trace 中透出；
- 未经真实基础设施验证就宣称“生产已验证”；
- production-grade `web_search` provider overhaul；
- 大范围纯视觉重设计。

## License

内部项目。
