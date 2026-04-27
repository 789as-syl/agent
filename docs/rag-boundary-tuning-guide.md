# RAG Boundary Evaluation Guide (Three-Tool Surface)

本指南用于评估三工具策略下的意图边界：

- `knowledge_retrieval`（创新创业领域默认检索优先）
- `math_calculator`（确定性数值计算）
- guidance short-circuit（闲聊 / 非领域问题引导）

---

## 1) 运行离线边界评估

```bash
python scripts/evaluate_rag_boundary.py ^
  --fixture app/tests/fixtures/rag_boundary_eval_cases.json ^
  --output-json docs/rag-boundary-eval-report.json ^
  --show-cases
```

可叠加本地误判样本：

```bash
python scripts/evaluate_rag_boundary.py ^
  --fixture app/tests/fixtures/rag_boundary_eval_cases.json ^
  --extra-fixture app/tests/fixtures/rag_boundary_eval_cases.local.json ^
  --output-json docs/rag-boundary-eval-report.json
```

---

## 2) 样本格式

主 fixture：

- `app/tests/fixtures/rag_boundary_eval_cases.json`

本地扩展样本建议：

- `app/tests/fixtures/rag_boundary_eval_cases.local.json`
- `app/tests/fixtures/rag_boundary_eval_cases.local.sample.json`

单条样本结构：

```json
{
  "id": "real_case_001",
  "category": "innovation_domain",
  "query": "老师在课上怎么定义MVP？",
  "history": [],
  "expected_use_kb": true
}
```

---

## 3) 结果解读

重点关注：

- `Precision`
- `Recall`
- `false_positive`
- `false_negative`
- `Per-category`

当前策略目标：

1. 闲聊/非领域问题尽量在前置意图层被 short-circuit。
2. 创新创业领域问题默认 `knowledge_retrieval`。
3. 数学确定性请求走 `math_calculator`。

当前建议质量门（固定 fixture）：

- Precision >= 0.80
- Recall >= 0.80
- Accuracy >= 0.80

---

## 4) 说明

旧的 probe / rewrite 预处理链路已整体下线；当前仅保留三工具边界评估。
