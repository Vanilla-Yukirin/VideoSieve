# VideoSieve 部署指南

## 本地开发部署

### 前置要求

- **Python 3.10+**
- **Node.js 18+**
- **FFmpeg** (音频处理)

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
从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并添加到 PATH。

### 后端部署

1. **克隆项目**
```bash
git clone https://github.com/YOUR_USERNAME/VideoSieve.git
cd VideoSieve/backend
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
```bash
cp .env.example .env
```

编辑 `.env` 文件：
```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
DATABASE_URL=sqlite+aiosqlite:///./data/db/videosieve.db
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
MAX_CONCURRENT_TASKS=5
AUDIO_OUTPUT_DIR=./data/audio
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

5. **启动后端**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端将运行在 `http://localhost:8000`。

### 前端部署

1. **进入前端目录**
```bash
cd ../frontend
```

2. **安装依赖**
```bash
npm install
```

3. **配置环境变量**
```bash
cp .env.example .env.local
```

编辑 `.env.local`：
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
NEXT_TELEMETRY_DISABLED=1
```

4. **启动开发服务器**
```bash
npm run dev
```

前端将运行在 `http://localhost:3000`。

5. **构建生产版本**
```bash
npm run build
npm start
```

## Docker 部署

### 使用 Docker Compose

1. **配置环境变量**

在项目根目录创建 `.env` 文件：
```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

2. **启动服务**
```bash
docker-compose up -d
```

3. **查看日志**
```bash
docker-compose logs -f
```

4. **停止服务**
```bash
docker-compose down
```

服务访问：
- 前端: `http://localhost:3000`
- 后端: `http://localhost:8000`
- API 文档: `http://localhost:8000/docs`

### 单独构建 Docker 镜像

#### 后端
```bash
cd backend
docker build -t videosieve-backend .
docker run -d -p 8000:8000 \
  -e OPENAI_API_KEY=your_key \
  -v $(pwd)/data:/app/data \
  videosieve-backend
```

#### 前端
```bash
cd frontend
docker build -t videosieve-frontend .
docker run -d -p 3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:8000/api \
  videosieve-frontend
```

## 生产环境部署

### 服务器要求

- **操作系统**: Ubuntu 20.04+ / CentOS 8+
- **CPU**: 2 核心以上
- **内存**: 4GB+ (推荐 8GB)
- **存储**: 20GB+
- **软件**:
  - Python 3.10+
  - Node.js 18+
  - FFmpeg
  - pm2 (进程管理)
  - Nginx (反向代理，可选)

### 手动部署

#### 1. 准备服务器

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装依赖
sudo apt install -y python3.10 python3-pip python3-venv nodejs npm ffmpeg

# 安装 pm2
sudo npm install -g pm2
```

#### 2. 部署后端

```bash
# 克隆项目
cd /var/www
sudo git clone https://github.com/YOUR_USERNAME/VideoSieve.git videosieve
cd videosieve/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
sudo nano .env
# 填写配置...

# 创建数据目录
mkdir -p data/db data/audio

# 使用 pm2 启动
pm2 start "venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000" --name videosieve-backend
pm2 save
pm2 startup
```

#### 3. 部署前端

```bash
cd ../frontend

# 安装依赖
npm ci

# 配置环境变量
sudo nano .env.production
# 填写配置...

# 构建
npm run build

# 使用 pm2 启动
pm2 start npm --name videosieve-frontend -- start
pm2 save
```

#### 4. 配置 Nginx (可选)

创建 Nginx 配置文件 `/etc/nginx/sites-available/videosieve`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # 后端 API
    location /api {
        proxy_pass http://localhost:8000/api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE 特殊配置
    location /api/tasks {
        proxy_pass http://localhost:8000/api/tasks;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 24h;
        chunked_transfer_encoding off;
    }
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/videosieve /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### GitHub Actions 自动部署

项目已配置 GitHub Actions 工作流 (`.github/workflows/deploy.yml`)。

#### 配置 Secrets

在 GitHub 仓库设置中添加以下 Secrets：

- `SERVER_HOST`: 服务器 IP 地址
- `SERVER_USER`: SSH 用户名
- `SSH_PRIVATE_KEY`: SSH 私钥
- `OPENAI_API_KEY`: OpenAI API 密钥
- `OPENAI_BASE_URL`: OpenAI API 地址
- `OPENAI_MODEL`: 模型名称 (可选)

#### 初次部署

首次部署需要手动设置：

```bash
# 在服务器上
cd /var/www
sudo mkdir videosieve
sudo chown $USER:$USER videosieve
git clone https://github.com/YOUR_USERNAME/VideoSieve.git videosieve
cd videosieve

