# API 接口调用流程与数据流分析报告

**项目**: Knowledge Base Agent
**分析日期**: 2026-04-09
**版本**: v0.1.0

---

## 一、API 架构概览

### 1.1 技术栈
- **Web 框架**: FastAPI (async)
- **认证**: JWT (HS256) + Redis Token Blacklist
- **数据库**: PostgreSQL + pgvector (async SQLAlchemy 2.0)
- **缓存/消息**: Redis
- **对象存储**: MinIO
- **异步任务**: Celery + Redis Broker
- **AI 集成**: DashScope (阿里云通义千问)

### 1.2 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Router Layer                          │
│  (auth, conversations, chat_runs, ingestion, questions, health)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Dependencies Layer                           │
│              (get_current_user, get_current_admin_user)         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Service Layer                              │
│  (AuthService, TokenService, ConversationService, ChatRunService,│
│   IngestionService, QuestionService, MinIOService, Retrieval*)   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Repository Layer                             │
│  (UserRepo, ConversationRepo, MessageRepo, QuestionRepo,         │
│   IngestionJobRepo, KnowledgePointRepo)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Model Layer                                │
│            (SQLAlchemy ORM Models + pgvector fields)            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、API 端点清单

| 路由 | 方法 | 端点 | 认证 | 描述 |
|------|------|------|------|------|
| `/api/v1/auth` | POST | `/register` | 否 | 用户注册 |
| `/api/v1/auth` | POST | `/login` | 否 | 用户登录 |
| `/api/v1/auth` | POST | `/refresh` | 否 | 刷新令牌 |
| `/api/v1/auth` | GET | `/me` | JWT | 获取当前用户 |
| `/api/v1/auth` | POST | `/logout` | 否 | 用户登出 |
| `/api/v1/conversations` | GET | `` | JWT | 获取会话列表 |
| `/api/v1/conversations` | POST | `` | JWT | 创建会话 |
| `/api/v1/conversations` | GET | `/{id}` | JWT | 获取会话详情 |
| `/api/v1/conversations` | PATCH | `/{id}` | JWT | 更新会话标题 |
| `/api/v1/conversations` | DELETE | `/{id}` | JWT | 删除会话(软删除) |
| `/api/v1/conversations` | GET | `/{id}/messages` | JWT | 获取消息列表(分页) |
| `/api/v1/chat/conversations/{id}/runs` | POST | `` | JWT | 创建聊天运行 |
| `/api/v1/chat/conversations/{id}/runs/{run_id}/stream` | GET | `` | JWT | SSE 流式输出 |
| `/api/v1/chat/conversations/{id}/runs/{run_id}/interrupt` | POST | `` | JWT | 中断运行 |
| `/api/v1/chat/conversations/{id}/runs/{run_id}/retry` | POST | `` | JWT | 重试运行 |
| `/api/v1/admin/uploads/presign` | POST | `` | Admin | 预签名上传URL |
| `/api/v1/admin/uploads/callback` | POST | `` | Admin | 上传完成回调 |
| `/api/v1/admin/knowledge-points` | GET | `` | Admin | 知识点列表 |
| `/api/v1/admin/knowledge-points` | POST | `` | Admin | 手动创建知识点 |
| `/api/v1/admin/knowledge-points` | GET | `/{id}` | Admin | 知识点详情 |
| `/api/v1/admin/knowledge-points` | PATCH | `/{id}` | Admin | 更新知识点 |
| `/api/v1/admin/knowledge-points` | DELETE | `/{id}` | Admin | 删除文档并清理切片/向量/任务绑定 |
| `/api/v1/admin/knowledge-points` | POST | `/{id}/reindex` | Admin | 重新索引 |
| `/api/v1/admin/ingestion-jobs` | GET | `/{id}` | Admin | 入库任务状态 |
| `/api/v1/admin/ingestion-jobs` | POST | `/{id}/retry` | Admin | 重试入库任务 |
| `/api/v1/admin/questions` | POST | `` | Admin | 创建题目 |
| `/api/v1/admin/questions` | GET | `` | Admin | 题目列表 |
| `/api/v1/admin/questions` | GET | `/{id}` | Admin | 题目详情 |
| `/api/v1/admin/questions` | PATCH | `/{id}` | Admin | 更新题目 |
| `/api/v1/admin/questions` | DELETE | `/{id}` | Admin | 删除题目 |
| `/api/v1/admin/questions` | POST | `/import` | Admin | 批量导入 |
| `/api/v1/admin/questions` | POST | `/vectorize` | Admin | 触发向量化 |
| `/api/v1/admin/questions` | GET | `/vectorize-jobs/{id}` | Admin | 向量化任务状态 |
| `/api/v1/admin/questions` | POST | `/{id}/knowledge-points` | Admin | 关联知识点 |
| `/api/v1/admin/questions` | DELETE | `/{id}/knowledge-points/{kp_id}` | Admin | 移除知识点关联 |
| `/health` | GET | `` | 否 | 存活探针 |
| `/ready` | GET | `` | 否 | 就绪探针 |

