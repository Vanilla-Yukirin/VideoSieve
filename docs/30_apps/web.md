# App: web

状态：当前页面使用 REST 完成 Provider 设置、项目/任务创建和文件传输；job 实时快照、
控制与增量事件使用 WebSocket。产品内没有账号、登录、游客或会话。下列 `[已实现]`
描述当前代码路径，不代表真实浏览器端到端验收已通过。

## Purpose

Web 应用负责：

- 首次 Provider setup 与后续系统设置；
- 项目与任务的创建、查看和控制；
- Cookie Vault 的前端入口；
- 实时状态展示与可靠重连。

## Status Legend

- **[已实现]** 当前存在对应代码路径；真实浏览器、provider 与内容验收另行记录。
- **[规划中]** 已接受方向，但当前代码尚未交付。

## Core Views

- **[已实现]** `/`：入口分流与 SQLite 权威项目列表；旧 localStorage 索引只作迁移缓存；
- **[已实现]** `/setup`：首次 Provider 引导，依次配置 ASR、画面描述 VLM 和全文摘要 LLM
  的 endpoint、model 与 credential；
- **[已实现]** `/settings/system`：Provider 与系统设置；
- **[已实现]** `/settings/cookies`：Cookie Vault（列表、新增、编辑、删除、设默认、validate）；
- **[已实现]** `/projects/[id]`：创建任务和查看历史 job；
- **[已实现]** `/jobs/[id]`：日志、进度、产物和控制。

## Entry Flow

- **[已实现]** 打开应用后读取 Provider setup 状态；未完成时直接进入 `/setup`；
- **[已实现]** 不创建账号，不显示登录或游客入口，也不在 localStorage 保存 auth token；
- **[已实现]** Provider 引导允许明确跳过可选摘要能力，并展示功能影响；
- **[已实现]** Provider 设置只回显 credential 是否已保存，不回显密钥明文；
- **[规划中]** 独立连接测试尚未实现，`configured` 不得渲染成“连接成功”。

产品页面假定调用者已经位于 single-host trusted boundary。Web/API 默认使用 loopback；
yukirin-server 等远程访问必须由 Tailscale、Yukirin Gateway 或认证反向代理控制。不得把
Web/API 直接暴露到公网或不受控局域网入口。

## Cookie Vault & Ingest Policy

- **[已实现]** create-job / probe 只透传可选 `cookie_id`，不发送 cookie 明文；
- **[已实现]** Web 不透传 `cookie_content`、`cookie_file_path` 或 `cookie_secret_ref`；
- **[已实现]** Cookie Vault 不回显已提交的明文 cookie；
- **[已实现]** 对外 API 使用 `/cookies`；validate 调用
  `POST /cookies/{cookie_id}/validate` 并传 `source_url`；
- **[已实现]** Validate Source URL 必须是具体视频页；空值在前端拦截，最近输入可保存在
  localStorage 以便回填。

底层历史表名只属于兼容实现细节，不构成前端 API 契约。

## Realtime Model

- **[已实现]** 任务页连接 `/ws/jobs/{job_id}`，服务端重放缺失事件、发送权威 snapshot，
  再放行连接期间缓存的 live events；
- **[已实现]** 客户端保存最后 cursor，重连使用 `after_cursor`，并忽略重复或更旧 cursor；
- **[已实现]** 状态按 `state_version` 防倒退，追加事件按 cursor 去重；
- **[已实现]** 命令带稳定 `request_id`，控制回执区分 accepted 与 applied；
- **[已实现]** WS 断开时显示状态并自动重连，不回退到 HTTP snapshot 轮询；
- **[规划中]** 事件保留期与 `cursor_reset` 尚未实现，当前事件表不主动裁剪。

HTTP 保留给设置、项目/任务 CRUD、上传、播放/下载和健康检查。视频与产物不通过
WebSocket 传输。

## Results Preview

- **[已实现]** 原始转录页签读取 transcript / keyframe JSONL 并按时间交错展示；
- **[已实现]** frame-summary 整批完成后原子发布 JSONL；读取器支持 HTTP byte range，
  服务端不支持时回退全量读取；
- **[已实现]** 润色稿读取 `outputs/illustrated_notes.md`，只解析受限 frame 引用，不把
  Markdown 作为 HTML 注入；
- **[已实现]** 摘要页签读取含 provider/model 信息的 `outputs/summary.json`，缺失时明确
  显示不可用；
- **[已实现]** 日志只在用户位于底部时自动跟随。

## i18n

- **[已实现]** 全局语言切换为 `中文 / English`，默认中文并用 localStorage 持久化；
- **[已实现]** Provider 初始化、系统设置、Cookie Vault、项目页和任务页文案已 key 化；
- **[规划中]** 部分后端状态值可继续增加本地化映射。

## Error Handling & Fallback

- **[已实现]** 网络失败保留页面级错误，不静默吞错；
- **[已实现]** Provider 缺配置或保存失败显示明确错误，不把失败渲染为可用；
- **[已实现]** 删除等破坏性操作使用应用内可访问确认对话框；反馈使用 Toast 或页面内
  错误，不调用浏览器原生 `alert()` / `confirm()`。
