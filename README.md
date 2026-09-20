# VideoSieve

把长视频自动转成可读、可回溯的知识资产：转译稿、图文交错笔记、摘要。

## 入口

- 单机重做方案与迁移记录：`docs/00_vision/rebuild-plan.md`
- 架构总览：`docs/ARCHITECTURE.md`
- 文档索引：`docs/README.md`
- 当前运行说明：`how_to_run.md`

## 当前状态

单机运行时已经改为 FastAPI + SQLite 持久队列 + 独立 Python worker + 本地文件系统，
任务状态与游标事件保存在 SQLite，前端任务状态和控制通过 WebSocket 传输。Celery 与
Redis 只保留在历史设计中，不是运行依赖。

VideoSieve 不内置或下载 ASR 模型。ASR 默认未配置，可在系统设置中选择外部
`CapsWriter（WS）` 并使用官方 WebSocket 协议，Token 为选填项。画面描述和最终摘要
使用真实兼容模型接口。漏配、网络错误和空响应会让任务
明确失败，不会生成 mock 或占位成功。自动化验证已经覆盖队列、
控制、恢复、事件重连和 provider 失败；真实视频与真实模型的内容验收仍需按
`docs/harness/README.md` 留存证据，不能用单元测试代替。

## 本地开发（UV）

Python 环境统一使用 `uv`；按 `.python-version` 当前使用 Python 3.12：

```powershell
uv python install 3.12
uv venv --python 3.12
uv sync --extra dev
```

常用命令：

```powershell
uv run python scripts/verify.py --profile quick
uv run python scripts/verify.py --profile integration
uv run ruff check .
uv run mypy apps packages workers
```

`pyproject.toml` 让裸 `uv run pytest` 覆盖 unit、contract 和 integration Python 测试；
它仍不包含前端、静态检查和真实模型验收。日常完整检查使用上面的 harness 入口。

基础依赖不包含 FunASR、PyTorch、Torchaudio、Transformers 或模型下载器。外部
CapsWriter 可先在系统设置中配置，也可在首次初始化 SQLite 设置前用环境变量提供默认值：

```env
VIDEOSIEVE_ASR_PROVIDER=capswriter
VIDEOSIEVE_ASR_ENDPOINT=ws://capswriter-host:6016
# CAPSWRITER_TOKEN=only-if-your-server-requires-it
```

worker 只连接外部服务，音频规范化仍依赖 FFmpeg。完整启动与验证命令见
`how_to_run.md` 和 `docs/QUALITY.md`。

## 历史版本

- `v0.0.2`：Next.js + FastAPI 架构（已归档）
- `v0.0.1`：初始版本

## License

MIT
