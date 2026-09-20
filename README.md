# VideoSieve

把长视频自动转成可读、可回溯的知识资产：转译稿、图文交错笔记、摘要。

## 入口

- 单机重做方案与现状核查：`docs/00_vision/rebuild-plan.md`（方案尚未实施）
- 架构总览：`docs/ARCHITECTURE.md`
- 文档索引：`docs/README.md`
- 当前运行说明：`how_to_run.md`

## 当前状态

项目已有前后端、处理模块和测试，但仍是未完成的原型。当前任务在 API 后台线程
执行，事件总线为内存实现；没有实际运行的 Celery/Redis 链路。最终摘要尚未接入
大模型，ASR 默认模拟结果、画面摘要错误回退等问题详见重做方案。

## 本地开发（UV）

Python 环境统一使用 `uv`；按 `.python-version` 当前使用 Python 3.12：

```powershell
uv python install 3.12
uv venv --python 3.12
uv sync --extra dev
```

常用命令：

```powershell
uv run pytest
uv run ruff check .
uv run mypy apps packages workers
```

当前 FunASR / PyTorch 已在主依赖中，`asr_local` extra 为空，无需额外安装该 extra。
真实转写需在本地配置中显式选择 provider：

```env
VIDEOSIEVE_ASR_PROVIDER=funasr_local
```

模型首次使用时加载，可能触发下载。以上命令来自现有配置，本次文档核查未执行安装或测试。

## 历史版本

- `v0.0.2`：Next.js + FastAPI 架构（已归档）
- `v0.0.1`：初始版本

## License

MIT