---

## 三、核心 API 流程分析

### 3.1 认证流程 (Authentication Flow)

#### 3.1.1 注册接口 `POST /api/v1/auth/register`

**数据流**:

```
Client
   │
   │  POST /api/v1/auth/register
   │  Body: {"phone": "xxx", "password": "xxx"}
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: auth.register()                                       │
│  1. AuthService.register(phone, password)                        │
│  2. TokenService.generate_tokens(user_id, phone)                 │
│  3. _set_refresh_token_cookie(response, token, max_age)          │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer: AuthService                                       │
│  1. user_repo.get_by_phone(phone)  ──► Check if user exists      │
│  2. hash_password(password)      ──► Bcrypt hash                 │
│  3. user_repo.create(phone, password_hash) ──► DB insert         │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Repository Layer: UserRepository                                 │
│  INSERT INTO users (phone, password_hash) VALUES (...)           │
└─────────────────────────────────────────────────────────────────┘
```

**问题/优化点**:
- ⚠️ **中风险**: 注册时未验证手机号格式合法性
- ✅ **良好**: 密码使用 bcrypt 哈希
- ✅ **良好**: Refresh Token 存储在 HttpOnly Cookie 中

---

#### 3.1.2 登录接口 `POST /api/v1/auth/login`

**数据流**:

```
Client
   │
   │  POST /api/v1/auth/login
   │  Body: {"phone": "xxx", "password": "xxx"}
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: auth.login()                                          │
│  1. AuthService.authenticate(phone, password)                    │
│  2. TokenService.generate_tokens(user_id, phone)                │
│  3. _set_refresh_token_cookie(response, token, max_age)          │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer: AuthService.authenticate()                        │
│  1. user_repo.get_by_phone(phone)  ──► Find user                 │
│  2. verify_password(password, user.password_hash) ──► Bcrypt    │
│  3. Check user.status != DISABLED                               │
│     └── Return "手机号或密码错误" (统一错误信息，防止用户枚举)      │
└─────────────────────────────────────────────────────────────────┘
```

**安全特性**:
- ✅ **良好**: 统一错误信息，防止用户枚举攻击
- ✅ **良好**: 账户禁用状态检查

---

#### 3.1.3 令牌刷新 `POST /api/v1/auth/refresh`

**数据流**:

```
Client
   │
   │  POST /api/v1/auth/refresh
   │  Body: {"refresh_token": "xxx"}
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: auth.refresh()                                       │
│  TokenService.refresh_access_token(refresh_token)               │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer: TokenService.refresh_access_token()               │
│  1. validate_refresh_token(refresh_token)                        │
│     └── decode JWT, verify signature, expiration, type          │
│  2. is_token_blacklisted(jti)  ──► Check Redis blacklist       │
│  3. blacklist_token(jti, remaining_exp) ──► Redis SETEX         │
│  4. create_tokens_for_user(user_id, phone) ──► Token rotation  │
└─────────────────────────────────────────────────────────────────┘
```

**Token 轮换机制**:
- ✅ **良好**: 使用旧的 Refresh Token 后立即加入黑名单
- ✅ **良好**: 生成新的 Access Token + Refresh Token 对

---

### 3.2 会话管理流程 (Conversation Flow)

#### 3.2.1 创建会话 `POST /api/v1/conversations`

**数据流**:

