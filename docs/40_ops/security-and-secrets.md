# Security and Secrets

## Rules

- never commit secrets to git
- use environment variables or secret manager
- redact sensitive fields in logs/events

Status markers:
- `implemented`: active in current runtime.
- `planned`: target behavior not yet exposed.

## Secret Types

- provider API keys
- cookie credentials (if needed for source download)
- storage credentials

## Cookie Handling (High Sensitivity)

- `implemented` cookie vault stores encrypted cookie text server-side; plaintext is not returned by API responses
- `implemented` cookie validation requires a concrete video-page URL and rejects site homepage/root URLs
- cookie-related fields must be fully redacted in logs/events/errors
- `implemented` prefer `cookie_id` in API job payloads; resolve cookie material server-side
- `implemented` keep `cookie_file_path` only as migration fallback in controlled local/dev deployments

## API Startup Preconditions

- `implemented` `APP_SECRET_KEY` is mandatory for API startup (fail-fast).
- `implemented` missing or blank `APP_SECRET_KEY` prevents service startup instead of deferring failure to runtime handlers.

## Minimum Deployment Env (API)

- `APP_SECRET_KEY`
- `ENABLE_GUEST_MODE`
- `GUEST_ALLOW_COOKIE_INPUT`
- `GUEST_COOKIE_KEY`
- `GUEST_JOB_COOLDOWN_SECONDS`
- `QWEN_API_KEY`

Constraint:
- `implemented` if `guest_allow_cookie_input=true` in persisted settings while `GUEST_COOKIE_KEY` is empty, runtime must reject configuration.

## Frontend Public Env Boundary

- `NEXT_PUBLIC_*` variables are public and shipped to browser clients.
- Do not place secrets in `NEXT_PUBLIC_*` values.
- Examples of non-secret public config: `NEXT_PUBLIC_API_ORIGIN`.

## Browser Session Token Tradeoff

- `implemented` 当前 Web 把管理会话 token 存在浏览器 `localStorage`，请求时通过
  `Authorization: Bearer ...` 发送；SSR 使用空的 server snapshot，hydration 后再读取 token，
  避免服务端与客户端首屏状态不一致。
- 这意味着一旦页面发生 XSS，攻击脚本可以读取 token。该实现只接受于当前“一台主机、
  一个或少量可信用户”的自托管范围，不能据此声称适合直接暴露为公网多用户服务。
- 当前前端不把模型输出或 Markdown 作为 HTML 注入；润色稿只渲染文本和经过严格字符集
  校验的 frame 占位符。部署时仍需限制允许的 Web origin、使用 TLS，并避免加载不可信
  第三方脚本。
- `planned` 若部署范围扩展到公网或不可信多用户，认证应迁移到 `HttpOnly`、`Secure`、
  合适 `SameSite` 的服务端 cookie，并同时设计 CSRF 防护、WebSocket 握手认证和会话撤销；
  不能只把 Bearer token 改存 cookie。

## Operational Guardrails

- rotate keys periodically
- least privilege for service accounts
- separate dev/prod credentials
