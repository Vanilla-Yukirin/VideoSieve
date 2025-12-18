# VideoSieve

一个基于 AI 的视频转录、优化、翻译与摘要生成工具。支持从多平台（YouTube、TikTok、Bilibili 等 30+ 平台）下载音频、使用 Faster-Whisper 进行高质量转录、通过 OpenAI 兼容 API 生成智能优化与多语言摘要。

## ✨ 特性

- 🎬 **多平台支持**：支持 YouTube、Bilibili、TikTok 等 30+ 视频平台
- 🎙️ **高质量转录**：使用 Faster-Whisper 进行音频转录，支持简体中文
- 🤖 **AI 智能处理**：自动优化转录文本、生成摘要，支持 OpenAI 兼容 API
- 📊 **实时进度推送**：通过 SSE 实时显示任务进度和日志
- 🔄 **多任务并行**：支持同时处理多个视频任务
- 📱 **响应式设计**：完美适配移动端和桌面端
- 🚀 **现代化架构**：Next.js + FastAPI + SQLite

## 🏗️ 技术栈

### 前端
- **Next.js 14+** (App Router)
- **TypeScript**
- **TailwindCSS + shadcn/ui**
- **SSE (EventSource)** 实时更新

### 后端
- **FastAPI** (Python 3.10+)
- **SQLAlchemy + SQLite**
- **yt-dlp** (支持 30+ 平台)
- **faster-whisper** (CPU 模式)
- **openai** Python SDK
- **asyncio** 异步处理

## 📦 项目结构

```
VideoSieve/
├── frontend/              # Next.js 前端应用
│   ├── src/
│   │   ├── app/          # Next.js 页面
│   │   ├── components/   # React 组件
│   │   ├── lib/          # 工具函数、API 客户端
│   │   └── types/        # TypeScript 类型定义
│   └── package.json
│
├── backend/              # FastAPI 后端服务
│   ├── app/
│   │   ├── api/         # API 路由
│   │   ├── core/        # 核心配置
│   │   ├── models/      # 数据模型
│   │   ├── schemas/     # Pydantic 模型
│   │   ├── services/    # 业务逻辑
│   │   └── main.py      # 应用入口
│   └── requirements.txt
│
├── .github/
│   └── workflows/
│       └── deploy.yml   # GitHub Actions 部署工作流
│
└── README.md
```

## 🚀 快速开始

### 前置要求

- **Python 3.10+**
- **Node.js 18+**
- **FFmpeg** (用于音频处理)

### 安装 FFmpeg

#### macOS
```bash
brew install ffmpeg
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

#### Windows
从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并添加到 PATH

### 后端设置

1. **进入后端目录**

```bash
cd backend
```

2. **创建虚拟环境**

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **安装依赖**

```bash
pip install -r requirements.txt
```

4. **配置环境变量**

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写你的 OpenAI API 密钥：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

5. **启动后端服务**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端服务将运行在 `http://localhost:8000`

### 前端设置

1. **进入前端目录**

```bash
cd frontend
```

2. **安装依赖**

```bash
npm install
```

3. **配置环境变量**

复制 `.env.example` 为 `.env.local`：

```bash
cp .env.example .env.local
```

4. **启动开发服务器**

```bash
npm run dev
```

前端应用将运行在 `http://localhost:3000`

5. **构建生产版本**

```bash
npm run build
npm start
```

## 🐳 Docker 部署

1. **启动所有服务**

```bash
docker-compose up -d
```

2. **查看日志**

```bash
docker-compose logs -f
```

3. **停止服务**

```bash
docker-compose down
```

## 📖 使用说明

1. **打开前端页面** `http://localhost:3000`
2. **粘贴视频链接**（支持 YouTube、Bilibili、TikTok 等）
3. **点击提交**，任务将自动开始处理
4. **实时查看进度**，包括下载、转录、AI 处理等阶段
5. **任务完成后**，查看转录文本、优化文本和摘要

## 🔧 配置说明

### Whisper 模型选择

