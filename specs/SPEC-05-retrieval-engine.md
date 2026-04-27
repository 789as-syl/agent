# SPEC-05-retrieval-engine.md

## 1. 阶段目标
构建核心检索工具链：query 重构、知识点/题目双库并行检索、题目映射知识点、加权融合、rerank、缓存、日志。

## 2. 范围
- query rewrite：原句 -> 陈述句 + 疑问句
- 三路查询：原句/陈述/疑问
- 双库并行：knowledge_point_chunks + question_vectors
- 相似度阈值过滤
- question -> knowledge_point 映射
- 多路得分融合
- DashScope rerank
- TopK 输出
- RetrievalLog 记录
- Redis 缓存 rewrite 与高频检索结果

## 3. 核心流程
1. 接收原始 query
2. 生成 statement / question rewrite
3. 并发查询知识点库与题目库
4. 过滤低分结果
5. 将题目命中映射到知识点
6. 对直接命中的知识点与映射知识点做加权融合
7. 排序取 TopN
8. 对候选知识点内容做 rerank
9. 输出最终知识点列表与检索解释

## 4. 配置项
- similarity_threshold
- top_k_before_rerank
- top_k_after_rerank
- weights.original
- weights.statement
- weights.question
- weights.direct_hit
- weights.question_mapping

## 5. API / Service
本阶段优先实现 service，不急于公开给前端。
建议内部接口：
- RetrievalService.retrieve(query, user_id, conversation_id, config)

## 6. 验收标准
- 检索链路可独立调用
- 关键权重可配置
- 有单元测试覆盖融合逻辑
- 有集成测试覆盖完整检索流程
- RetrievalLog 可审计
- 缓存命中/失效机制明确
