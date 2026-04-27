### 🧩 一、三端需求与技术栈矩阵

| 维度               | 🖥️ 用户端前端                                                 | 🛠️ 管理端前端                                                 | ⚙️ 后端服务 (RAG Core)                                        |
| :----------------- | :----------------------------------------------------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| **🎯 功能性需求**   | 1. **认证**：手机+密码注册/登录（JWT无状态），暂时不实现短信验证服务<br />2. **AI对话**：支持流式问答<br>3. **Trace可视化**：Trace实时渲染workflows流程<br>4. **会话管理**：本地历史会话记录、清空、导出、新建对话。 | 1. **知识库管理**：支持 PDF/Word/MD/TXT 文档上传，每文档对应一个知识点（KP），文档自动切分为多个向量，支持解析进度查看，知识点编辑、向量刷新<br>2. **题库管理**：  JSON/Excel 批量导入，题目 CRUD 题目与知识点：多对多关系， 题目量少，向量与关系数据统一存关系数据库 ，向量化开关<br>3.**知识图谱可视化**：  展示题库与知识点之间的多对多关系网络，支持节点点击查看详情<br />4. **数据看板**：检索热词TopN、命中率、拒绝率、知识点热度排行，Celery队列状态、向量库容量、Token消耗日志 | 1. **认证服务**：JWT签发/校验，无状态，用户身份识别，个人会话历史持久化<br>2. **异步解析流水线**：前端直传 MinIO（预签名 URL）→ 回调后端 → Celery 触发文档解析/清洗/切分（`llama-index` 解析/切分组件）→ DashScope Embedding → pgvector 入库，支持解析进度查询、失败重试<br>3.**题库向量化（异步）**：全局/批量向量化开关，Celery 异步读取题目表 → DashScope Embedding → 存入向量表，题目更新时标记脏数据，支持增量重新向量化<br />3.  **智能 Agent 对话引擎（基于 LangGraph+ ReAct）**：Agent 自主决策，RAG/检索，联网搜索等作为 Tool 按需调用。<br />4.**检索工具流程**：将用户提问重构为陈述句和疑问句，分别对知识点向量库和题目向量库执行并行混合检索，同时原始问题也分别检索两类库；对检索结果按相似度阈值过滤后，将题目库命中的题目通过题目-知识点多对多关联映射到知识点，并与直接命中的知识点分数进行加权融合（陈述句、疑问句、原始问题的不同权重可配置），得到每个知识点的综合得分；排序取 TopN 后，使用重排序模型对知识点内容进一步精排，最终输出最相关的知识点列表供生成模型使用，题目仅作为辅助定位的中间结果。<br />5. **流式Trace**：SSE 推送 Agent 每一步决策(思考，执行，观察)，支持中断/重试，断点续传，全链路可追踪：用户输入 → Agent 推理 → 检索调用（含子步骤）→ 最终回答<br>6. **统计与缓存**：RetrievalLog 记录每次实际发生的检索（非每次对话），Redis 缓存高频查询结果、双句重构结果，记录 Agent 决策轨迹（用于调优） |
| **⚡ 非功能性需求** | 1. **低延迟渲染**：SSE打字机效果平滑，无卡顿<br>2. **响应式适配**：PC/移动端一致体验<br>3. **容错降级**：网络抖动支持Trace断点续传，AI异常友好提示<br>4. **隐私安全**：本地缓存脱敏，Token不持久化<br />5.**交互流畅**：操作即时响应，无感知等待<br />6.**视觉审美**：现代级设计风格，简洁专业 | 1. **大文件与容错**：分片上传、进度轮询、解析失败自动重试，网络异常友好提示，支持断点续传（Trace级别）<br>2. **数据可视化与性能**：图表/关系网络渲染高效，万级数据不卡UI，使用虚拟滚动、懒加载、Web Worker 处理大列表<br>3. **操作幂等与并发安全**：防重复导入、向量化开关防并发冲突，所有写操作支持幂等设计（重复提交不产生副作用）<br>4. **视图隔离**：单用户双视图路由守卫<br />5.**交互流畅**：操作即时响应，无感知等待<br />6.**视觉审美**：现代级设计风格，简洁专业 | 1. **流程可控**：Agent 决策链路透明：每次推理（思考、调用 Tool、生成）均可追踪，支持全链路调试：用户输入 → Agent 决策轨迹 → Tool 执行详情 → 最终回答<br>2. **向量性能**：pgvector HNSW 索引，三路混合检索 + Dashscope Rerank 端到端延迟 < 1.5s，Agent 决策额外开销 < 200ms（不含检索和 LLM 生成）<br>3. **一致性**：文档预处理使用 `llama-index` 的解析/切分组件完成文档读取与分块，Embedding / Rerank / LLM 统一直连 `dashscope` SDK，避免封装层行为漂移并保持调用参数、错误处理一致<br>4. **高可用与维护性**：异步解耦：文档解析、题库向量化走 Celery，不阻塞在线服务，流式降级：SSE 断线自动重连，检索超时降级为纯模型回答，连接池复用：数据库、Redis、HTTP 客户端连接池，结构化日志：全链路 Request ID 串联，便于问题排查。 |