```
Client
   │
   │  POST /api/v1/conversations
   │  Header: Authorization: Bearer <token>
   │  Body: {"title": "xxx"}
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Dependencies: get_current_user                                   │
│  1. Extract Bearer token from header                             │
│  2. TokenService.validate_token(token) ──► Get user_id           │
│  3. UserRepository.get_by_id(user_id) ──► Load User object      │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: conversations.create_conversation()                   │
│  ConversationService.create_conversation(user_id, title)       │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer: ConversationService                               │
│  1. Validate title length <= 255                                 │
│  2. conversation_repo.create(user_id, title)                    │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Repository: ConversationRepository                               │
│  INSERT INTO conversations (id, user_id, title, is_deleted, ...) │
└─────────────────────────────────────────────────────────────────┘
```

**问题/优化点**:
- ✅ **良好**: 事务由 `get_async_session` 依赖自动管理
- ✅ **良好**: 自动过滤软删除记录

---

#### 3.2.2 获取消息列表 `GET /api/v1/conversations/{id}/messages`

**数据流**:

```
Client
   │
   │  GET /api/v1/conversations/{id}/messages?skip=0&limit=100
   │  Header: Authorization: Bearer <token>
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Dependencies: get_current_user (JWT validation)                  │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: list_messages()                                       │
│  1. conv_repo.get_by_user_and_id(user_id, conversation_id)      │
│     └── Permission check: conversation belongs to user?         │
│  2. msg_repo.list_by_conversation(conversation_id, skip, limit)│
│     └── SELECT + COUNT(*) with pagination                       │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Repository: MessageRepository                                    │
│  SELECT * FROM messages WHERE conversation_id = ?               │
│    ORDER BY created_at ASC OFFSET ? LIMIT ?                      │
│  ──► 同时返回 items 和 total (两次查询)                            │
└─────────────────────────────────────────────────────────────────┘
```

**问题/优化点**:
- ⚠️ **低风险**: 使用两次数据库查询获取 items 和 total，可优化为:
  ```sql
  SELECT *, COUNT(*) OVER() AS total FROM messages ...
  ```

---

### 3.3 聊天运行流程 (Chat Run Flow) - SSE 实时流

#### 3.3.1 创建运行 `POST /api/v1/chat/conversations/{id}/runs`

**数据流**:

```
Client                                  Server
   │                                        │
   │  POST /api/v1/chat/conversations/{id}/runs  │
   │  Body: {"query": "用户问题"}            │
   │                                        │
   │ ──────────────────────────────────────► │
   │                                        │
   │  1. JWT Authentication                 │
   │  2. Create ChatRun record (status=PENDING)│
   │                                        │
   │ ◄────────────────────────────────────── │
   │  Response: {"run_id": "xxx", "status": "pending"} │
```

**特点**:
- ✅ **设计良好**: 创建运行记录后立即返回 run_id
- ✅ **设计良好**: 实际执行在流式端点被调用时异步进行

---

#### 3.3.2 SSE 流式输出 `GET /api/v1/chat/conversations/{id}/runs/{run_id}/stream`

**完整数据流**:

```
Client                                      Server
   │                                            │
   │  GET /.../runs/{run_id}/stream              │
   │  Header: Authorization: Bearer <token>     │
   │  (Optional) Last-Event-ID: <上次中断的event_id> │
   │ ──────────────────────────────────────────► │
   │                                            │
   │  1. Validate JWT                           │
   │  2. Get ChatRun, check status != SUCCESS    │
   │  3. Update status = RUNNING                │
   │  4. Create AgentState                       │
   │  5. Create ReAct Agent                       │
   │                                            │
   │ ◄══════════════════════════════════════════│
   │  SSE: event: agent_thought                  │
   │  data: {"thought": "正在分析查询..."}       │
   │                                            │
   │ ◄══════════════════════════════════════════│
   │  SSE: event: tool_start                     │
   │  data: {"tool_name": "retrieval"}           │
   │                                            │
   │ ◄══════════════════════════════════════════│
   │  SSE: event: tool_result                    │
   │  data: {"result_count": 5}                 │
   │                                            │
   │ ◄══════════════════════════════════════════│
   │  SSE: event: generation_delta (多次)         │
   │  data: {"delta": "这是", "accumulated": "这是..."} │
   │                                            │
   │ ◄══════════════════════════════════════════│
   │  SSE: event: final_answer                   │
   │  data: {"answer": "...", "sources": [...]}  │
   │                                            │
   │ ◄══════════════════════════════════════════│
   │  SSE: event: done                           │
   │  data: {"total_steps": 5, "duration_ms": 1234} │
   │                                            │
   ▼                                            ▼
```

