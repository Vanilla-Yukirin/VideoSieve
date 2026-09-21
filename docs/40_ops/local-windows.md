# Windows 本机部署

状态：面向一台 Windows 电脑、一个或少量用户的本地进程部署。Web、API 和 worker
是三个独立进程；SQLite 与 workspace 放在本机磁盘。不需要 Redis、Celery、PostgreSQL
或本地 ASR/PyTorch。

## 1. 前置条件

- Git；
- `uv`，并按 `.python-version` 安装 Python 3.12；
- Node.js `>=20.9.0` 和 npm；
- `ffmpeg`、`ffprobe` 可从 `PATH` 执行；
- 若要真正处理视频，可访问一个 CapsWriter WebSocket 服务和所选 VLM/LLM API。

在 PowerShell 中先检查：

```powershell
uv --version
node --version
npm.cmd --version
ffmpeg -version
ffprobe -version
```

## 2. 冷安装

在仓库根目录执行：

```powershell
uv python install 3.12
uv sync --locked --extra dev
npm.cmd --prefix apps/web ci
copy .env.example .env.local
```

编辑 `.env.local`：

1. 必须替换 `APP_SECRET_KEY`；示例值会被 API 拒绝；
2. 保持 `VIDEOSIEVE_API_DATA_DIR=runtime/api`，让 API 和 worker 使用同一数据目录；
3. 保持 `NEXT_PUBLIC_API_ORIGIN=http://127.0.0.1:8000`；
4. 按需设置监听 origin 等部署参数，Web/API 默认保持回环地址；
5. 不在 `.env.local` 填写新 Provider 的 endpoint、model 或 credential。

`APP_SECRET_KEY` 只放 `.env.local`，并与 `runtime/api/` 备份分开保管。在线 Provider
credential 通过 Web 录入后以密文存入 SQLite。不要把任何密钥写进 `NEXT_PUBLIC_*`
变量、截图或日志。

## 3. 启动

打开三个 PowerShell 终端，都停在仓库根目录。

终端 1：

```powershell
uv run python -m uvicorn apps.api.main:app --env-file .env.local --host 127.0.0.1 --port 8000
```

终端 2：

```powershell
uv run python -m workers.single_host --env-file .env.local
```

终端 3：

```powershell
npm.cmd --prefix apps/web run dev
```

访问 `http://localhost:3000`。首次进入流程是：

1. 直接进入 Provider 引导；
2. 配置 CapsWriter endpoint，以及按需填写选填 Token；
3. 配置画面摘要 VLM 的 endpoint、model 与 API key；
4. 按需配置全文摘要 LLM；
5. 保存后使用一段短视频完成真实验收。

要用生产模式运行前端：

```powershell
npm.cmd --prefix apps/web run build
npm.cmd --prefix apps/web run start
```

## 4. 本机使用边界

- 产品内没有账号、登录、游客或 session；Web/API 默认只绑定 loopback。yukirin-server
  等远程访问必须通过 Tailscale、Yukirin Gateway 或认证反向代理，不能直接把 Web/API
  端口开放到公网或不受控局域网；
- 只启动一个 worker。第二个实例会被 `runtime/api/worker.lock` 拒绝；
- `runtime/api/infra.db`、同目录 WAL/SHM 和 `runtime/api/workspaces/` 是持久数据，不要当缓存删除；
- 浏览器清理数据后仍可从 SQLite 重新加载项目；
- Windows 休眠、关机或强制结束 worker 会中断运行中的任务。确认旧进程已退出后，在页面显式恢复；
- 在线 Provider 配置和 credential 均在 Web 修改；
- 创建 job 时会冻结配置，设置变更只影响之后创建的 job；
- 环境中的 `QWEN_API_KEY`、`SUMMARY_API_KEY` 或 `CAPSWRITER_TOKEN` 只兼容旧 job
  snapshot；新配置不应依赖它们；
- API `/healthz` 只证明 API 进程存活，不证明 worker、CapsWriter 或模型服务可用。

当前尚未实现独立的 Provider 连接测试。页面显示已配置只证明字段与 credential 已保存，
不证明 endpoint 可达、鉴权有效或模型存在。

不配置真实 provider 时，界面、项目管理、上传和队列仍可启动，但视频任务会在缺少配置
的阶段明确失败。项目不会用 mock 或占位文本假装成功。

## 5. 验证与备份

代码质量与进程集成检查：

```powershell
uv run python scripts/verify.py --profile integration
```

开始日常使用前，再用一段短视频实际跑通 CapsWriter、VLM 和摘要服务。自动测试无法证明
外部模型地址、密钥、内容质量或长视频稳定性。

备份时同时保存 SQLite 和 workspace。运行中不要只复制 `infra.db` 主文件，因为 WAL 中
可能还有未合并事务；使用 SQLite backup API，或先正常停止 API/worker 后整体备份
`runtime/api/`。
