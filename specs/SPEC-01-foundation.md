# SPEC-01-foundation.md

## 1. 阶段目标
搭建后端可持续开发的基础骨架，确保后续认证、知识库、检索、Agent、SSE 都能在统一工程规范下演进。

## 2. 范围
- 初始化 FastAPI 工程
- 建立 Settings 配置体系
- 接入 PostgreSQL / pgvector / Redis / MinIO / Celery 的基础连接
- 建立 SQLAlchemy async session、基础 BaseModel、Alembic
- 建立统一日志、中间件、异常处理、健康检查
- 建立 pytest、lint、format、type-check 基础设施
- Docker Compose 本地基础环境可启动

## 3. 不在范围
- 业务接口
- JWT 登录
- 文档上传解析
- 检索与 Agent

## 4. 交付物
- 可运行 app/main.py
- /health, /ready 基础探针
- settings.py
- db/session.py
- celery_app.py
- logging.py
- docker-compose.yml
- alembic init + 首个迁移（启用 vector 扩展）
- CI 脚本或本地检查脚本

## 5. 关键设计
- 配置来源于 .env
- request_id 中间件自动注入日志上下文
- 统一异常格式：
  - error_code
  - message
  - details
  - request_id
- PostgreSQL 初始化包含 CREATE EXTENSION IF NOT EXISTS vector

## 6. 验收标准
- docker compose up 后 health 全绿
- FastAPI 能连通 PostgreSQL/Redis/MinIO（可用 mock readiness）
- Alembic upgrade head 成功
- pytest 基础样例通过
- Ruff/Black/mypy 可运行

## 7. 推荐任务拆分
1. 项目骨架与配置
2. DB/Redis/MinIO/Celery 装配
3. 日志/中间件/异常
4. Docker Compose 与迁移
5. 基础测试
