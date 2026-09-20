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

准备发布时必须提供与当前 Git revision 一致的真实模型验收记录：

```powershell
uv run python scripts/verify.py --profile release `
  --real-evidence D:\evidence\videosieve-real-model.json
```

旧的人工打分表只能用于视觉体验讨论，不是合并或发布依据。
