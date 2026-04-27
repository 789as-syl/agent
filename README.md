# Knowledge Base Agent

知识库 RAG / Agent 系统，包含 FastAPI 后端、用户端 Vite React 应用、管理员端 Vite React 应用，以及 PostgreSQL/pgvector、Redis、MinIO、Celery、LangGraph checkpoint 等本地开发依赖。

> 当前 README 反映 2026-04-26 的实际代码状态。旧的“仅 Foundation 后端阶段”描述已不再准确；SPEC 状态以 `docs/spec-status-matrix-2026-04-26.md` 为准。

## 当前能力概览

- 用户认证与会话：注册、登录、刷新、登出、当前用户查询。
- 用户端：会话列表、消息历史、Agent Chat 流式输出、SSE 断线回放、HITL resume、retry/regenerate 入口。
- 管理端：知识点/文档入库、题库/题库向量化、用户管理、用户会话只读审阅、Dashboard 与知识图谱数据接口。
- RAG/文档：文档解析、预览、切片、向量化、检索、重排/融合相关服务；Docling/PDF 能力依赖运行时安装状态。
- Agent/Trace：LangGraph 原生运行时、Postgres checkpoint、`run_events` 持久回放、`messages` 用户可见历史写回。

## 关键文档入口

- 当前架构：`docs/current-architecture-2026-04-26.md`
- API 路由：`docs/API_DOCUMENTATION.md`
- Agent/RAG/Trace 契约：`docs/agent-rag-trace-contract-2026-04-26.md`
- SPEC 状态矩阵：`docs/spec-status-matrix-2026-04-26.md`
- 验证矩阵：`docs/validation-matrix-2026-04-26.md`
- 本轮修复 PRD：`.omx/plans/prd-global-architecture-repair-20260426.md`
- 本轮测试规格：`.omx/plans/test-spec-global-architecture-repair-20260426.md`

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

## P0 质量门槛

本仓库的 P0 gate 不是“关闭检查换取通过”，而是让检查重新产生有用信号。

```powershell
python -m ruff check app scripts
python -m mypy app
pytest app/tests/test_api_chat_runs.py app/tests/test_unit_trace_consistency.py app/tests/test_unit_agent_trace_contract.py -q
cd front/client; npm run typecheck; npm run test:trace
cd front/admin; npm run typecheck
```

完整矩阵和环境依赖见：`docs/validation-matrix-2026-04-26.md`。

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

## 明确非目标

本轮 P0+B1 修复不包含：

- full learning loop、错题本、掌握度模型、review cards、完整学习路径；
- 多租户、组织空间、full RBAC；
- 生产部署栈、Nginx、secret manager、完整运维平台；
- production-grade `web_search` 替换；
- 大范围 UI 视觉重设计；
- `native_agent_runner.py`、`document_processing.py`、`ChatPage.tsx` 或 admin 大页面的未验证大重写；
- 未批准的新依赖/新基础设施；
- 未批准的破坏性数据变更。

## License

内部项目。
