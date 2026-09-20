# VideoSieve Harness

## 1. 目的

Harness 把文档契约、代码实现、自动测试和真实媒体验收连成一条可复查的证据链。
它首先防止“假成功”：缺少模型配置、供应商失败、空响应、占位文本、仅修改状态标签，
或只生成了一个文件，都不能算任务成功。

统一入口是 `scripts/verify.py`。脚本输出 `PASS`、`FAIL`、`NOT-RUN`，并以进程退出码
表示所有必需门槛是否通过。pytest/Jest 出现 skip 会被改判为 `FAIL`；仓库中的目标契约
不得用 `skip` 或 `xfail` 隐藏未实现行为。

## 2. 分层

| 层级 | 检查内容 | 通过条件 |
| --- | --- | --- |
| 静态 | `git diff --check`、Ruff、mypy、ESLint、TypeScript | 命令实际运行且退出码均为 0 |
| 单元/契约 | Python 单元与契约测试、前端 Jest | 全部通过、收集数大于 0、skip 为 0 |
| 进程级集成 | 两个独立 Python 进程竞争 SQLite 任务；worker 崩溃后的中断与显式恢复；Next.js 生产构建 | 不重复领取，不自动双跑，重启后状态和 attempt 可证明，前端可生成生产构建 |
| 真实模型验收 | 真实视频、真实 ASR/VLM/LLM、保存产物和人工内容复核 | 证据匹配当前 revision，真实 provider 与产物齐全，覆盖视频后段，人工复核全部完成 |

三个 profile：

- `quick`：Python/前端静态检查、Python 单元/契约、前端单元。
- `integration`：`quick` 加进程级集成与 Next.js 生产构建；这是日常完整检查的默认值。
- `release`：`integration` 加真实模型证据；没有证据时结果是必需的 `NOT-RUN`，退出码为 1。

命令：

```powershell
uv run python scripts/verify.py --profile quick
uv run python scripts/verify.py --profile integration
uv run python scripts/verify.py --profile release --real-evidence <evidence.json>
```

## 3. 当前缺陷回归契约

| 编号 | 契约 | 自动证据 |
| --- | --- | --- |
| VS-Q001 | 未设置 ASR provider 时选择真实 `funasr_local`；空值、未知值、`baseline`/`mock` 显式失败 | `tests/unit/test_asr_provider_factory.py` |
| VS-Q002 | VLM 缺密钥、超时、HTTP/网络错误、畸形或空响应均失败，不返回占位成功；批次仅在全部成功后原子发布 | `tests/contract/test_provider_failure_contracts.py` 与 frame-summary 单元测试 |
| VS-Q003 | 两个线程或进程不能领取同一 SQLite 任务 | `tests/contract/test_sqlite_worker_contracts.py`、`tests/integration/test_sqlite_worker_processes.py` |
| VS-Q004 | 控制请求与 worker 确认使用独立 version；请求 pause 不得直接宣称已经暂停 | `tests/contract/test_sqlite_worker_contracts.py` |
| VS-Q005 | 失联 worker 的任务先进入 `interrupted`；必须显式恢复后才能再次领取，attempt 递增 | 同上及进程级集成测试 |
| VS-Q006 | WebSocket 每条消息有持久 cursor；重连按序补发遗漏事件，最后用 snapshot 收敛 | `tests/contract/test_websocket_cursor_contract.py` |
| VS-Q007 | 最终摘要来自真实 LLM，覆盖视频后段，并和原始转写、画面描述分开保存 | release profile 的真实模型证据 |

修改契约时，先更新相应 `docs/10_system/*` 和 ADR，再同步生产代码及这里的测试。删除测试、
放宽断言或把失败改成 skip，不能作为修复手段。

## 4. 真实模型证据

真实模型调用受网络、凭据、模型下载和费用影响，不在普通自动测试里偷偷触发。完成一次
真实验收后，按 `real-model-evidence.example.json` 生成记录，并把三个产物路径指向实际
保存的非空文本/JSONL 文件。证据不得包含 API key、Cookie 或 Authorization header。

验证器会检查：

- `revision` 必须等于当前 `git rev-parse HEAD`；
- 输入视频有 SHA-256 与正时长；
- ASR、画面理解、最终总结都记录真实 provider 和存在的非空产物；
- 产物不能含 `baseline_mock`、offline frame summary 或 placeholder；
- ASR 与总结的来源覆盖至少到视频时长的 80%；
- 转写内容/时间戳、画面描述、最终摘要均已人工抽查。

证据 JSON 是验收索引，不替代原始日志、模型响应和产物。它证明“对哪个版本、哪个输入、
用哪个 provider、检查了什么”，避免把旧结果或 mock 结果当作当前版本通过。