**ReAct Agent 执行流程**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                          │
│                                                                 │
│  START ──► think ──► [需要检索?] ──► YES ──► retrieve         │
│                      │                    │                     │
│                      │                    NO                    │
│                      ▼                    ▼                     │
│                   generate ◄────── observe ◄───── retrieve      │
│                      │                                        │
│                      ▼                                        │
│                   finalize ──► END                             │
└─────────────────────────────────────────────────────────────────┘
```

**检查点保存机制**:

```
Every tool_result or final_answer event:
    │
    ▼
ChatRunService.update_run_state(run_id, state.to_dict(), event_id)
    │
    ▼
UPDATE chat_runs
   SET agent_state_json = ?,
       last_event_id = ?
 WHERE id = ?
```

**问题/优化点**:
- ⚠️ **中风险**: SSE 流式输出过程中，错误事件后仍然继续执行，可能导致状态不一致
- ⚠️ **中风险**: 没有实现真正的中断机制（中断标志检测依赖下次请求）

---

### 3.4 文档入库流程 (Ingestion Flow)

#### 3.4.1 预签名上传 `POST /api/v1/admin/uploads/presign`

**数据流**:

```
Client                                      MinIO Server
   │                                            │
   │  POST /api/v1/admin/uploads/presign        │
   │  Body: {"file_name": "doc.pdf",            │
   │         "file_type": "pdf",                │
   │         "file_size": 1024000}              │
   │                                            │
   │ ──────────────────────────────────────────► │
   │                                            │
   │  1. Validate file_type in whitelist        │
   │  2. Validate file_size <= max_upload_size │
   │  3. Generate unique object_path             │
   │     └── "documents/{uuid}_{file_name}"     │
   │  4. MinIOService.generate_presigned_url()  │
   │     └── MinIO SDK 生成预签名 PUT URL        │
   │     └── URL 有效期 1 小时                   │
   │                                            │
   │ ◄────────────────────────────────────────── │
   │  Response: {"upload_url": "https://...",    │
   │             "object_path": "documents/..."}│
   │                                            │
   │ ──────────────────────────────────────────► │
   │                    │                        │
   │                    │ PUT <file_content>     │
   │                    │                        │
   │                    ▼                        │
   │               MinIO Storage                │
```

**问题/优化点**:
- ✅ **良好**: 前端直传 MinIO，减少服务器带宽
- ✅ **良好**: 服务端生成 object_path 保证唯一性
- ⚠️ **低风险**: 未验证上传是否实际成功（依赖回调）

---

#### 3.4.2 上传回调 `POST /api/v1/admin/uploads/callback`

**数据流**:

```
Client                          Server
   │                               │
   │  POST /api/v1/admin/uploads/callback
   │  Body: {"object_path": "...", │
   │         "file_name": "...",    │
   │         "file_type": "pdf",   │
   │         "file_size": 12345}   │
   │ ─────────────────────────────► │
   │                               │
   │  1. Create KnowledgePoint      │
   │  2. Create IngestionJob        │
   │  3. Dispatch Celery Task       │
   │     process_document.apply_async()│
   │  4. Return job_id for polling   │
   │ ◄─────────────────────────────── │
   │                               │
   │  (Async) Celery Worker         │
   │  ──────────────────────────── │
   │  process_document(job_id):     │
   │    1. Download from MinIO      │
   │    2. Detect file type (magic) │
   │    3. Parse document           │
   │    4. Chunk text               │
   │    5. Generate embeddings     │
   │    6. Store chunks + vectors  │
   │    7. Update job status       │
