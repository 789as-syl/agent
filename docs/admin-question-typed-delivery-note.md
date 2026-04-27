# 管理端题库按题型统一改造交付说明

交付日期：
- 2026-04-14

---

## 1. 本次交付目标

将以下三条主链路统一到同一套题型规则：

- 新建题目
- 编辑题目
- 批量导入

并补齐知识图谱中的题目编辑入口，保证其与题库管理页使用相同规则，而不是保留一套旧的独立编辑逻辑。

---

## 2. 已完成范围

### 后端
- 增加统一规则层，对题目 payload 做归一化与严格校验
- schema 收紧为 canonical 模型
- 导入改为严格按新模板处理
- JSON / Excel 导入支持 partial success
- 保留 dirty 规则：仅 `question_text` 变化时置脏

### 前端
- 新建题目按题型动态展示与校验
- 编辑题目按题型动态展示与校验
- 批量导入与后端严格模板对齐
- 知识图谱页中的题目编辑入口已同步到同一套规则

### 文档
- 导入模板说明
- 手工验收清单
- 合法导入示例
- 混合合法/非法导入示例

---

## 3. 当前题型规则

仅支持四种题型：

- `single`
- `multiple`
- `true_false`
- `short_answer`

规则摘要：

### `single`
- 仅支持 A/B/C/D
- 至少两个选项
- 答案为单个字母

### `multiple`
- 仅支持 A/B/C/D
- 至少两个选项
- 至少两个答案
- 入库格式如 `A,C`

### `true_false`
- 不允许 options
- 入库值固定为 `true/false`

### `short_answer`
- 不允许 options
- 答案为文本

---

## 4. 严格兼容策略

本轮明确采用严格校验，不做旧格式宽松兼容。

以下格式会失败：

- `single_choice`
- `multiple_choice`
- `options: string[]`
- 判断题/简答题带 options
- 多选只填一个答案

---

## 5. 导入策略

导入失败策略：

- 非法行跳过
- 合法行继续
- 返回 `created / updated / skipped / failed / errors`

适用渠道：

- JSON body
- form-data + `json_data`
- 上传 `.json`
- 上传 `.xlsx`

---

## 6. 关键文件

### 后端
- `app/services/question_rules.py`
- `app/schemas/question.py`
- `app/services/question_service.py`
- `app/repositories/question_repo.py`
- `app/api/questions.py`

### 前端
- `front/shared/types/question.ts`
- `front/admin/src/components/questions/questionEditorUtils.ts`
- `front/admin/src/components/questions/QuestionEditorModal.tsx`
- `front/admin/src/pages/QuestionManagementPage.tsx`
- `front/admin/src/components/NodeDetailModal.tsx`
- `front/admin/src/pages/KnowledgeGraphPage.tsx`
- `front/admin/src/hooks/useQuestionManagementActions.ts`

### 文档
- `docs/admin-question-import-template.md`
- `docs/admin-question-typed-acceptance-checklist.md`
- `docs/examples/admin-question-import-sample.json`
- `docs/examples/admin-question-import-mixed-invalid.json`
- `docs/examples/admin-question-import-sample.xlsx`

---

## 7. 验证结果

### 后端
- `pytest app/tests/test_unit_question_rules.py app/tests/test_question_dirty_rule.py app/tests/test_api_questions.py app/tests/test_e2e_workflows.py`
- 结果：`37 passed`

### 类型检查
- `mypy app/api/questions.py app/services/question_service.py app/repositories/question_repo.py app/schemas/question.py`
- 结果：通过

### 前端
- `npm run typecheck`
- `npm run lint`
- `npm run build`
- 结果：通过

---

## 8. 交付产物给联调/测试的使用建议

建议使用以下文件直接开始验证：

- 模板说明：`docs/admin-question-import-template.md`
- 手工验收：`docs/admin-question-typed-acceptance-checklist.md`
- 合法样例：`docs/examples/admin-question-import-sample.json`
- Excel 合法样例：`docs/examples/admin-question-import-sample.xlsx`
- 混合失败样例：`docs/examples/admin-question-import-mixed-invalid.json`

---

## 9. 已知未处理项

- 尚未执行浏览器手工 smoke
- 仓库仍存在 questions 之外的 mypy 历史基线问题，未纳入本轮

---

## 10. 建议下一步

优先顺序建议：

1. 管理端浏览器手工 smoke
2. 让测试/产品按验收清单执行一次完整联调
3. 若稳定，再处理仓库其他模块的 mypy 历史债务
