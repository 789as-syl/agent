# 管理端题库导入模板说明

适用范围：
- 新建题目
- 编辑题目
- 批量导入

以上三条链路已统一按题型规则处理，必须使用同一套字段与校验规则。

---

## 1. 支持的题型

仅支持以下四种：

- `single`
- `multiple`
- `true_false`
- `short_answer`

不再兼容旧写法，例如：
- `single_choice`
- `multiple_choice`

---

## 2. 通用字段

所有题型统一字段模型如下：

| 字段 | 必填 | 说明 |
|---|---|---|
| `external_id` | 否 | 外部唯一标识，建议导入时填写，便于幂等更新 |
| `question_text` | 是 | 题干 |
| `question_type` | 是 | 题型，必须是四种 canonical 值之一 |
| `options` | 按题型 | 仅单选/多选可填写 |
| `answer` | 是 | 标准答案 |
| `explanation` | 否 | 解析 |
| `knowledge_point_titles` | 否 | 关联知识点标题数组 |

---

## 3. 各题型规则

### 3.1 单选题 `single`

- 选项固定只支持 `A/B/C/D`
- 至少填写 2 个选项，最多 4 个
- 选项必须连续，不能跳空
- `answer` 必须是一个选项字母，如：`A`

示例：

```json
{
  "question_text": "2 + 2 = ?",
  "question_type": "single",
  "options": [
    { "label": "A", "text": "3" },
    { "label": "B", "text": "4" }
  ],
  "answer": "B"
}
```

### 3.2 多选题 `multiple`

- 选项固定只支持 `A/B/C/D`
- 至少填写 2 个选项，最多 4 个
- 选项必须连续，不能跳空
- `answer` 必须为逗号分隔字母，如：`A,C`
- 至少 2 个答案

示例：

```json
{
  "question_text": "哪些是质数?",
  "question_type": "multiple",
  "options": [
    { "label": "A", "text": "2" },
    { "label": "B", "text": "4" },
    { "label": "C", "text": "5" }
  ],
  "answer": "A,C"
}
```

### 3.3 判断题 `true_false`

- 不允许填写 `options`
- `answer` 只能是：
  - `true`
  - `false`

前端展示为“对/错”，后端入库统一保存为 `true/false`。

示例：

```json
{
  "question_text": "太阳从东方升起。",
  "question_type": "true_false",
  "options": null,
  "answer": "true"
}
```

### 3.4 简答题 `short_answer`

- 不允许填写 `options`
- `answer` 为文本

示例：

```json
{
  "question_text": "请简述 HTTP 的作用。",
  "question_type": "short_answer",
  "options": null,
  "answer": "用于客户端与服务端传输超文本数据的应用层协议。"
}
```

---

## 4. JSON 导入格式

### 4.1 直接请求体

```json
{
  "bank_id": "题库ID",
  "questions": [
    {
      "external_id": "q-1",
      "question_text": "2 + 2 = ?",
      "question_type": "single",
      "options": [
        { "label": "A", "text": "3" },
        { "label": "B", "text": "4" }
      ],
      "answer": "B",
      "explanation": "4 正确",
      "knowledge_point_titles": []
    }
  ]
}
```

### 4.2 上传 `.json` 文件

支持两种文件结构：

1. 对象格式

```json
{
  "bank_id": "题库ID",
  "questions": [...]
}
```

2. 仅数组格式  
此时 `bank_id` 通过 form-data 单独传入。

```json
[
  {
    "external_id": "q-1",
    "question_text": "2 + 2 = ?",
    "question_type": "single",
    "options": [
      { "label": "A", "text": "3" },
      { "label": "B", "text": "4" }
    ],
    "answer": "B",
    "knowledge_point_titles": []
  }
]
```

仓库内示例文件：
- `docs/examples/admin-question-import-sample.json`
- `docs/examples/admin-question-import-mixed-invalid.json`
- `docs/examples/admin-question-import-sample.xlsx`

---

## 5. Excel 导入模板

Excel 表头支持以下 canonical 列：

| 列名 |
|---|
| `external_id` |
| `question_text` |
| `question_type` |
| `option_a` |
| `option_b` |
| `option_c` |
| `option_d` |
| `answer` |
| `explanation` |
| `knowledge_point_titles` |

说明：
- `knowledge_point_titles` 多个值用英文逗号分隔
- `single/multiple` 读取 `option_a` 到 `option_d`
- `true_false/short_answer` 不允许填写 `option_a~d`

---

## 6. 导入失败策略

当前导入策略为：

- 非法行跳过
- 合法行继续
- 返回创建/更新/跳过/失败统计
- 返回错误列表，便于定位失败行或失败项

---

## 7. 严格校验说明

本轮改造已明确采用：

- 严格按新模板校验
- 不做旧格式宽松兼容

因此以下内容会失败：

- 旧题型值：`single_choice` / `multiple_choice`
- `options` 使用字符串数组
- 判断题/简答题仍填写选项
- 单/多选答案不使用字母
- 多选答案只填一个选项
- 选项标签不连续或跳空