在 `.env` 中配置 `WHISPER_MODEL`，可选值：
- `tiny` - 最快，准确度最低（~1GB RAM）
- `base` - 快速，准确度较低（~1GB RAM）**【推荐 CPU】**
- `small` - 中等速度，准确度中等（~2GB RAM）
- `medium` - 较慢，准确度较高（~5GB RAM）
- `large` - 最慢，准确度最高（~10GB RAM）

### OpenAI 兼容 API

支持任何 OpenAI 兼容的 API 服务，包括：
- **OpenAI** 官方 API
- **Azure OpenAI**
- **SiliconFlow**
- **月之暗面**（Kimi）
- **OpenAI-HK**
- **DeepSeek**
- **本地 LLM**（如 Ollama、LocalAI）

只需配置 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 即可。

## 🌐 GitHub Actions 部署

本项目包含自动化部署工作流，推送到 `main` 分支时自动部署到服务器。

### 配置 GitHub Secrets

在 GitHub 仓库设置中添加以下 Secrets：

- `SERVER_HOST` - 服务器地址
- `SERVER_USER` - SSH 用户名
- `SSH_PRIVATE_KEY` - SSH 私钥
- `OPENAI_API_KEY` - OpenAI API 密钥
- `OPENAI_BASE_URL` - OpenAI API 地址
- `OPENAI_MODEL` - 使用的模型（可选，默认 gpt-4o-mini）

### 服务器要求

- **Python 3.10+**
- **Node.js 18+**
- **pm2**（进程管理）
- **Nginx**（可选，用于反向代理）

### 服务器准备

```bash
# 安装 pm2
npm install -g pm2

# 克隆项目
cd /var/www
git clone https://github.com/YOUR_USERNAME/VideoSieve.git videosieve
cd videosieve

# 首次手动部署后，后续推送将自动部署
```

## 📝 API 文档

后端服务启动后，访问以下地址查看完整 API 文档：

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### 主要端点

- `POST /api/tasks/` - 创建新任务
- `GET /api/tasks/` - 获取任务列表
- `GET /api/tasks/{task_id}` - 获取任务详情
- `GET /api/tasks/{task_id}/stream` - SSE 实时进度推送
- `DELETE /api/tasks/{task_id}` - 删除任务
- `GET /api/tasks/{task_id}/transcript` - 获取转录文本
- `GET /api/tasks/{task_id}/optimized` - 获取优化文本
- `GET /api/tasks/{task_id}/summary` - 获取摘要

## 🎯 核心功能

### 1. 视频下载
使用 `yt-dlp` 下载视频音频，支持：
- YouTube、Bilibili、TikTok、Twitter 等 30+ 平台
- 自动选择最佳音频质量
- 实时下载进度显示

### 2. 音频转录
使用 `Faster-Whisper` 进行转录：
- 强制简体中文输出
- CPU 优化模式（int8）
- 逐段转录，实时进度更新
- VAD（语音活动检测）过滤静音

### 3. AI 处理
支持并发处理：
- **文本优化**：修正语法、标点、分段
- **摘要生成**：提取核心内容（200-300字）
- **翻译功能**（可选）：翻译成其他语言

### 4. 实时进度
通过 SSE 推送：
- 任务状态更新（pending/downloading/transcribing/processing/completed/failed）
- 进度百分比（0-100%）
- 实时日志信息
- 心跳保持连接

## 🔒 注意事项

1. **Whisper 单任务处理**：同一时间只能处理一个转录任务（使用 asyncio.Lock）
2. **LLM 并发**：多个 AI 处理任务可以并发执行
3. **数据持久化**：任务信息存储在 SQLite 数据库中
4. **文件清理**：删除任务时会自动删除相关音频文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 强大的视频下载工具
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - 高效的 Whisper 实现
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架
- [Next.js](https://nextjs.org/) - React 框架
- [shadcn/ui](https://ui.shadcn.com/) - 精美的 UI 组件库

---

**Made with ❤️ by VideoSieve Team**