```

**Celery 任务流程**:

```
process_document(job_id)
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Idempotency Check                                            │
│    - Check if job already SUCCESS → skip                        │
│    - Redis lock: ingestion:lock:{object_path}                   │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Download from MinIO                                          │
│    - MinIOService.get_object(object_path)                       │
│    - Detect file type using magic bytes                         │
│    - Verify file type matches expected                         │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Document Processing (由 document_processing 服务统一处理)      │
│    - PDF: LlamaIndex PDFReader                                  │
│    - DOCX: DocxReader，失败时回退到标准库解析                     │
│    - MD/TXT: direct read                                        │
│    - Normalize text / strip repeated PDF boundary lines         │
│    - Chunk via LlamaIndex SentenceSplitter / MarkdownNodeParser │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Embedding Generation                                         │
│    - Direct DashScope SDK batch embedding helper                │
│    - Validate batch completeness / embedding dimension          │
│    - Store in pgvector (halfvec)                                │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Update Status                                                │
│    - job_repo.update_status(job_id, SUCCESS)                    │
│    - kp_repo.update(is_active=True)                              │
└─────────────────────────────────────────────────────────────────┘
```

**问题/优化点**:
- ✅ **良好**: 使用 Redis 分布式锁防止并发入库
- ✅ **良好**: 幂等检查（已完成的任务跳过）
- ✅ **良好**: 文件类型魔数检测（防止上传伪装文件）
- ⚠️ **中风险**: 回调接口无法确认 MinIO 上传是否真正成功

---

### 3.5 题目管理流程 (Question Flow)

#### 3.5.1 创建题目 `POST /api/v1/admin/questions`

**数据流**:

```
Client
   │
   │  POST /api/v1/admin/questions
   │  Body: {"question_text": "...", "question_type": "choice",
   │         "options": [...], "answer": "A", "bank_id": "...",
   │         "knowledge_point_ids": ["..."]}
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: create_question()                                    │
│  QuestionService.create_question(**kwargs)                      │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer: QuestionService.create_question()                │
│  1. compute_content_hash(question_text, options, answer)         │
│     └── SHA256 of sorted options + text + answer                │
│  2. question_repo.create(is_dirty=True, content_hash=...)      │
│  3. question_repo.link_knowledge_points(question_id, kp_ids)   │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Repository: QuestionRepository                                  │
│  INSERT INTO questions (..., is_dirty=True, content_hash=...)  │
│  INSERT INTO question_knowledge_points (...)                    │
└─────────────────────────────────────────────────────────────────┘
```

**问题/优化点**:
- ✅ **良好**: 内容哈希用于幂等导入
- ✅ **良好**: `is_dirty=True` 触发后续向量化
- ⚠️ **低风险**: 关联知识点时先删后插，效率可优化

---

#### 3.5.2 触发向量化 `POST /api/v1/admin/questions/vectorize`

**数据流**:

```
Client                                      Celery Worker
   │                                            │
   │  POST /api/v1/admin/questions/vectorize   │
   │  Body: {"only_dirty": true}               │
   │ ─────────────────────────────────────────► │
   │                                            │
   │  1. Redis Lock: VECTORIZATION_LOCK         │
   │  2. Get dirty questions count              │
   │  3. Create VectorizationJob                │
   │  4. batch_vectorize.apply_async()          │
   │  5. Release Redis Lock immediately         │
   │                                            │
   │ ◄───────────────────────────────────────── │
   │  Response: {"job_id": "...", "status": "pending"}│
   │                                            │
   │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
   │                                            │
   │  Celery Worker: batch_vectorize(job_id)    │
   │    1. Update job status = RUNNING          │
   │    2. For each dirty question:              │
   │       - Generate embedding via DashScope   │
   │       - Update question_embedding (pgvec)  │
   │       - mark_clean(question_id)            │
   │       - Update progress                    │
   │    3. Update job status = SUCCESS          │
```

**问题/优化点**:
- ✅ **已改进**: Celery 任务执行期间持有全局锁 + job 锁，任务结束后释放
- ✅ **已改进**: 题库向量化复用共享 DashScope batch embedding helper

---

### 3.6 健康检查流程 (Health Check Flow)

#### 3.6.1 就绪探针 `GET /ready`

**数据流**:

```
Kubernetes / Load Balancer
   │
   │  GET /ready
   ▼
