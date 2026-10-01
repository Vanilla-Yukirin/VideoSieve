# 模型预算、完成状态与用量统计验证（2026-10-01）

## 范围与结果

本轮实现官方 OpenAI / Anthropic SDK 传输、可配置输出预算与思考适配、完成状态
检查、有上限的重试，以及任务模型调用 journal 和 WebSocket 用量展示。
可信单机免登录模式和 TS / IPv4 访问方式没有变更。

默认上下文预算为 131072，最大输出为 32768，思考开启，最多额外重试 2 次。
这些参数可在 Provider 编辑弹窗修改；草稿测试读取当前字段，保存与测试独立。
新任务冻结配置，修改 Profile 不会改写已创建任务。

## 自动验证：PASS

运行仓库 `scripts/verify.py` 的 `integration` gates：

| 检查 | 结果 |
| --- | --- |
| `git diff --check` | PASS |
| Ruff | PASS |
| mypy | PASS |
| ESLint（0 warnings） | PASS |
| TypeScript（noEmit） | PASS |
| Python unit / contract | 306 passed，0 skipped |
| Python process integration | 3 passed，0 skipped |
| Jest | 71 passed，0 skipped |
| Next 生产构建 | PASS |

关键测试覆盖 SDK 实际请求格式、三种协议的输出上限、思考参数、停止原因、
有效 JSON 文本仍被截断时的失败、拒绝响应、空响应、有限重试与控制检查。
同时覆盖失败请求用量保留、journal 断尾恢复、并发 frame 回调独立读取 SQLite、
任务快照配置冻结，以及 Web 草稿预算编辑和用量事件的版本／游标处理。

流水线测试使用真实生产 adapter 和合成 SDK transport，验证截断耗尽后任务失败，
不发布最终 readiness manifest。它们不等于真实视频验收。

## 真实最小请求：PASS

只读使用本机数据库已有配置和加密凭据，没有修改数据库配置或输出凭据。
在默认 32768 输出上限和开启思考的条件下分别请求一次文本和一次已有教程关键帧；
最小测试关闭额外重试，超时设为 60 秒。模型为现有 `deepseek-flash` 配置，
协议为 OpenAI Chat Completions。以下值均来自真实响应 `usage`，没有 token 估算：

| 输入 | 停止原因 | 输入 tokens | 输出 tokens | total_tokens | reasoning_tokens | 请求耗时 |
| --- | --- | --- | --- | --- | --- | --- |
| 简短架构材料 | stop | 101 | 236 | 337 | 189 | 1703 ms |
| 教程关键帧 | stop | 1028 | 285 | 1313 | 165 | 2031 ms |

两次响应分别返回 85 和 220 字符的非空文本，缓存计数均为 0，没有返回 request ID。
脱敏最小请求记录位于忽略目录 `runtime/model-budget-acceptance.json`，不提交用户
图片、凭据、API 地址或原始材料。

## 验证边界

- 本轮没有重新跑完整真实视频 ASR / VLM / LLM 流程，也没有重新审查全部内容质量。
- 真实最小请求只证明已有 Chat 兼容服务可接受本轮参数；Responses 与 Anthropic
  的协议验证采用 SDK MockTransport，没有实际服务验收。
- 有效 JSON、正常停止和非空文本不能证明事实正确或完整覆盖全部视频材料。
- 输入预算的 UTF-8 保守检查和分段机制不是用量统计，也不能扩大实际模型窗口。
- 时间记录为客户端单调时钟测量的请求耗时（包含网络），不是服务商推理时间或
  TTFT；并发请求耗时之和不等于任务总耗时。
- 未返回的 usage 字段保留未知；部分已报告小计有标识，历史任务不补算。
  输入、缓存、思考字段在不同协议中的口径不同，不自动相加生成总计。
- `real-model-acceptance` gate 仍为 NOT-RUN。最小请求记录不满足 release profile
  所需的完整视频输入、各阶段产物、覆盖率和人工复核证据。
- 本轮没有更新或重启 yukirin-server 上的部署。

详细契约见 [ADR-0010](../adr/ADR-0010-model-completion-budgets-and-usage.md)、
[配置](../10_system/configuration.md)和[观测](observability.md)。
