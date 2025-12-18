# VideoSieve 架构文档

## 系统架构

VideoSieve 采用前后端分离的现代化架构：

```
┌─────────────────┐
│  用户浏览器      │
└────────┬────────┘
         │
         │ HTTP/SSE
         │
┌────────▼────────┐
│  Next.js 前端   │
│  (端口 3000)    │
└────────┬────────┘
         │
         │ REST API / SSE
         │
┌────────▼────────┐      ┌──────────────┐
│  FastAPI 后端   │──────│ SQLite 数据库│
│  (端口 8000)    │      └──────────────┘
└────────┬────────┘
         │
    ┌────┴────┬─────────┬─────────┐
    │         │         │         │
┌───▼───┐ ┌──▼───┐ ┌───▼────┐ ┌──▼──┐
│yt-dlp │ │Whisper│ │OpenAI  │ │Files│
└───────┘ └───────┘ └────────┘ └─────┘
```

## 技术栈

### 前端
- **Next.js 14+**: React 框架，使用 App Router
- **TypeScript**: 类型安全
- **TailwindCSS**: 实用优先的 CSS 框架
- **shadcn/ui**: 高质量 UI 组件库
- **EventSource API**: 实时 SSE 更新

### 后端
- **FastAPI**: 高性能异步 Python Web 框架
- **SQLAlchemy**: ORM 和数据库抽象
- **SQLite + aiosqlite**: 轻量级异步数据库
- **yt-dlp**: 多平台视频下载
- **Faster-Whisper**: 高效音频转录（CPU 优化）
- **OpenAI SDK**: AI 文本处理

## 核心组件

### 后端组件

#### 1. 核心配置 (core/)
- **config.py**: 环境变量管理，使用 Pydantic Settings
- **database.py**: 数据库连接和会话管理

#### 2. 数据模型 (models/)
- **task.py**: Task 数据库模型
  - 状态: pending → downloading → transcribing → processing → completed/failed
  - 存储: URL, 进度, 文件路径, 转录文本, 优化文本, 摘要, 日志

#### 3. API 模式 (schemas/)
- **task.py**: Pydantic 验证和序列化模型

#### 4. 服务层 (services/)
- **downloader.py**: yt-dlp 集成，支持 30+ 平台
- **transcriber.py**: Faster-Whisper 转录，单例模式
- **ai_processor.py**: OpenAI API 调用（优化、摘要）
- **task_queue.py**: 异步任务队列管理
  - Whisper 单线程处理（asyncio.Lock）
  - LLM 并发处理（asyncio.gather）

#### 5. API 路由 (api/)
- **tasks.py**: REST 端点（CRUD 操作）
- **sse.py**: Server-Sent Events 实时更新

### 前端组件

#### 1. 类型定义 (types/)
- **task.ts**: Task 相关 TypeScript 接口

#### 2. 工具库 (lib/)
- **api.ts**: 后端 API 客户端
- **sse.ts**: SSE 连接管理
- **utils.ts**: 通用工具函数

#### 3. UI 组件 (components/)
- **ui/**: shadcn/ui 基础组件
- **TaskForm.tsx**: 视频 URL 提交表单
- **TaskCard.tsx**: 任务卡片，显示进度
- **TaskDetails.tsx**: 任务详情查看

#### 4. 页面 (app/)
- **layout.tsx**: 根布局
- **page.tsx**: 主页，任务列表

## 数据流

### 任务创建流程

1. 用户在前端输入视频 URL
2. POST /api/tasks/ 创建任务
3. 后端创建 Task 记录，状态为 "pending"
4. 将任务加入处理队列
5. 前端连接到 SSE 端点接收实时更新

### 任务处理流程

```
pending
  │
  ├─> downloading (yt-dlp)
  │     └─> 下载音频文件
  │
  ├─> transcribing (Faster-Whisper, 单线程)
  │     └─> 生成转录文本
  │
  ├─> processing (OpenAI, 并发)
  │     ├─> 优化文本
  │     └─> 生成摘要
  │
  └─> completed / failed
```

### SSE 实时更新

1. 前端通过 EventSource 连接到 `/api/tasks/{id}/stream`
2. 后端每次更新任务时，将事件推送到队列
3. SSE 端点从队列读取并推送给客户端
4. 前端更新 UI 显示最新状态
5. 任务完成或失败时，连接自动关闭

## 并发控制

### Whisper 转录
- 使用 `asyncio.Lock` 确保同一时间只有一个转录任务
- 原因: Faster-Whisper 在 CPU 上内存密集，单线程处理更稳定

### AI 处理
- 使用 `asyncio.gather()` 并发执行优化和摘要
- 原因: API 调用 I/O 密集，并发可显著提升速度

### 数据库
- 使用 `AsyncSession` 异步访问
- SQLite 配置 `check_same_thread=False`

## 文件存储

- **数据库**: `data/db/videosieve.db`
- **音频文件**: `data/audio/{task_id}.mp3`
- 删除任务时自动清理关联文件

## 安全性

- CORS 配置限制前端访问
- 环境变量存储敏感信息（API 密钥）
- 文件路径验证防止路径遍历

## 扩展性

### 水平扩展
- 可使用 Redis 替代内存队列
- 数据库可迁移到 PostgreSQL
- 可部署多个 worker 处理任务

### 功能扩展
- 添加翻译功能（已预留接口）
- 支持更多 AI 模型（兼容 OpenAI API）
- 添加用户认证和权限管理

## 性能优化

1. **Whisper 模型选择**
   - 默认使用 `base` 模型
   - 可根据需求选择 tiny/small/medium/large

2. **AI 处理批量化**
   - 使用 `asyncio.gather()` 并发处理

3. **前端优化**
   - Next.js 静态生成和服务端渲染
   - 组件懒加载
   - SSE 自动重连

## 监控和日志

- 任务日志存储在数据库 JSON 字段
- Python logging 模块记录服务器日志
- 前端 console 错误上报
