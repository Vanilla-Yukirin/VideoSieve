# VideoSieve 质量与验收入口

本文件是仓库质量门槛的入口。具体命令、分层和真实模型证据格式见
[harness/README.md](harness/README.md)。

质量结论只有三种：

- `PASS`：检查实际执行且全部满足。
- `FAIL`：检查执行失败、无测试被收集，或出现任何 skip。
- `NOT-RUN`：检查没有执行。必需门槛中的 `NOT-RUN` 与失败等价。

仓库不使用累计分数抵消关键错误。ASR、画面理解、全文总结、任务领取、控制确认、
崩溃恢复和 WebSocket 重连中的任一关键门槛失败，当前层级就不能通过。

开发时运行：

```powershell
uv run python scripts/verify.py --profile quick
uv run python scripts/verify.py --profile integration
```

裸 `uv run pytest` 会执行 unit、contract 和 integration Python 测试，但不会执行前端、
静态检查或真实模型验收，因此不能代替 harness。

Ruff 排除 `packages/asr/vendor` 和 `tests/funasr_bug_validation`：两处是上游派生代码或
需要真实 GPU/音频的手工复现脚本，不属于维护中的应用与自动测试 gate。普通 unit、
contract 和 integration 套件仍全部进入 Ruff 与 pytest。

准备发布时必须保证所有 tracked 文件与 `HEAD` 一致，并提供与当前 Git revision 一致的
真实模型验收记录：

```powershell
uv run python scripts/verify.py --profile release `
  --real-evidence D:\evidence\videosieve-real-model.json
```

release 会重新计算输入媒体和三类模型产物的 SHA-256，以 `ffprobe` 复核媒体时长，并要求
每个模型阶段记录 provider、model 以及 request ID 或同一次验收的 run ID。仅填写声明、
仅指向非空文件或使用名称含 `test`/`mock`/`placeholder` 的配置都不能通过。

旧的人工打分表只能用于视觉体验讨论，不是合并或发布依据。
