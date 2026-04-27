# SPEC-02-auth-and-session.md

## 1. 阶段目标
实现用户认证、JWT 鉴权、用户信息与会话持久化，为后续对话与 Trace 奠定身份基础。

## 2. 范围
- 用户注册：手机号 + 密码
- 用户登录：手机号 + 密码
- JWT 签发/校验
- 当前用户信息接口
- 会话 CRUD 基础能力
- 消息记录基础表结构
- 本地历史会话与服务端历史会话的同步基础接口

## 3. 数据模型
- users
- conversations
- messages

建议字段：
- users: id, phone, password_hash, status, created_at
- conversations: id, user_id, title, created_at, updated_at, deleted_at
- messages: id, conversation_id, role, content, metadata_json, created_at

## 4. API
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/me
- GET /api/v1/conversations
- POST /api/v1/conversations
- GET /api/v1/conversations/{id}
- DELETE /api/v1/conversations/{id}
- GET /api/v1/conversations/{id}/messages

## 5. 规则
- JWT 无状态
- 密码 bcrypt
- phone 唯一
- conversation 软删除
- message 只做追加，不做原地覆盖

## 6. 验收标准
- 注册/登录/鉴权链路通
- 未授权访问返回统一错误码
- 用户只能访问自己的 conversation
- OpenAPI 文档正确
- auth / conversation 基础单测与集成测试通过