# 后续推送将自动部署
```

#### 自动部署流程

1. 推送代码到 `main` 分支
2. GitHub Actions 自动触发
3. 通过 SSH 连接服务器
4. 拉取最新代码
5. 安装依赖
6. 重启服务

查看部署日志：
```bash
# 在服务器上
pm2 logs
```

## 监控和维护

### 查看日志

```bash
# pm2 日志
pm2 logs videosieve-backend
pm2 logs videosieve-frontend

# 实时日志
pm2 logs --lines 100
```

### 重启服务

```bash
# 重启后端
pm2 restart videosieve-backend

# 重启前端
pm2 restart videosieve-frontend

# 重启所有
pm2 restart all
```

### 停止服务

```bash
pm2 stop videosieve-backend
pm2 stop videosieve-frontend
```

### 数据备份

```bash
# 备份数据库
cd /var/www/videosieve/backend
cp -r data data_backup_$(date +%Y%m%d)

# 定期备份 (crontab)
0 2 * * * cd /var/www/videosieve/backend && cp -r data /backups/videosieve_$(date +\%Y\%m\%d)
```

### 清理音频文件

定期清理旧音频文件以节省空间：

```bash
# 删除 7 天前的音频文件
find /var/www/videosieve/backend/data/audio -type f -mtime +7 -delete
```

## 故障排查

### 后端无法启动

1. 检查 Python 版本: `python3 --version`
2. 检查依赖: `pip list`
3. 检查环境变量: `cat .env`
4. 查看日志: `pm2 logs videosieve-backend`

### 前端无法访问

1. 检查 Node.js 版本: `node --version`
2. 检查进程: `pm2 list`
3. 查看日志: `pm2 logs videosieve-frontend`

### SSE 连接失败

1. 检查 CORS 配置
2. 检查 Nginx 配置（如果使用）
3. 查看浏览器控制台错误

### 转录失败

1. 检查 FFmpeg: `ffmpeg -version`
2. 检查音频文件是否存在
3. 查看后端日志

### 磁盘空间不足

1. 清理旧音频文件
2. 清理旧任务记录
3. 使用 `du -sh data/` 检查占用

## 性能优化

### Whisper 模型选择

根据服务器性能选择：
- `tiny`: 最快，1GB RAM
- `base`: 快速，1GB RAM (默认)
- `small`: 中等，2GB RAM
- `medium`: 较慢，5GB RAM
- `large`: 最慢，10GB RAM

### 并发任务数

调整 `MAX_CONCURRENT_TASKS` 根据服务器性能。

### 数据库优化

生产环境可迁移到 PostgreSQL：
```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/videosieve
```

## 安全建议

1. 使用 HTTPS (Let's Encrypt)
2. 配置防火墙
3. 定期更新依赖
4. 限制 API 访问频率
5. 备份敏感数据

## 扩展部署

### 多服务器部署

1. 使用 Redis 共享任务队列
2. 使用 PostgreSQL 共享数据库
3. 使用负载均衡器分发请求
4. 音频文件存储到对象存储 (S3/OSS)

### Kubernetes 部署

TODO: 提供 Kubernetes 配置文件

## 支持

遇到问题？
- 查看 [GitHub Issues](https://github.com/YOUR_USERNAME/VideoSieve/issues)
- 阅读 [API 文档](API.md)
- 阅读 [架构文档](ARCHITECTURE.md)
