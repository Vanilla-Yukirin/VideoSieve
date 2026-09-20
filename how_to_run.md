# 如何运行（统一环境变量方案）

> 本文说明单机运行方式。FastAPI 只负责入队与 WebSocket，媒体处理由独立 SQLite
> worker 执行。当前不需要启动 Celery 或 Redis。自动化验证与真实模型内容验收的
> 边界见 `docs/QUALITY.md`。

当前项目建议使用一份根目录 `.env.local` 来管理本地运行配置：

- 前端通过 `apps/web/next.config.js` 的加载逻辑读取根目录 `.env.local`
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
SUMMARY_API_KEY=your-summary-key
SUMMARY_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
SUMMARY_MODEL=qwen-plus
```

VLM（画面描述 + 文字提取）建议至少配置：

- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `VLM_MODEL`

启用最终摘要时还必须配置 `SUMMARY_API_KEY`。摘要 endpoint、模型、提示词与上下文预算
可在系统设置中单独调整；创建 job 时会冻结到非敏感配置快照。VLM 与最终摘要可使用
不同的 key 和模型。

## 2. 初始化 Python 环境（UV）

```powershell
uv python install 3.12
uv venv --python 3.12
uv sync --extra dev
```

版本与当前 `.python-version` 对齐。已有环境应先检查，不要直接重建。
FunASR / PyTorch 目前属于主依赖；`asr_local` extra 为空。
启用真实本地 ASR 时，在启动后端前设置（可写入 `.env.local`）：

```env
VIDEOSIEVE_ASR_PROVIDER=funasr_local
VIDEOSIEVE_ASR_MODEL=FunAudioLLM/Fun-ASR-Nano-2512
VIDEOSIEVE_ASR_HUB=ms
VIDEOSIEVE_ASR_DEVICE=auto
```

模型在首次转写时加载，可能下载文件。真实媒体处理还需核对 FFmpeg/ffprobe 等
外部工具的可用性，具体由下载格式、合并和音频解码路径决定。
未设置 ASR provider 时默认使用真实 `funasr_local`。空值、未知值或 `baseline` 会明确
失败。VLM／摘要缺密钥、调用失败或返回空内容时任务失败，不生成占位结果。启动成功
仍不能视为模型内容验收通过。

## 3. 启动后端（终端 1）

```powershell
uv run python -m uvicorn apps.api.main:app --env-file .env.local --host 127.0.0.1 --port 8000
```

## 4. 启动独立 worker（终端 2）

worker 和 API 必须使用相同的 `VIDEOSIEVE_API_DATA_DIR`：

```powershell
uv run python -m workers.single_host --data-dir runtime/api
```

启动入口持有 `runtime/api/worker.lock`，第二个实例会拒绝启动。`--once` 可用于只领取
一个任务的诊断运行。worker 崩溃或心跳过期会把任务标为 `interrupted`，必须显式恢复，
不会自动重复执行。

## 5. 启动前端（终端 3）

首次安装按已有 npm 锁文件执行：

```powershell
npm --prefix apps/web ci
```

```powershell
npm --prefix apps/web run dev
```

## 6. 浏览器访问

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
  - 最终摘要：`SUMMARY_API_KEY`、`SUMMARY_BASE_URL`、`SUMMARY_MODEL`
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

## 验证

日常检查：

```powershell
uv run python scripts/verify.py --profile integration
```

发布验收必须提供与当前 Git revision 匹配的真实模型证据：

```powershell
uv run python scripts/verify.py --profile release --real-evidence path/to/evidence.json
```

证据格式和人工复核项见 `docs/harness/README.md`。未提供真实证据时，release profile
必须失败，不能把 NOT-RUN 解释为通过。
