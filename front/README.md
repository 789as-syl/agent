# 知识库问答系统 - 前端

## 项目概述

这是一个完整的知识库问答系统前端项目，包含用户端和管理端两个独立应用。

### 技术栈

- **框架**: React 19 + TypeScript
- **构建工具**: Vite
- **状态管理**: Zustand
- **路由**: React Router v7
- **样式**: Tailwind CSS
- **UI 组件**: Lucide React (用户端) / Ant Design (管理端)
- **图表**: ECharts
- **Markdown 渲染**: React Markdown + remark-gfm
- **动画**: Framer Motion
- **提示**: Sonner
- **HTTP 客户端**: Axios

## 项目结构

```
front/
├── client/                 # 用户端应用
│   ├── src/
│   │   ├── components/     # 通用组件
│   │   ├── pages/          # 页面组件
│   │   ├── store/          # Zustand 状态管理
│   │   ├── App.tsx         # 主应用组件
│   │   ├── main.tsx        # 入口文件
│   │   └── index.css       # 全局样式
│   └── package.json
├── admin/                  # 管理端应用
│   ├── src/
│   │   ├── components/     # 通用组件
│   │   ├── pages/          # 页面组件
│   │   ├── store/          # Zustand 状态管理
│   │   ├── App.tsx         # 主应用组件
│   │   ├── main.tsx        # 入口文件
│   │   └── index.css       # 全局样式
│   └── package.json
└── shared/                 # 共享代码
    ├── api/                # API 客户端
    └── types/              # TypeScript 类型定义
```

## 环境变量

### 用户端 (client/.env)

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 管理端 (admin/.env)

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 开发指南

### 安装依赖

```bash
# 安装用户端依赖
cd front/client
npm install

# 安装管理端依赖
cd ../admin
npm install
```

### 启动开发服务器

```bash
# 启动用户端 (默认端口 5173)
cd front/client
npm run dev

# 启动管理端 (默认端口 5174)
cd ../admin
npm run dev
```

### 构建生产版本

```bash
# 构建用户端
cd front/client
npm run build

# 构建管理端
cd ../admin
npm run build
```

## 用户端功能

### 1. 认证模块
- 用户注册 / 登录
- JWT Token 认证
- Token 自动刷新
- 安全退出

### 2. 会话管理
- 会话列表展示
- 创建新会话
- 重命名会话
- 删除会话
- 会话历史记录

### 3. 聊天对话
- 实时流式对话 (SSE)
- Markdown 渲染
- 打字机效果
- 消息中断
- 消息重试
- 响应式布局

### 4. Trace 可视化
- Agent 思考过程展示
- 工具调用详情
- 事件时间线
- 可折叠侧边栏

## 管理端功能

### 1. 数据看板
- 今日搜索统计
- 检索命中率
- 平均响应时间
- 搜索趋势图
- 检索结果分布图
- 知识点热度图

### 2. 知识库管理
- 文档上传 (预签名 URL)
- 知识点列表
- 知识点搜索
- 重新索引
- 文档状态管理

### 3. 题库管理
- 题目 CRUD
- 批量导入 (JSON)
- 向量化触发
- 题目类型管理
- 知识点关联

### 4. 知识图谱
- ECharts 关系图
- 节点拖拽缩放
- 知识点-题目关联展示
- 统计卡片

## API 接口

所有 API 接口严格遵循 `docs/API_DOCUMENTATION.md` 规范。

### 基础路径
- 用户端和管理端共用 API: `/api/v1`

### 认证方式
- Bearer Token (JWT)
- Refresh Token 通过 HttpOnly Cookie 自动携带

## 状态管理

### 用户端 Store (front/client/src/store/index.ts)
- `useAuthStore`: 认证状态
- `useConversationStore`: 会话和消息
- `useChatStore`: 聊天运行和 Trace
- `useGlobalStore`: 全局状态

### 管理端 Store (front/admin/src/store/index.ts)
- `useAdminAuthStore`: 管理员认证
- `useKnowledgeStore`: 知识库管理
- `useQuestionStore`: 题库管理
- `useAdminGlobalStore`: 全局状态

## 性能优化

- 组件使用 React.memo 优化
- 虚拟滚动 (react-window)
- 图片懒加载
- 路由懒加载
- Zustand 状态分片

## 浏览器支持

- Chrome (推荐)
- Firefox
- Safari
- Edge

## 许可证

MIT
