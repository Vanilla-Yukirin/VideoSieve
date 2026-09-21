# ADR-0008: Single-host Trusted Mode

Status: Accepted

Date: 2026-09-21

## Context

VideoSieve 的确认范围是一台电脑或服务器，供本人或少量已经受信的用户使用。任务、
Provider credential、Cookie Vault、产物和控制接口都具有高权限；仓库当前不以公网或
不可信多用户 SaaS 为目标。

在产品内保留账号、登录、游客、冷却和 session 会制造一套不完整的安全边界，并让首次
使用必须先理解无关的身份流程。实际的远程访问已经更适合由宿主环境的 Tailscale、
Yukirin Gateway 或认证反向代理统一控制。

## Decision

- 产品内不提供账号、登录、登出、游客、按用户授权或 session；
- 首次打开应用时直接进入 Provider setup，随后进入项目与任务界面；
- HTTP、WebSocket、Cookie Vault、设置和产物接口都假定调用者已经位于 single-host
  trusted boundary；
- Web/API 默认绑定 `127.0.0.1` / `localhost`；
- yukirin-server 等远程访问必须通过 Tailscale、Yukirin Gateway 或带认证的反向代理；
- 禁止把 Web/API 直接暴露到公网或不受控局域网入口；无登录不等于公开访问安全；
- `APP_SECRET_KEY` 继续保护持久化 credential，但不承担用户身份、session 或请求授权；
- Cookie Vault 对外路由使用 `/cookies`。底层保留历史表名只属于兼容实现细节，不要求
  为此迁移或重命名数据库表；
- Provider `configured` 只证明字段和 credential reference 已保存。独立连接测试尚未
  实现，不能据此声称 `reachable`、`verified` 或真实视频 E2E 已通过。

## Consequences

Positive:

- 首次使用直接解决运行任务所需的 Provider 配置；
- 产品不再维护一套与实际部署边界重叠且不完整的身份状态；
- 本地 Web、HTTP 和 WebSocket 使用同一个清晰的外层信任边界。

Trade-offs:

- 任何进入外层受信网络或代理身份的人都具有产品全部能力；
- 错误绑定到 `0.0.0.0` 或绕过外层入口会直接暴露高权限接口；
- 远程访问的身份、撤销、TLS 和访问日志由外层系统承担，必须与应用一起部署和验收。

## Supersedes and Clarifies

- 覆盖 [ADR-0005](ADR-0005-single-host-sqlite-worker.md) 中关于产品认证与初始 session
  引导的表述；其 SQLite queue/worker 决策不变；
- 覆盖 [ADR-0007](ADR-0007-web-provider-credentials.md) 中旧的首次账号步骤；Provider
  credential 加密、reference 与验证边界不变。

## Revisit Triggers

出现以下任一需求时，必须先形成新的安全与身份 ADR：

- 直接服务不可信用户或公开互联网；
- 需要按用户隔离项目、Cookie、Provider credential 或产物；
- 需要细粒度权限、审计归因、配额或强制会话撤销；
- 无法保证所有 HTTP 与 WebSocket 流量经过同一个外层受信入口。
