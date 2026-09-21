# 如何运行（单机部署配置 + 网页 Provider 配置）

> 本文说明单机运行方式。FastAPI 只负责入队与 WebSocket，媒体处理由独立 SQLite
> worker 执行。当前不需要启动 Celery 或 Redis。自动化验证与真实模型内容验收的
> 边界见 `docs/QUALITY.md`。

当前项目建议使用一份根目录 `.env.local` 管理进程启动所需的部署配置：

- 前端通过 `apps/web/next.config.js` 的加载逻辑读取根目录 `.env.local`
- 后端（Uvicorn）通过 `--env-file .env.local` 读取同一份配置
- worker 通过自身的 `--env-file` 参数读取同一份配置（默认也是 `.env.local`）

## 1. 准备环境变量文件

先复制模板：

```powershell
copy .env.example .env.local
```

然后编辑 `.env.local`。模板中的 `APP_SECRET_KEY` 示例值会被后端拒绝，必须换成随机、
不可公开的值。

最小必填项：

- `APP_SECRET_KEY`（后端必须，不能为空）
- `NEXT_PUBLIC_API_ORIGIN`（前端访问后端地址）

默认推荐：

```env
APP_SECRET_KEY=replace-with-a-long-random-value
NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000
```

在线 ASR、画面描述 VLM 和全文摘要 LLM 的 endpoint、model 与 credential 不属于部署
环境变量。首次启动后在网页 Provider 引导中填写；credential 经 `APP_SECRET_KEY` 加密
持久化，API 不会把明文返回浏览器。创建 job 时只把非敏感配置与 credential reference
冻结到快照。VLM 与全文摘要可以使用不同的 endpoint、key 和模型。

## 2. 初始化 Python 环境（UV）

```powershell
uv python install 3.12
uv venv --python 3.12
uv sync --extra dev
```

版本与当前 `.python-version` 对齐。已有环境应先检查，不要直接重建。基础安装不包含
FunASR、PyTorch、Torchaudio 或 Transformers，也不会下载 ASR 模型。

ASR 默认是 `unconfigured`。在 Web 的 Provider 设置中选择“CapsWriter（WS）”，填写
`ws://` 或 `wss://` endpoint；原版 CapsWriter 不要求 Token，只有自建服务启用鉴权时
才填写 Token。适配器使用上游原版根 WebSocket 协议。

`CAPSWRITER_TOKEN`、`QWEN_API_KEY` 和 `SUMMARY_API_KEY` 环境变量只为仍引用这些
credential name 的旧不可变 job snapshot 保留。新安装和新配置不要依赖它们。

WebSocket 适配器使用 FFmpeg 把输入转为 16 kHz、单声道、float32 音频流，因此 worker
主机仍必须可执行 FFmpeg/ffprobe。未配置、未知 provider、连接失败或空响应都会明确
失败。VLM／摘要缺密钥、调用失败或返回空内容时同样失败，不生成占位结果。启动成功
仍不能视为模型内容验收通过。

## 3. 一条命令启动完整本地服务

```powershell
uv run python scripts/run_local.py
```

启动器会在同一个终端内：

- 检查 `.env.local`、`APP_SECRET_KEY`、Python/Node/npm、FFmpeg/ffprobe 和端口占用；
- `node_modules` 缺失或锁文件更新时自动执行 `npm ci`；
- 首次运行或 Web 源码、配置、`.env.local` 更新后自动执行生产构建；
- 分别启动 API、独立 worker 和生产 Next.js Web，并用 `[api]`、`[worker]`、`[web]`
  前缀汇总日志；
- 等待 API 与 Web 就绪，任何子进程意外退出时停止整组进程；
- 收到一次 `Ctrl+C` 后停止全部子进程及其进程树。

只检查环境、不启动或构建：

```powershell
uv run python scripts/run_local.py --check-only
```

需要无条件重新构建 Web 时使用 `--force-build`。启动入口仍持有
`runtime/api/worker.lock`，因此已有手动 worker 未关闭时，统一启动器会明确失败并停止整组
进程。worker 崩溃或心跳过期会把任务标为 `interrupted`，必须显式恢复，不会自动重复执行。

三个组件仍是相互隔离的进程，但不再要求打开三个终端。实际只有两个本机监听端口：
Web 使用 `3000`，API 与任务 WebSocket 共用 `8000`；worker 不监听任何网络端口。Next.js
负责服务页面和把 `/api/*` 代理给 FastAPI，所以不能在不增加额外反向代理层的情况下把两个
监听端口直接合并。

如需单独诊断，原始入口仍可直接运行：

```powershell
uv run python -m uvicorn apps.api.main:app --env-file .env.local --host 127.0.0.1 --port 8000
uv run python -m workers.single_host --env-file .env.local
npm.cmd --prefix apps/web run start
```

## 4. 浏览器访问

- Web：`http://localhost:3000`
- API 健康检查：`http://127.0.0.1:8000/healthz`

日常只打开 Web 地址。FastAPI 没有首页，因此浏览器直接访问
`http://127.0.0.1:8000/` 返回 `404 Not Found` 是正常行为。

首次进入的推荐流程：

1. 直接进入 Provider 引导，配置 CapsWriter；
2. 配置画面描述 VLM 的 endpoint、model 和 API key；
3. 按需配置全文摘要 LLM；
4. 保存后用一段短视频做真实验收。

当前尚未实现独立的 Provider 连接测试。页面显示“已配置”只表示字段和 credential 已
保存，不表示 endpoint 可达、鉴权有效或模型存在；真实短视频成功并人工检查内容，才是
端到端验收。

## 配置来源说明

- 本地开发：使用 `.env.local`（不提交 Git）
- 部署环境：使用云平台 / CI 注入的环境变量
- 仓库中仅提交 `.env.example` 作为模板

## 部署说明（CI / GitHub Actions）

- 不要把 `.env.local` 提交到仓库。
- 在部署平台或 GitHub Actions 中配置环境变量：
  - 必填：`APP_SECRET_KEY`
  - 推荐：`NEXT_PUBLIC_API_ORIGIN`
- 在线 Provider 的 endpoint、model 与 credential 在 Web 中配置，不放入新部署的环境变量。
- 仅当恢复旧 job snapshot 时，才按其 credential name 临时提供旧环境变量。
- `NEXT_PUBLIC_*` 变量会暴露到前端浏览器，只能放非敏感配置。

VideoSieve 采用 single-host trusted mode，产品内没有账号、登录、游客或会话鉴权。Web 与
API 默认只绑定回环地址。若从 yukirin-server 等远程主机访问，必须通过 Tailscale、
Yukirin Gateway 或带认证的反向代理建立外层访问控制；不要把 Web/API 直接开放到公网或
不受控的局域网入口。无登录不代表公开访问安全。

## 常见问题（Windows）

### 0) 为什么不再使用 conda？

- 当前项目统一使用 `uv + .venv`，便于跨机器迁移与依赖锁定。
- 执行 Python 命令时统一用 `uv run ...`。

### 1) 端口绑定失败（例如 8000）

如果出现类似错误：

`[Errno 13] ... bind on address ('127.0.0.1', 8000)`，或启动器报告端口已占用。

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
npm.cmd --prefix apps/web run dev
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
