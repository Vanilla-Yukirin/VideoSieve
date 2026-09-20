# Configuration

状态：本文件同时记录当前缺口与目标契约；目标行为尚未全部实现。

## 1. 配置分层

### Deployment configuration

由环境变量或受保护的运行配置提供，描述进程启动和敏感依赖：

- `APP_SECRET_KEY` 等会话密钥；
- SQLite 文件路径、workspace 根目录；
- worker 轮询、心跳、busy timeout 等运行参数；
- provider API key 或本地模型凭据。

密钥不得写入普通数据库快照、日志、事件或产物。

### System settings

保存在 SQLite，表示管理员可调整的默认值和产品开关。环境变量只在首次初始化时提供
默认值；初始化后不能在每次启动时无条件覆盖数据库设置。

### Job snapshot

创建 job 时冻结不可变配置，保存到
`jobs/{job_id}/meta/config.snapshot.json` 并记录内容哈希。worker 整个 attempt 只读取
该快照和受保护的 secret reference，不读取当前 UI 状态或可变 system settings。

优先级为：系统默认值 -> 创建 job 的合法覆盖 -> 不可变 job snapshot。执行开始后，
管理员修改设置只影响以后创建的 job。

## 2. Snapshot 必须覆盖的内容

- ingest 来源引用、格式选择、cookie secret reference；
- ASR provider、模型、语言、热词和非敏感参数；
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
| ASR | 显式真实 provider；首版可用本地 FunASR | 未知 provider、模型缺失或加载失败时明确失败，不回退 mock |
| Frame summary | 显式视觉模型和凭据引用 | 缺 key、超时、鉴权、空／畸形响应明确失败，不生成占位描述 |
| Overall summary | 独立 LLM、提示词版本和上下文预算 | 必须实际总结完整材料，不允许截取／拼接片段冒充摘要 |

测试中的 fake/mock 由依赖注入提供，不能成为生产配置默认值或未知 provider 的兜底。

## 4. 创建和执行时校验

创建 job 时：

- 校验 provider 名称、必要参数和 secret reference 是否存在；
- 校验阶段依赖，例如 frame summary 需要 keyframes；
- 冻结快照并持久化成功后才能返回 queued；
- 不发起大模型下载或耗时推理。

worker 开始 attempt 时：

- 验证 snapshot schema、哈希和 secret 可解析性；
- 验证本地模型／二进制依赖；
- 把环境或运行期错误写成明确错误码；
- 不因当前 system settings 改变而修改 job 行为。

## 5. 重做审计基线缺口

截至 2026-09-20 的重做审计基线：

- 部分 system settings、环境初始化和 job 快照文件已经存在；
- 执行器仍会在 frame summary 阶段读取可变设置，尚未完全遵守快照；
- ASR 默认／未知 provider 仍可能选择 mock；
- frame summary 仍可能把失败转成占位文本；
- overall summary 尚无独立真实模型配置和完整调用链；
- 独立 worker、队列及 attempt 运行参数尚未接线。

后续提交可逐项关闭这些缺陷，但必须由对应测试和验收记录证明。这些缺陷不得用
“配置可选”解释为预期降级。

## 6. Guest 与 Cookie 约束

- guest mode 默认关闭；
- `guest_allow_cookie_input=true` 时必须提供有效 `GUEST_COOKIE_KEY`，否则启动或设置写入失败；
- Web 创建 job 使用 `cookie_id`／受保护引用，不传 cookie 明文；
- `cookie_file_path` 仅作为迁移兼容入口，不是目标 Web 协议；
- cookie、key 和 token 在日志、事件、快照与错误中完全脱敏。

## 7. 变更、版本与验证

- 配置 schema 破坏性变更需要迁移和版本说明；
- provider、模型、提示词或关键参数变化必须产生不同输入／配置指纹；
- 重跑只可复用指纹及产物校验都匹配的阶段；
- 设置更新、job snapshot 创建和 secret 解析失败都要留下不含秘密的操作记录；
- 配置文档、代码默认值和 UI 选项必须由测试核对，不能各自维护隐含枚举。
