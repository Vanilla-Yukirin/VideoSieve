# VideoSieve

把长视频自动转成可读、可回溯的知识资产：转译稿、图文交错笔记、摘要。

## 入口

- 架构总览：`docs/ARCHITECTURE.md`
- 文档索引：`docs/README.md`

## 本地开发（UV）

Python 环境统一使用 `uv`（不再使用 conda）：

```powershell
uv python install 3.11
uv venv --python 3.11
uv sync --extra dev
```

常用命令：

```powershell
uv run pytest
uv run ruff check .
uv run mypy apps packages workers
```

## 历史版本

- `v0.0.2`：Next.js + FastAPI 架构（已归档）
- `v0.0.1`：初始版本

## License

MIT
