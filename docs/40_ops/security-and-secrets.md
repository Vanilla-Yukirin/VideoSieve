# Security and Secrets

## Single-host Trusted Boundary

VideoSieve 采用 single-host trusted mode：产品内没有账号、登录、登出、游客、session 或
按用户授权。HTTP 与 WebSocket 都假定调用者已经位于部署方建立的受信边界内。

- Web/API 默认只监听 `127.0.0.1` / `localhost`；
- yukirin-server 等远程访问必须通过 Tailscale、Yukirin Gateway 或认证反向代理；
- 不得把 Web/API 端口直接开放到公网或不受控局域网入口；
- 无登录不等于公开访问安全，CORS 也不能代替网络访问控制；
- 若未来需要不可信多用户访问，必须重新设计身份、授权、CSRF、WebSocket 握手和审计，
  并以新 ADR 修改当前边界。

## Rules

- never commit secrets to git
- encrypt persisted credentials
- redact sensitive fields in logs/events/errors
- keep browser-visible configuration non-secret

Status markers:

- `implemented`: active in current runtime.
- `planned`: target behavior not yet exposed.

## Secret Types

- provider API keys and optional CapsWriter token
- cookie credentials used for source download
- `APP_SECRET_KEY`
- future storage credentials, if introduced

## Online Provider Credentials

- `implemented` Web Provider 设置录入 CapsWriter Token、VLM API key 和 summary API key；
  endpoint 与 model 由同一页面管理；
- `implemented` credential 使用由 `APP_SECRET_KEY` 派生的密钥加密后持久化；数据库只保存
  密文与 metadata，读取 API 只返回 `configured` 状态；
- 替换和清除 credential 使用显式 write-only 操作，不用空字符串或掩码值猜测；
- job snapshot 只保存 credential reference；日志、事件、错误、产物、浏览器状态和操作记录
  不得包含明文；
- `CAPSWRITER_TOKEN`、`QWEN_API_KEY` 与 `SUMMARY_API_KEY` 环境变量只兼容旧 snapshot，
  新用户不应编辑这些变量；
- `planned` 独立 Provider 连接测试尚未实现。credential 已保存不代表 endpoint 可达、
  鉴权有效、模型存在或真实视频 E2E 已验证。

## Cookie Handling

- `implemented` Cookie Vault 在服务端加密保存 cookie，读取 API 不返回明文；
- `implemented` 对外 API 使用 `/cookies`，底层历史表名只属于兼容实现细节；
- `implemented` validation 要求具体视频页 URL，并拒绝站点首页；
- cookie 字段在日志、事件和错误中完全脱敏；
- job 请求优先使用 `cookie_id`，服务端解析实际 cookie；
- `cookie_file_path` 只作为受控本地迁移兼容入口。

## APP_SECRET_KEY

- `implemented` API 启动必须提供非空且非示例值的 `APP_SECRET_KEY`；
- API 与 worker 必须使用同一密钥，否则 worker 无法解密网页保存的 provider credential；
- 轮换前必须完成受控重加密，直接替换会使现有密文不可读；
- `APP_SECRET_KEY` 是静态数据加密根密钥，不是用户密码、Bearer token 或访问控制机制。

API 的最低部署环境包含 `APP_SECRET_KEY`、数据目录、监听地址／端口和允许的 Web origin。
在线 Provider key 不属于新部署环境变量集合。

## Frontend Public Env Boundary

- `NEXT_PUBLIC_*` 会发给浏览器，不能包含任何秘密；
- `NEXT_PUBLIC_API_ORIGIN` 可以公开；
- 前端不保存 auth token，因为产品没有登录或 session；
- 模型输出和 Markdown 不作为任意 HTML 注入；仍应限制 origin、使用安全的外层远程入口，
  并避免加载不可信第三方脚本。

## Operational Guardrails

- 定期验证备份和密钥恢复；
- Provider 使用最小权限凭据，并区分开发与正式环境；
- 外层 Tailscale、Yukirin Gateway 或认证反向代理的访问策略属于部署必需项，必须与
  Web/API 一起验收；
- 外层入口失效或绕过时，停止远程开放，不能依赖产品内不存在的登录兜底。