---
### 🛠️ 二、技术栈选型（统一推荐）

| 端           | 核心技术栈                                                   | 关键依赖/插件                                                |
| :----------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| **用户端**   | `React 19 + `Vite` + `TypeScript` + `TailwindCSS` | `react-router-dom`、`zustand`（状态）、`EventSource` 原生 SSE、`react-markdown` + `remark-gfm`、`framer-motion`（流畅动画）、`axios`（带自动取消） | `axios` / `fetch`、`EventSource` 或 `sse.js`、`react-markdown` / `markdown-it`、`zustand` / `pinia`（轻量状态）、`framer-motion`（动画过渡） |
| **管理端**   | 同用户端（复用技术栈） + `Ant Design`（组件库）              | `ECharts`（大数量图表）、`react-window`（虚拟滚动）、`react-query`（服务端状态）、`sheetjs`（Excel 解析）、`use-context-selector`（避免无效重渲染） |
| **后端服务** | `FastAPI` + `SQLAlchemy 2.0`（异步） + `Alembic`             | **Agent 编排**：`LangGraph`（ReAct Agent）+ 自定义 Tool<br/>**AI 调用**：`dashscope` API 统一（LLM、Embedding、Rerank）<br/>**向量库**：`pgvector` + `asyncpg` + `psycopg`（二进制）<br/>**异步任务**：`Celery` + `Redis`（broker/result/缓存）<br/>**对象存储**：`minio` + `boto3` 风格 SDK<br/>**JWT**：`python-jose` + `passlib[bcrypt]`<br/>**结构化日志**：`loguru` + `python-json-logger` |

---
### 📦 三、全局架构与部署约束（精简）
| 模块               | 说明                                                         |
| :----------------- | :----------------------------------------------------------- |
| **数据流向**       | 文档上传 → MinIO → Celery Worker（文档解析/清洗/切分 → DashScope Embedding）→ pgvector（知识点向量 + 题目向量）→ 题目-知识点多对多关联表 → Redis（高频查询缓存） |
| **检索链路**       | 用户Query → Agent决策是否需要检索 → 若需要，执行检索Tool：<br/>① 重构为陈述句+疑问句 → ② 三路（原句/陈述/疑问）并行检索知识点库与题目库 → ③ 题目映射到知识点 + 多路加权融合 → ④ Dashscope Rerank精排 → ⑤ 返回TopK知识点 → Agent结合历史记忆生成最终回答（SSE流式推送） |
| **部署方式**       | Docker Compose 一键拉起：`pgvector/pgvector:0.8.2-pg18-trixie` + `redis:latest` + `minio/minio:latest` + `fastapi` + `celery-worker`（+ `celery-beat` 可选），网络桥接，数据卷持久化 |
| **环境管理**       | `.env` 统一配置（`DASHSCOPE_API_KEY`, DB, MinIO, Redis），`uv` 锁依赖 + 虚拟环境，`Alembic` 管理库表迁移（含向量扩展） |
| **反向代理与防护** | 前端 Nginx 统一入口：<br/>\- 代理静态资源与 API 请求（分离路由）<br/>\- 限流：每 IP 每秒 10 次请求（SSE 长连接除外）<br/>\- 安全头：HSTS、X-Frame-Options、X-Content-Type-Options<br/>\- 防 DDoS：`limit_req` + `limit_conn`，可选 `fail2ban` 联动<br/>\- SSL/TLS 终结（生产环境强制 HTTPS） |



> 💡 **核心实施建议**：Agent推理轨迹及检索Tool内部各步骤均返回结构化事件（含 `event_type`, `trace_data`, `is_final`），后端通过SSE逐条推送；前端单一组件消费，按 `event_type` 渲染不同Trace卡片（如“Agent思考”、“检索中”、“重排序”、“生成中”），实现检索过程透明化与最终回答分离渲染。





| 🛠️ 技能名称                        | 📦 应用技术栈                                             | 💡 核心应用说明（本项目场景）                                 | 🚀 性能/工程价值                                              |
| :-------------------------------- | :------------------------------------------------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| **`fastapi-templates`**           | `FastAPI` + `SQLAlchemy 2.0` + `Alembic` + `Pydantic v2` | 采用标准化分层架构 (`api/` `services/` `models/` `core/`)；依赖注入管理 DB/Redis/MinIO 会话；统一异常处理与结构化日志；异步路由全链路 `async/await`。 | 消除样板代码，确保资源自动回收防泄漏；路由级超时控制；依赖注入提升测试覆盖率与代码可维护性。 |
| **`langgraph-fundamentals`**      | `LangGraph` + `Dashscope LLM` + 自定义 Tool              | 使用 `StateGraph` 编排 ReAct Agent；定义 `AgentState`（含 `messages`, `context`, `trace`）；配置 `interrupt_before` 支持调试中断；Tool 节点封装检索/重排/生成。 | 非自主 Agent，决策链路完全可控；状态持久化支持断点续传；避免无限循环；全节点 Trace 可观测。 |
| **`pgvector-semantic-search`**    | `PostgreSQL` + `pgvector` + `asyncpg` + `HNSW`           | 向量列直接映射 ORM；创建 HNSW 索引 (`m=16, ef_construction=64`)；三路 Query 并行检索 + 分数归一化融合；动态调优 `hnsw.ef_search`。 | 向量检索延迟 `<50ms`；免去独立向量库运维；支持混合检索（语义+关键词）；内存占用低，扩展性强。 |
| **`typescript-advanced-types`**   | `TypeScript 5+` + `Zod` + `SSE Stream`                   | 严格模式 (`strict: true`)；泛型封装 API Client；判别联合类型定义 SSE 事件流；映射/条件类型处理动态表单与图表配置；零 `any` 规范。 | 编译期拦截 90%+ 运行时错误；SSE 解析类型安全；重构零成本；大幅降低前端崩溃率与维护成本。 |
| **`ui-ux-pro-max`**               | `React 19` + `TailwindCSS` + `Framer Motion` + `Sonner`  | 微交互动画（按钮态/呼吸灯/卡片展开）；骨架屏与乐观更新；暗黑/亮色自适应；ECharts 光泽感配置；无障碍访问支持。 | 感知延迟降低 40%+；60fps 流畅交互；专业级视觉体验；提升用户信任度与停留时长。 |
| **`vercel-react-best-practices`** | `React 19` + `@tanstack/react-query` + 虚拟滚动          | 组件懒加载 (`lazy`+`Suspense`)；重渲染优化 (`memo`/`useCallback`)；服务端状态缓存与预取；`react-window` 处理万级日志/题目列表。 | 主线程零阻塞；首屏包体积 `<150KB`；内存占用稳定；长列表滚动不掉帧，彻底解决 Trace 渲染卡顿。 |
| **`vite`**                        | `Vite` + `Rollup` + `ESBuild` + `HMR`                    | 毫秒级热更新；生产环境自动代码分割、Tree-shaking、资源压缩；环境变量隔离；插件链集成 Markdown/WASM/TS。 | 开发迭代效率提升 3 倍+；生产 TTFB 优化；按需加载管理端重依赖；构建产物极致精简。 |

> 📌 **使用建议**：在代码仓库根目录创建 `SKILLS.md` 或 `ARCHITECTURE.md`，将此表作为**工程规范基准**。所有 PR 需对照此表进行 Code Review，确保技术选型与性能目标严格对齐，杜绝“技术债”累积。
