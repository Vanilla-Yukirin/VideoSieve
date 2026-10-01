# 模型预算与用量复审修复（2026-10-01）

## 范围

针对 PR #2 的本地独立复审，修复五项可复现问题。保持可信单机免登录模式、
TS / IPv4 访问方式及已创建任务的配置快照，不操作生产数据库或服务器部署。
修复后独立复审还发现 Anthropic 思考用量字段适配遗漏，一并补齐。
此前的[首轮验证记录](model-api-validation-20261001.md)保留为对应版本的历史证据。

## 修复与回归

| 问题 | 当前行为 | 回归边界 |
| --- | --- | --- |
| journal 断在中文 UTF-8 字符中，恢复或快照读取失败 | 二进制逐行解码，损坏行不阻断完整历史；追加前隔开断尾，保留原始字节 | 中文第 1 / 2 字节断点、重启追加、API 快照读取 |
| API 可接受整体摘要实际无法运行的预算 | API / worker 共用预算计算，前端同步校验；整体摘要 context/output 差额至少 8096 | 小一单位拒绝、最小有效值可构造生产摘要服务、小画面预算仍可用；旧配置可读可修，不能测试或创建摘要任务 |
| 关闭 OpenAI 思考只省略参数，服务可能仍默认思考 | 标准适配显式发送 effort `none`；非思考模型单独选择 legacy，禁止启用思考 | Chat / Responses 请求字段、legacy 兼容、不支持 `none` 时失败且不静默回退 |
| VLM 重试绕过 RPM | 每个请求 attempt 共用单次阶段运行的滑动窗口 gate | RPM=1 的重试至少相隔 60 秒；RPM=0 不增加限速等待；等待可取消，耗时不包含等待 |
| pause/cancel 确认提高状态版本后丢弃已完成调用的用量 | 用量按 cursor 和不下降的调用数独立合并，任务版本不倒退 | pause / cancel 并发完成、重复 cursor、较低累计调用数 |
| Anthropic 已报告思考 tokens 却显示未知 | 按协议映射 `output_tokens_details.thinking_tokens`，保留原始 usage；不重复计入 output | 报告正数、0、缺失及兼容字段，OpenAI 原字段不改变 |

小预算的限制来自当前分段算法，不代表服务商模型窗口限制或 token 用量估算。
默认 131072 上下文、32768 输出、开启思考及两次额外重试保持不变。

## 验证

运行 `scripts.verify` 的 `integration` 全部门槛，结果如下。测试使用独立临时目录，
没有读取或覆盖生产数据库。
通过验证的代码收敛在 `efb7ac5`；其后本轮提交仅更新文档。

| 检查 | 结果 |
| --- | --- |
| `git diff --check` | PASS |
| Ruff / mypy | PASS |
| ESLint（0 warnings） / TypeScript（noEmit） | PASS |
| Python unit / contract | 336 passed，0 skipped |
| Python process integration | 3 passed，0 skipped |
| Jest | 77 passed，0 skipped |
| Next 生产构建 | PASS |
| `real-model-acceptance` | NOT-RUN，integration 的非必需项 |

本轮模型 / 画面摘要针对性测试 47 项通过。独立 subagent 复审中，六个相关 Python
文件 109 项和两个 Web 套件 16 项通过；随后新增的 Anthropic 用量 journal 回归
11 项通过，并已包含在最终完整门槛中。脱敏门槛结果保存在忽略目录
`runtime/model-api-review-fixes-gates.json`。

## 验证边界

- 请求格式、截断、重试和限速验证使用生产 adapter 与合成 transport / 时钟，不调用真实 Provider。
- 本轮没有重跑完整真实视频 ASR / VLM / LLM；首轮最小真实请求只属于首轮版本证据。
- 不把模拟测试、正常停止或合法文本等同于内容质量验收。
- `real-model-acceptance` 未执行；没有合并 PR 或更新 yukirin-server 部署。

契约见 [ADR-0010](../adr/ADR-0010-model-completion-budgets-and-usage.md)、
[配置](../10_system/configuration.md)、[事件与 WebSocket](../10_system/events-and-websocket.md)。
