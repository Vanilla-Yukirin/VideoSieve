# Configuration

状态：在线 Provider 的加密 credential vault、多 Profile、job credential reference、
worker 解析路径、首次 Provider 引导和真实最小测试已实现。真实视频经过完整 provider
链路的端到端验收仍未执行。

## 1. 配置分层

### Deployment configuration

由环境变量或受保护的运行配置提供，只描述进程启动和本机部署边界：

- `APP_SECRET_KEY`，用于 SQLite 中敏感值的加密根密钥；它不是用户会话或访问令牌；
- SQLite 文件路径、workspace 根目录；
- API/Web 的监听地址、端口与允许 origin；
- worker 轮询、心跳、busy timeout 等运行参数。

在线 Provider 的 endpoint、model 与 credential 不属于新部署环境配置。旧环境 credential
变量只用于兼容已经冻结并引用相应名称的旧 job snapshot。

### System settings

保存在 SQLite，表示操作者可调整的默认值和产品开关。在线 ASR、frame-summary VLM 和
overall-summary LLM 使用多个 capability-scoped Provider Profile；endpoint、protocol、
model、参数与 credential 均从 Web 管理。credential
使用由 `APP_SECRET_KEY` 派生的密钥加密，读取 API 只返回是否已配置，不返回明文。

首次启动流程为：Provider 引导 -> 配置所需能力 -> 创建任务。产品内没有账号、登录、
游客或会话；环境 provider 变量不得成为新用户必须理解的隐藏步骤。

### Job snapshot

创建 job 时冻结不可变配置，保存到
`jobs/{job_id}/meta/config.snapshot.json` 并记录内容哈希。worker 整个 attempt 只读取
该快照和受保护的 secret reference，不读取当前 UI 状态或可变 system settings。

优先级为：能力默认 Profile -> 创建 job 的 Profile 选择 -> 不可变 job snapshot。执行开始
后，操作者修改 Profile 只影响以后创建的 job。

## 2. Snapshot 必须覆盖的内容

- ingest 来源引用、格式选择、cookie secret reference；
- ASR provider、WebSocket endpoint、语言、上下文、超时、热词和 credential name；
- keyframe 策略、阈值和采样参数；
- frame-summary provider、模型、base URL 标识、提示词版本和参数；
- clean transcript / notes / overall summary 的 provider、模型、提示词版本和参数；
- fusion、输出和阶段启用规则；
- schema version、创建时间、来源 settings version 和整体内容哈希。

快照只保存 `secret_ref` 或 provider credential name，不保存 API key、cookie 明文或 token。
worker 解析 secret 后不得把值写回快照、事件或错误。

## 3. 三类模型能力必须分开

| Capability | Required selection | Missing/failure behavior |
| --- | --- | --- |
| ASR | 显式外部 provider；当前实现 CapsWriter 官方 WebSocket 协议 | 未配置、未知 provider、FFmpeg 或远端服务失败时明确失败，不回退 mock |
| Frame summary | 显式视觉模型和凭据引用 | 缺 key、超时、鉴权、空／畸形响应明确失败，不生成占位描述 |
| Overall summary | 独立 LLM、提示词版本和上下文预算 | 必须实际总结完整材料，不允许截取／拼接片段冒充摘要 |

测试中的 fake/mock 由依赖注入提供，不能成为生产配置默认值或未知 provider 的兜底。
设置页选择 provider 和协议，transport 由 adapter 决定。当前 `CapsWriter（WS）` 固定使用
官方 WebSocket；阿里云百炼 HTTP ASR 仅显示为禁用的计划项，在 adapter 和真实样本验收
完成前不增加伪可用选项。

模型 Profile 显式选择 OpenAI Chat Completions、OpenAI Responses 或 Anthropic Messages。
表单保存 API 根地址，通常以 `/v1` 结尾，不填写具体请求路由；adapter 按协议补全路径。

## 4. 创建和执行时校验

写入设置和创建 job 时：

- 设置 API 校验 provider、endpoint、model 和必需 credential 的结构；CapsWriter Token
  为选填，不作为配置完整性的必要条件；
- 创建 job 将非敏感 Provider 配置与加密 vault 的 credential reference 冻结到快照；
- 校验阶段依赖，例如 frame summary 需要 keyframes；
- 冻结快照并持久化成功后才能返回 queued；
- 不发起大模型下载或耗时推理。

worker 开始 attempt 时：

- 验证 snapshot schema、哈希和 secret 可解析性；
- 验证 provider 配置和 FFmpeg 等二进制依赖；
- 把环境或运行期错误写成明确错误码；
- 不因当前 system settings 改变而修改 job 行为。

## 5. 重做审计基线与当前关闭情况

2026-09-20 重做审计发现执行器读取可变 VLM 设置、ASR 默认 mock、画面描述占位降级、
摘要仅拼接文本，以及独立 worker 未接线。当前代码已完成以下关闭：

- 创建 job 时冻结 frame summary 和 overall summary 的非敏感配置，worker 只读快照；
- ASR 默认 `unconfigured`；已移除内置模型运行时，当前只实现 CapsWriter 官方
  WebSocket adapter，空值、未知值和 baseline 配置明确失败；
- Web 管理三类在线 Provider；credential 加密保存在 SQLite，明文不进入
  job snapshot、事件、日志、产物或读取响应；
- `CAPSWRITER_TOKEN`、`QWEN_API_KEY`、`SUMMARY_API_KEY` 仅用于旧 snapshot 兼容，
  不再作为新用户配置路径；
- frame summary 缺 key、传输失败、畸形或空响应明确失败，并删除旧／半写产物；
- overall summary 使用独立 credential reference 与兼容接口，对长材料分段归约后再总结；
- SQLite 保存领取、attempt、心跳、控制版本和游标事件，独立 worker 负责执行。

这些失败契约、credential vault 与首次 Provider 引导由自动测试约束。模型内容质量、
真实凭据和完整媒体覆盖必须另附真实验收证据；配置完成或 mock 测试通过不等于真实
链路通过。

## 6. Provider 状态语义

- `configured`：字段格式完整，所需 credential reference 存在；
- `reachable`：从实际执行进程完成 DNS/TCP/TLS/WS 或 HTTP 连接；
- `verified`：使用当前 credential 和 model 完成最小真实调用并解析合法响应；
- real E2E：真实视频经过 ASR/VLM/LLM，产物与内容经人工复核。

Profile 测试 API 使用保存的 credential 发起真实最小请求。CapsWriter 测试 WebSocket
握手，VLM 测试图片输入，LLM 测试文本输入；一次成功可陈述该配置在测试时 `verified`，
但不持久承诺可用性，也不替代真实视频 E2E。`GET /healthz` 仍只证明 API 进程存活。

## 7. Cookie 约束

- Web 创建 job 使用 `cookie_id`／受保护引用，不传 cookie 明文；
- Cookie Vault 对外路由使用 `/cookies`；底层历史表名只属于兼容实现细节；
- `cookie_file_path` 仅作为迁移兼容入口，不是目标 Web 协议；
- cookie、key 和 token 在日志、事件、快照与错误中完全脱敏。

## 8. 变更、版本与验证

- 配置 schema 破坏性变更需要迁移和版本说明；
- provider、模型、提示词或关键参数变化必须产生不同输入／配置指纹；
- 重跑只可复用指纹及产物校验都匹配的阶段；
- 设置更新、job snapshot 创建和 secret 解析失败都要留下不含秘密的操作记录；
- 配置文档、代码默认值和 UI 选项必须由测试核对，不能各自维护隐含枚举。
