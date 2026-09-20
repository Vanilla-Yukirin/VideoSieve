# App: web

状态：当前页面已实现 REST + WS 混合流程；目标协议改为 WebSocket 业务快照、命令和
增量事件。下列 `[已实现]` 只描述迁移前当前代码。

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
- **[已实现]** 已初始化后，前端使用本地 token 调 `GET /auth/me`：
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

当前实现：

- **[已实现]** 任务页先拉 `GET /jobs/{job_id}/snapshot`，再连接
  `/ws/jobs/{job_id}` 接收增量；
- **[已实现]** WS 断开时回退 HTTP snapshot 轮询。

目标契约：

- **[规划中]** 会话建立后，通过 WS 获得权威 snapshot，业务状态不再依赖 HTTP 轮询；
- **[规划中]** 客户端保存最后连续 `event_id`，重连发送 `after_event_id`；
- **[规划中]** 服务端重放后发送 snapshot 校正；cursor 过期时明确发送 `cursor_reset`；
- **[规划中]** 状态更新按 `state_version` 防倒退，追加事件按 `event_id` 去重；
- **[规划中]** 命令携带稳定 `request_id`，断线重发不会重复执行；
- **[规划中]** UI 分别显示请求 accepted 与 worker applied，例如“正在暂停”与“已暂停”；
- **[规划中]** 断线期间显示状态可能过期，不把本地缓存冒充实时结果。

HTTP 在目标架构中保留给页面／初始会话、上传、播放／下载和健康检查。视频与产物
本体不通过 WebSocket 传输。

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
