# SPEC-04-question-bank-and-vectorization.md

## 1. 阶段目标
实现题库导入、题目 CRUD、题目与知识点多对多关系、题目向量化与脏数据重建。

## 2. 范围
- question_banks / questions / question_knowledge_points / question_vectors
- JSON/Excel 批量导入
- 题目 CRUD
- 题目与知识点关联维护
- 全局/批量向量化开关
- Celery 异步向量化
- 题目更新标记 dirty
- 增量重新向量化

## 3. API
- POST /api/v1/admin/questions/import
- GET /api/v1/admin/questions
- POST /api/v1/admin/questions
- PATCH /api/v1/admin/questions/{id}
- DELETE /api/v1/admin/questions/{id}
- POST /api/v1/admin/questions/vectorize
- GET /api/v1/admin/questions/vectorize-jobs/{id}

## 4. 设计要求
- 题目量较少，可将关系数据与向量统一进 PostgreSQL
- question -> knowledge_point 为多对多
- 向量化开关要防并发重复执行
- 导入支持幂等去重策略（建议 external_id/hash）

## 5. 验收标准
- JSON/Excel 成功导入
- CRUD 可用
- 关联关系可维护
- 脏题目可增量重新向量化
- 批量向量化任务可观测
