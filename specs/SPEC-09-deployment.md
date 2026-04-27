# SPEC-09-deployment.md

## 1. 阶段目标
完成本地一键启动与生产可部署基线，形成可复用的部署方案。

## 2. 范围
- Docker Compose 编排
- FastAPI / Celery Worker / Redis / PostgreSQL / MinIO / Nginx 装配
- 环境变量模板
- 健康检查
- 日志输出规范
- Nginx 反向代理与限流
- 数据卷持久化
- 备份与恢复说明
- 基础监控建议

## 3. 必须产出
- docker-compose.yml
- docker-compose.prod.yml（可选）
- .env.example
- ops/nginx.conf
- ops/deploy.md
- ops/backup-restore.md

## 4. 验收标准
- 新环境可按文档启动
- SSE 正常经过代理
- 上传与回调链路可用
- Worker 可独立扩容
- 核心数据可持久化
