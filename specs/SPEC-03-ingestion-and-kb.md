# SPEC-03-ingestion-and-kb.md

## 1. 阶段目标
实现知识库文档上传、解析任务投递、知识点与向量切片落库、进度查询与失败重试。

## 2. 范围
- 管理端上传前签发 MinIO 预签名 URL
- 上传回调接口
- knowledge_points / knowledge_point_chunks / ingestion_jobs 表
- Celery 文档解析任务
- 基于 LlamaIndex 的文档读取/清洗/切分，Embedding 统一走 DashScope
- pgvector 入库
- 解析进度查询
- 失败重试
- 知识点编辑、向量刷新

## 3. 支持格式
- PDF
- Word
- MD
- TXT

## 4. API
- POST /api/v1/admin/uploads/presign
- POST /api/v1/admin/uploads/callback
- GET /api/v1/admin/knowledge-points
- POST /api/v1/admin/knowledge-points
- PATCH /api/v1/admin/knowledge-points/{id}
- DELETE /api/v1/admin/knowledge-points/{id}
- POST /api/v1/admin/knowledge-points/{id}/reindex
- GET /api/v1/admin/ingestion-jobs/{id}

## 5. 设计要求
- 每文档对应一个知识点
- chunk 与 knowledge_point 1:N
- ingestion_job 记录状态、进度、错误原因、对象路径
- 任务可重试
- reindex 重新生成 chunk + embedding，替换旧版本或版本化管理二选一，需明确
- 删除文档时必须同步清理 knowledge_point_chunks 向量、解除 ingestion_jobs 关联，并删除对象存储中的原始文件

## 6. 验收标准
- 文档可上传到 MinIO
- 回调后自动产生任务
- 任务完成后 chunk 与向量可查询
- 失败任务支持重试
- 进度轮询可见
- 至少覆盖 PDF/MD 两类文件测试
