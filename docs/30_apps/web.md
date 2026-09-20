# App: web

状态：当前页面使用 REST 完成认证、设置、项目/任务创建和文件传输；job 实时快照、
控制与增量事件使用 WebSocket。下列 `[已实现]` 描述当前代码路径。

## Purpose

Web 应用负责“用户看到什么 + 前端如何做决策”，覆盖：

- 访问入口分流（初始化 / 登录 / 游客 / 主界面）
- 项目与任务的创建、查看、控制
- 系统设置与 Cookie Vault 的前端治理入口
- 实时状态展示与可靠重连

## Status Legend

- **[已实现]** 重做审计时观察到对应代码路径；不代表真实浏览器端到端验收已通过。
- **[规划中]** 在 Web 文档中保留方向，但当前代码未强制完成。

## Core Views

- **[已实现]** `/`：入口分流 + 项目列表主界面
- **[已实现]** `/setup`：首次初始化（创建单用户账号）
- **[已实现]** `/login`：登录 + 游客入口
- **[已实现]** `/settings/system`：游客开关与游客 cookie 输入策略
- **[已实现]** `/settings/cookies`：Cookie Vault（列表/新增/编辑/删除/设默认/validate）
- **[已实现]** `/projects/[id]`：创建任务（双资产 ingest）+ 历史 job 列表
- **[已实现]** `/jobs/[id]`：日志/进度/产物/控制

## Entry Flow (用户看到什么)

- **[已实现]** 打开 `/` 后先请求 `GET /auth/bootstrap-status`。
- **[已实现]** `bootstrap_required=true` 时跳转 `/setup`。
- **[已实现]** 已初始化后，前端从 `localStorage` 读取 token，并以 Bearer token 调
  `GET /auth/me`：
  - token 有效 -> 进入主界面
  - token 无效或缺失 -> 跳转 `/login`
- **[已实现]** 游客会话只能由 `/login` 页面主动进入。

## Guest Mode & Cooldown (前端决策)

- **[已实现]** `/login` 仅通过 `GET /public/access-flags` 决定是否展示“游客进入”。
- **[已实现]** 游客进入不写入 auth token。
- **[已实现]** 在游客模式下，`/projects/[id]` 轮询 `GET /guest/cooldown` 并显示全服统一剩余秒数。
- **[已实现]** 冷却中禁用提交按钮，并显示剩余秒数。
- **[已实现]** 收到 `auth_required` 时统一回退到 `/login`。
- **[已实现]** 收到 `guest_cooldown_active` 时展示剩余秒数并保持冷却态提示。

## Cookie Vault & Ingest Policy

- **[已实现]** create-job / probe 仅透传 `cookie_id`（可选），不发送明文 cookie 字段。
- **[已实现]** 禁止 Web 侧透传 `cookie_content` / `cookie_file_path` / `cookie_secret_ref`。
- **[已实现]** Cookie Vault 不回显已提交明文 cookie。
- **[已实现]** `POST /me/cookies/{cookie_id}/validate` 前端必须传 `source_url`。
- **[已实现]** Cookie Vault 页面提供可编辑 Validate Source URL：
  - 默认值为前端常量视频页 URL
  - 输入为空时前端拦截并提示，不发请求
  - 最近一次输入写入 localStorage 并在下次打开回填
- **[已实现]** 当 guest 且 `guest_allow_cookie_input=false`：
  - UI 禁用 cookie 选择
  - submit 前剔除 `ingest.cookie_id`（双保险）

## Realtime Model

- **[已实现]** 任务页连接 `/ws/jobs/{job_id}`，服务端先在 barrier 内重放缺失事件，
  再发送权威 snapshot，随后放行连接建立期间缓存的 live events；
- **[已实现]** 客户端保存最后 cursor，重连发送 `after_cursor`；重复或较旧 cursor 被忽略；
- **[已实现]** 状态更新按 `state_version` 防倒退，追加事件按 cursor 去重；
- **[已实现]** 命令携带 `request_id`，后端持久化当前请求 ID 与控制版本以保证重复提交幂等；
- **[已实现]** 控制命令通过 WebSocket 返回 accepted/applied phase；UI 在 worker 确认前
  保持原执行状态并显示等待提示，收到 `job_state_changed` 后再显示 paused/cancelled；
- **[已实现]** WS 断开时显示连接状态并自动重连，不回退到 HTTP snapshot 轮询；
- **[规划中]** 事件保留期与 `cursor_reset` 尚未实现；当前事件表不主动裁剪。

HTTP 保留给认证、设置、项目/任务 CRUD、上传、播放/下载和健康检查。视频与产物
本体不通过 WebSocket 传输。

## Results Preview

- **[已实现]** 原始转录页签读取 transcript / keyframe JSONL，并按时间交错展示；
- **[已实现]** 运行中画面摘要使用 HTTP byte range 读取新增内容；若服务端不支持 range，
  客户端安全回退到全量读取；单行损坏不会让整个 JSONL 进入错误态；
- **[已实现]** 润色稿页签读取已发布的 `outputs/illustrated_notes.md`，严格解析
  `[[frame:...]]` 引用并展示对应 workspace 图片；不把 Markdown 当 HTML 注入页面；
- **[已实现]** 摘要页签读取带 provider/model 信息的 `outputs/summary.json`；未生成时
  明确显示尚不可用，不以拼接文本伪装模型摘要；
- **[已实现]** 日志仅在用户停留于底部时跟随新增内容，向上阅读历史时保持当前位置。

## i18n

- **[已实现]** 全局底部语言切换：`中文 / English`。
- **[已实现]** 默认中文（`zh`），浏览器 localStorage 持久化。
- **[已实现]** 核心页面与关键组件文案已 key 化（登录、初始化、系统设置、Cookie Vault、项目页、任务页）。
- **[规划中]** 状态码/内部状态值（例如部分后端原始字符串）可继续做更细粒度本地化映射。

## Error Handling & Fallback

- **[已实现]** `invalid_credentials`：登录页显示明确错误。
- **[已实现]** `bootstrap_required`：登录流程回退到 `/setup`。
- **[已实现]** `guest_cookie_key_required`：系统设置页显示可理解错误信息。
- **[已实现]** `auth_required`：需要登录的页面统一回退 `/login`。
- **[已实现]** 网络失败场景保留页面级错误提示，不静默吞错。
- **[已实现]** 删除等破坏性操作使用应用内可访问确认对话框；操作反馈统一使用 Toast
  或页面内错误信息，不调用浏览器原生 `alert()` / `confirm()`。