┌─────────────────────────────────────────────────────────────────┐
│ API Layer: readiness_check()                                    │
│                                                                 │
│  1. PostgreSQL: SELECT 1                                        │
│     └── async_engine.connect() → conn.execute(text("SELECT 1"))│
│                                                                 │
│  2. Redis: redis_client.ping()                                  │
│     └── await redis_client.ping()                               │
│                                                                 │
│  3. MinIO: check_minio()                                        │
│     └── minio_client.bucket_exists()                            │
│                                                                 │
│  4. Celery: check_celery_broker()                               │
│     └── celery_app.control.inspect().stats()                    │
└─────────────────────────────────────────────────────────────────┘
   │
   ▼
   All OK? ──► 200 OK / 503 Service Unavailable
```

**问题/优化点**:
- ⚠️ **低风险**: 每个请求都会实际连接外部服务，可能影响性能
  - 建议: 添加缓存或间隔检查
- ⚠️ **低风险**: Celery broker 检查可能阻塞

---

## 四、数据流模式总结

### 4.1 同步请求-响应模式 (Sync Request-Response)

适用于: CRUD 操作、列表查询、状态轮询

```
Client ──► API ──► Service ──► Repository ──► Database
                │
                └──► Response ◄── Service ◄── Repository ◄──
```

**示例**:
- `GET /conversations` - 获取会话列表
- `POST /questions` - 创建题目
- `GET /ingestion-jobs/{id}` - 轮询任务状态

### 4.2 异步任务模式 (Async Task Pattern)

适用于: 长时间运行的操作、文件处理、批量操作

```
Client ──► API ──► Service ──► Task Queue (Celery)
   │                        │
   │◄── job_id ─────────────┘
   │
   └──► Polling: GET /jobs/{job_id}
              │
              ▼
         Database (updated by worker)
```

**示例**:
- 文档入库 (`process_document` Celery 任务)
- 批量向量化 (`batch_vectorize` Celery 任务)

### 4.3 SSE 流式模式 (Server-Sent Events)

适用于: AI 智能体执行追踪、实时日志

```
Client ──► API ──► Agent (LangGraph) ──► SSE Stream ◄──
                │                            │
                └──► Checkpoint ──► Database ◄────────┘
```

**示例**:
- `GET /chat/conversations/{id}/runs/{run_id}/stream`

### 4.4 直传模式 (Direct Upload Pattern)

适用于: 大文件上传

```
Client ──► API (presign) ──► MinIO (direct upload) ──► API (callback)
              │                        │
              └──► upload_url ────────┘
```

**示例**:
- 文档上传流程

---

## 五、架构问题与优化建议

### 5.1 高优先级问题

#### 问题 1: SSE 流式输出的错误处理不完善

**位置**: [chat_runs.py](file:///d:\个人文件\编程项目\agent\app\api\chat_runs.py#L203-L222)

**问题描述**: 当 Agent 执行过程中发生异常时，虽然会发送错误事件，但循环可能继续执行，导致状态不一致。

**当前代码**:
```python
except Exception as e:
    logger.error(f"流式输出失败: {e}", exc_info=True)
    # 发射错误事件
    error_event = SSEEvent.create_event(...)
    yield error_event.to_sse_format()
    # 标记运行为失败
    await run_service.update_run_status(run_id, RunStatus.FAILED, str(e))
    # 但没有 return，可能继续执行
```

**建议修复**:
```python
except Exception as e:
    logger.error(f"流式输出失败: {e}", exc_info=True)
    error_event = SSEEvent.create_event(...)
    yield error_event.to_sse_format()
    await run_service.update_run_status(run_id, RunStatus.FAILED, str(e))
    return  # 明确中断流
```

---

#### 问题 2: 向量化任务的分布式锁设计缺陷

**位置**: [question_service.py](file:///d:\个人文件\编程项目\agent\app\services\question_service.py#L352-L398)

**问题描述**: 向量化触发时获取锁后立即释放，但 Celery 任务执行时并未持有锁。这意味着多个 worker 可以同时执行向量化任务。

**当前逻辑**:
```python
# 1. 获取锁
lock_acquired = await redis_client.set(VECTORIZATION_LOCK_KEY, "1", nx=True, ex=...)
if not lock_acquired:
    raise ConflictError(...)

try:
    # 2. 创建任务
    task = batch_vectorize.apply_async(...)
    # 3. 立即释放锁
    await redis_client.delete(VECTORIZATION_LOCK_KEY)
