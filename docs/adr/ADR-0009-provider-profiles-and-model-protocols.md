# ADR-0009: Provider Profiles and Model Protocols

Status: Accepted

Date: 2026-09-21

## Context

早期设置页把 ASR、画面摘要和整体摘要各表示成一组全局字符串，并把百炼 Qwen 的
完整 Chat Completions URL 和模型名作为初始值。这会把某一家服务误写成产品默认，无法
表达 OpenAI Responses 或 Anthropic Messages，也无法为同一能力保存多套配置并在任务
创建时选择。

用户需要从 Web 完成配置、测试和运行选择。环境变量继续只负责部署，不应成为在线模型
配置入口。保存成功、真实最小请求成功与真实视频端到端验收必须分开陈述。

## Decision

- SQLite 保存多个 capability-scoped Provider Profile。每个 Profile 包含显示名、能力、
  协议、API 根地址、模型、认证方式、能力参数、revision、默认标记和加密 credential
  reference；读取 API 永不返回 credential 明文。
- 模型协议显式支持 `openai_chat_completions`、`openai_responses` 和
  `anthropic_messages`。UI 保存 API 根地址，通常以 `/v1` 结尾；adapter 分别追加
  `/chat/completions`、`/responses` 或 `/messages`。
- ASR 当前只启用 `capswriter_ws`。阿里云百炼 HTTP ASR 在 UI 中作为禁用的计划项，
  在 adapter、快照和真实样本验收完成前不得显示为可用。
- 首次引导不预填 Qwen、DashScope 或其他厂商模型。官方模板只填协议和官方 API 根地址，
  模型由操作者明确填写。
- Profile 测试发送真实最小请求：CapsWriter 执行官方 `binary` 子协议握手，画面摘要发送
  内置一像素 PNG，整体摘要发送短文本。结果只返回耗时和脱敏状态，不返回上游响应体、
  请求头或 credential。编辑器测试直接使用当前草稿，不先保存；临时 credential 只用于
  当次请求，已有 Profile 的空 credential 输入可只读复用已保存密钥。
- 创建任务时可以分别选择 ASR、画面摘要和整体摘要 Profile。API 将 Profile ID、revision、
  协议、模型、参数和 credential reference 冻结进 job snapshot；后续修改默认项不改变
  已有 job。
- 旧的单配置字段幂等迁移为 Profile，旧 credential reference 保留；历史 snapshot 继续按
  Chat Completions 兼容路径读取。

协议结构以官方文档为准：

- [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat)
- [OpenAI Responses](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [OpenAI vision input](https://developers.openai.com/api/docs/guides/images-vision)
- [Anthropic API overview](https://platform.claude.com/docs/en/api/overview)
- [Anthropic Messages](https://platform.claude.com/docs/en/api/typescript/messages/create)
- [Anthropic vision](https://platform.claude.com/docs/en/build-with-claude/vision)

交互参考 [DeepSeek Harness Provider guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)，
只借鉴协议选择、多 Provider 和运行时选择，不引入其插件框架。

## Consequences

- API、worker 和 Web 必须共享 Profile 枚举与快照字段；新增协议需要同步三处契约和真实
  请求测试。
- 修改 Profile 或 credential 会增加 revision；界面中的一次测试结果只对应当时配置，
  不能当作长期健康状态。
- 当前一个 Profile 对应一种能力和一个模型。跨能力复用同一 Provider 或自动发现模型可
  在后续引入独立 Provider/Model 层时迁移，不阻塞单机多配置使用。
- 最小请求成功只证明该协议、credential、模型和模态在测试时可用，仍不等于真实视频
  经过完整 ASR/VLM/LLM 流水线。
