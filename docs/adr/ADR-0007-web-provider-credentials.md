# ADR-0007: Web-managed Provider Credentials

Status: Accepted

Date: 2026-09-21

## Context

VideoSieve 面向单机个人／少量用户。要求新用户先编辑 `.env.local` 才能配置在线 ASR、
VLM 和 LLM，会把产品设置与部署设置混在一起，也无法在首次使用流程中清楚展示缺失项。
Provider credential 不能进入浏览器读响应、普通 SQLite settings、job snapshot、日志、事件
或产物。

已有 job snapshot 可能通过 credential name 引用 `CAPSWRITER_TOKEN`、`QWEN_API_KEY`
或 `SUMMARY_API_KEY`，迁移时需要保留受限兼容路径。

## Decision

- `APP_SECRET_KEY`、数据目录、监听地址／端口、Web origin 和进程参数继续作为部署配置；
- 在线 Provider 的 endpoint、model、参数与 credential 由管理员在 Web 中设置；
- Provider credential 使用由 `APP_SECRET_KEY` 派生的密钥加密后持久化；读取 API 只返回
  是否已配置，替换与清除使用显式 write-only 字段；
- job snapshot 冻结非敏感配置与 credential reference，worker 按 reference 解密；
- 环境 Provider credential 只兼容缺少新 credential-reference 字段的旧 snapshot，不是新
  安装或新 job 的回退配置；
- 首次使用流程为创建管理员账号后进入 Provider 引导；总体摘要可以明确跳过；
- `configured`、`reachable`、`verified` 与真实视频 E2E 是不同状态。

## Verification Boundary

当前没有独立 Provider 连接测试。保存设置最多证明 `configured`，不能声称 endpoint
可达、鉴权有效、模型支持所需模态，或真实视频链路已通过。真实 E2E 仍需使用真实视频、
真实 ASR/VLM/LLM，并检查产物与内容。

## Consequences

- API 与 worker 必须使用相同的 `APP_SECRET_KEY`，备份时需把密钥与 SQLite 数据分开保护；
- 轮换 `APP_SECRET_KEY` 前必须重加密 credential；直接替换会使已有密文不可读；
- 浏览器不需要读取旧 credential，空输入表示保留，清除必须显式选择；
- 旧 snapshot 的环境兼容分支需要与新 snapshot 的“credential 缺失”严格区分，避免环境
  变量重新成为新用户的隐藏配置路径。