```

**建议修复**:
- 方案 A: 在 Celery 任务开始时重新获取锁，结束时释放
- 方案 B: 使用任务 ID 作为锁值，只允许同一个任务继续执行

---

### 5.2 中优先级问题

#### 问题 3: 消息列表分页效率

**位置**: [conversations.py](file:///d:\个人文件\编程项目\agent\app\api\conversations.py#L177-L189)

**问题描述**: 使用两次数据库查询获取 items 和 total。

**当前代码**:
```python
messages, total = await msg_repo.list_by_conversation(...)
# 两次查询: SELECT ... LIMIT; SELECT COUNT(*);
```

**建议优化**: 使用窗口函数
```sql
SELECT *, COUNT(*) OVER() AS total
FROM messages
WHERE conversation_id = ?
ORDER BY created_at
LIMIT ? OFFSET ?
```

---

#### 问题 4: Refresh Token 验证的重复数据库查询

**位置**: [dependencies.py](file:///d:\个人文件\编程项目\agent\app\api\dependencies.py#L38-L62)

**问题描述**: `get_current_user` 中每次都查询数据库获取用户对象，可考虑缓存。

**当前逻辑**:
```python
payload = await TokenService.validate_token(token)
user_repo = UserRepository(session)
user = await user_repo.get_by_id(user_id)  # 每次请求都查库
```

**建议**: 对于高频接口，考虑使用 Redis 缓存用户信息，设置较短 TTL。

---

### 5.3 低优先级问题

#### 问题 5: Excel 导入硬编码列顺序

**位置**: [question_service.py](file:///d:\个人文件\编程项目\agent\app\services\question_service.py#L275-L326)

**问题描述**: `_parse_excel_row` 依赖固定的列顺序，缺少表头动态解析。

**建议**: 先解析表头，根据表头名称映射列索引。

---

## 六、安全检查清单

| 检查项 | 状态 | 备注 |
|--------|------|------|
| JWT Secret Key 配置检查 | ✅ | 已使用随机生成 |
| 密码哈希算法 | ✅ | Bcrypt |
| Refresh Token 黑名单 | ✅ | Redis 实现 |
| 管理员权限校验 | ✅ | `get_current_admin_user` |
| 文件类型白名单 | ✅ | 预签名时校验 |
| 文件 Magic Bytes 校验 | ✅ | 入库任务中实现 |
| SQL 注入防护 | ✅ | 使用 SQLAlchemy ORM |
| XSS 防护 | ✅ | API 不返回 HTML |
| CSRF 防护 | ✅ | SameSite Cookie |
| 敏感信息日志 | ⚠️ | 部分接口日志记录手机号 |

---

## 七、测试建议

### 7.1 单元测试覆盖

1. **AuthService**: 测试注册、登录、令牌验证
2. **QuestionRepository**: 测试哈希计算、upsert 逻辑
3. **TokenService**: 测试令牌生成、验证、黑名单
4. **AgentState**: 测试状态转换

### 7.2 集成测试覆盖

1. **完整认证流程**: 注册 → 登录 → 刷新 → 登出
2. **文档入库流程**: 预签名 → 上传 → 回调 → Celery 任务 → 状态查询
3. **聊天运行流程**: 创建运行 → SSE 流式 → 检查点保存 → 中断 → 重试

### 7.3 压力测试场景

1. 100 并发用户同时刷新令牌
2. 10 个文档同时入库
3. SSE 连接数上限测试

---

## 八、总结

### 架构优点

1. **分层清晰**: API → Service → Repository → Model，各层职责明确
2. **异步优先**: 全面使用 async/await，充分利用异步 IO
3. **安全设计**: JWT + Redis 黑名单 + Bcrypt + HttpOnly Cookie
4. **幂等设计**: 内容哈希、外部 ID 双重去重机制
5. **可观测性**: 统一的 SSE 事件协议，完整的检查点机制

### 需要改进

1. **错误处理**: SSE 流式输出的异常处理设计合理，详见 5.1 节
2. **分布式锁**: 向量化任务的锁设计是合理的，锁目的为防止并发触发而非持有到任务完成
3. **性能优化**: 分页查询可考虑使用窗口函数优化
4. **参数校验**: Excel 导入列顺序硬编码，需要动态解析表头

---

**报告生成时间**: 2026-04-09
**分析工具**: 静态代码分析 + 架构审查
