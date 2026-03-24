# 如何运行（统一环境变量方案）

当前项目建议使用一份根目录 `.env.local` 来管理本地运行配置：

- 前端（Next.js）会自动读取 `.env.local`
- 后端（Uvicorn）通过 `--env-file .env.local` 读取同一份配置

## 1. 准备环境变量文件

先复制模板：

```powershell
copy .env.example .env.local
```

然后按需编辑 `.env.local`。

最小必填项：

- `APP_SECRET_KEY`（后端必须，不能为空）
- `NEXT_PUBLIC_API_ORIGIN`（前端访问后端地址）

默认推荐：

```env
APP_SECRET_KEY=dev-secret-change-me
NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000
ENABLE_GUEST_MODE=false
GUEST_ALLOW_COOKIE_INPUT=false
GUEST_JOB_COOLDOWN_SECONDS=120
QWEN_API_KEY=your-key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
VLM_MODEL=qwen3.5-plus
VLM_TIMEOUT_SECONDS=60
```

VLM（画面描述 + 文字提取）建议至少配置：

- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `VLM_MODEL`

## 2. 初始化 Python 环境（UV）

```powershell
uv python install 3.11
uv venv --python 3.11
uv sync --extra dev
```

## 3. 启动后端（终端 1）

```powershell
uv run python -m uvicorn apps.api.main:app --env-file .env.local --host 127.0.0.1 --port 8000
```

## 4. 启动前端（终端 2）

```powershell
npm --prefix apps/web run dev
```

## 5. 浏览器访问

- Web：`http://localhost:3000`
- API：`http://127.0.0.1:8000`

## 配置来源说明

- 本地开发：使用 `.env.local`（不提交 Git）
- 部署环境：使用云平台 / CI 注入的环境变量
- 仓库中仅提交 `.env.example` 作为模板

## 部署说明（CI / GitHub Actions）

- 不要把 `.env.local` 提交到仓库。
- 在部署平台或 GitHub Actions 中配置环境变量：
  - 必填：`APP_SECRET_KEY`
  - 推荐：`NEXT_PUBLIC_API_ORIGIN`
  - 可选：`ENABLE_GUEST_MODE`、`GUEST_ALLOW_COOKIE_INPUT`、`GUEST_JOB_COOLDOWN_SECONDS`、`GUEST_COOKIE_KEY`
  - VLM：`QWEN_API_KEY`、`QWEN_BASE_URL`、`VLM_MODEL`、`VLM_TIMEOUT_SECONDS`
- `NEXT_PUBLIC_*` 变量会暴露到前端浏览器，只能放非敏感配置。

## 常见问题（Windows）

### 0) 为什么不再使用 conda？

- 当前项目统一使用 `uv + .venv`，便于跨机器迁移与依赖锁定。
- 执行 Python 命令时统一用 `uv run ...`。

### 1) 端口绑定失败（例如 8000）

如果出现类似错误：

`[Errno 13] ... bind on address ('127.0.0.1', 8000)`

执行检查：

```powershell
netstat -ano | findstr :8000
netsh interface ipv4 show excludedportrange protocol=tcp
```

说明：

- 如果 8000 在排除端口范围内（例如 `7940-8039`），该端口被 Windows 保留。
- 直接换端口最省事（本方案默认 `8000`）。

### 2) 前端改了环境变量不生效

`NEXT_PUBLIC_*` 变量在前端需要重启开发服务器后生效。改完 `.env.local` 后请重新执行：

```powershell
npm --prefix apps/web run dev
```
