# 管理端题库按题型统一改造验收清单

适用版本：
- 新建题目
- 编辑题目
- 批量导入
- 知识图谱中的题目编辑入口

目标：
- 保证前端展示、表单校验、接口提交、后端入库规则一致
- 保证所有题型统一使用 canonical 字段模型

---

## 1. 本轮验收范围

必须验证：
- 题库管理页新建题目
- 题库管理页编辑题目
- 批量导入 JSON / Excel
- 知识图谱页题目编辑
- 后端严格校验
- 非法导入行跳过、合法行继续

不在本轮：
- 导出会话记录
- 复杂导入工作台
- 新题型扩展
- 题库领域模型大重构

---

## 2. 支持题型

仅支持：
- `single`
- `multiple`
- `true_false`
- `short_answer`

不再兼容：
- `single_choice`
- `multiple_choice`
- `options: string[]`

---

## 3. 验收前准备

建议准备：

1. 一个空题库
2. 一个带少量题目的题库
3. 若干知识点数据
4. 一份 JSON 导入文件
5. 一份 Excel 导入文件

导入模板说明见：
- `docs/admin-question-import-template.md`

---

## 4. 页面级手工验收清单

## 4.1 题库管理页 - 新建题目

### 单选题
- [ ] 选择题型为“单选题”时，页面展示 A/B/C/D 选项输入区
- [ ] A/B 至少需要填写，C/D 可选
- [ ] 若出现 A、C 有值但 B 为空，应阻止提交
- [ ] 答案只能从已填写选项中单选
- [ ] 提交后后端保存 `question_type=single`
- [ ] 提交后后端保存 `answer=A/B/C/D`

### 多选题
- [ ] 选择题型为“多选题”时，页面展示 A/B/C/D 选项输入区
- [ ] 至少勾选两个答案
- [ ] 提交后答案规范化为 `A,C` 这类格式
- [ ] 若勾选不存在的选项，不允许提交

### 判断题
- [ ] 选择题型为“判断题”时，不再展示 A/B/C/D 文本输入
- [ ] 页面只展示“对 / 错”选择
- [ ] 提交后后端保存为 `true` 或 `false`

### 简答题
- [ ] 选择题型为“简答题”时，不展示 A/B/C/D
- [ ] 页面展示文本答案输入框
- [ ] 空答案不可提交

### 通用项
- [ ] 解析字段可选
- [ ] 可正常绑定知识点
- [ ] 创建成功后列表展示答案格式正确

---

## 4.2 题库管理页 - 编辑题目

- [ ] 打开已存在单选题时，选项与答案回填正确
- [ ] 打开已存在多选题时，多选答案回填正确
- [ ] 打开已存在判断题时，只展示对/错回填
- [ ] 打开已存在简答题时，文本答案回填正确
- [ ] 题型切换时，旧题型无效字段被清理
- [ ] 从单选切到判断题后，旧 options 不应继续提交
- [ ] 从判断题切到简答题后，对/错值不应继续提交
- [ ] 编辑后列表展示正确

---

## 4.3 题库管理页 - 批量导入

### JSON 导入
- [ ] 合法 JSON 文件可成功导入
- [ ] 若部分题目非法，应返回部分成功结果
- [ ] 导入结果中展示 created / updated / skipped / failed
- [ ] 非法行错误信息可在前端 toast 中看到摘要

### Excel 导入
- [ ] 合法 Excel 模板可成功导入
- [ ] `single/multiple` 能正确读取 `option_a~option_d`
- [ ] `true_false/short_answer` 若填写 `option_a~d`，应判失败
- [ ] 非法行跳过、合法行继续

### 严格校验
- [ ] `single_choice` 导入失败
- [ ] `multiple_choice` 导入失败
- [ ] `options: ["A", "B"]` 这类字符串数组导入失败
- [ ] 多选答案只有一个字母时导入失败

---

## 4.4 知识图谱页 - 题目编辑

- [ ] 打开题目节点后，编辑区按当前题型正确展示
- [ ] 题型切换规则与题库管理页一致
- [ ] 单选/多选仍然只支持 A/B/C/D
- [ ] 判断题仍然只允许对/错
- [ ] 简答题仍然只允许文本答案
- [ ] 保存后节点详情刷新为最新内容
- [ ] 保存后知识点绑定仍然可用

---

## 5. 接口联调检查项

## 5.1 创建接口

接口：
- `POST /api/v1/admin/questions`

检查：
- [ ] `single` 成功
- [ ] `multiple` 成功
- [ ] `true_false` 成功
- [ ] `short_answer` 成功
- [ ] `true_false` 携带 `options` 时返回 422
- [ ] `short_answer` 携带 `options` 时返回 422

---

## 5.2 更新接口

接口：
- `PATCH /api/v1/admin/questions/{id}`

检查：
- [ ] 同题型编辑成功
- [ ] 跨题型切换成功
- [ ] 切换到非选择题时若未清掉 options，应返回失败
- [ ] 返回值中 `question_type / options / answer` 与目标题型一致

---

## 5.3 导入接口

接口：
- `POST /api/v1/admin/questions/import`

检查：
- [ ] JSON body 导入成功
- [ ] form-data + json_data 导入成功
- [ ] form-data + `.json` 文件导入成功
- [ ] form-data + `.xlsx` 文件导入成功
- [ ] partial success 统计正确
- [ ] errors 返回失败项说明

---

## 6. 数据一致性检查

- [ ] 单选答案入库为单个字母
- [ ] 多选答案入库为 `A,C` 这种规范字符串
- [ ] 判断题答案入库为 `true/false`
- [ ] 简答题答案入库为文本
- [ ] 判断题/简答题 `options` 为 `null`
- [ ] 单选/多选 `options` 为对象数组 `{label,text}`

---

## 7. dirty 规则回归检查

必须确认：

- [ ] 仅修改 `question_text` 时，`is_dirty=true`
- [ ] 仅修改 `options/answer` 时，不因本轮改造破坏既有 dirty 规则
- [ ] `content_hash` 会随 `question_text/options/answer` 变化而更新

---

## 8. 已完成自动验证

本轮已完成：

- 后端测试：
  - `app/tests/test_unit_question_rules.py`
  - `app/tests/test_question_dirty_rule.py`
  - `app/tests/test_api_questions.py`
  - `app/tests/test_e2e_workflows.py`
- 前端检查：
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`

---

## 9. 建议的手工回归顺序

建议按以下顺序执行：

1. 题库管理页新建四种题型
2. 题库管理页编辑四种题型
3. JSON 导入合法文件
4. JSON 导入混合合法/非法文件
5. Excel 导入合法文件
6. Excel 导入混合合法/非法文件
7. 知识图谱页编辑已有题目
8. 回看题目列表展示与答案展示

---

## 10. 当前已知非阻塞项

- CLI 环境下未执行浏览器手工 smoke
- 后端存在独立的 mypy 历史基线问题，未纳入本轮题型改造处理
