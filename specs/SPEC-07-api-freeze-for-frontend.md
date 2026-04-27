# SPEC-07-api-freeze-for-frontend.md

## 1. 阶段目标
冻结后端对前端开放的 API 契约，产出前端可直接参考的接口文档、SSE 协议、示例 payload、错误码表。

## 2. 范围
- 冻结 OpenAPI
- 冻结 SSE 事件 schema
- 输出接口示例
- 输出鉴权说明
- 输出分页/筛选/排序约定
- 输出错误码字典
- 输出前端 mock 示例

## 3. 必须产出
- openapi.json
- docs/api-reference.md
- docs/sse-events.md
- docs/error-codes.md
- docs/frontend-integration-checklist.md

## 4. 规则
- 从本阶段起，对前端公开字段不得随意改名
- 新增字段必须向后兼容
- 若必须破坏变更，必须增加版本号或显式迁移说明

## 5. 验收标准
- 前端团队仅凭文档即可开始开发
- 至少覆盖认证、会话、知识点管理、题库管理、chat stream
- 示例请求/响应完整
