# App: api

状态：SQLite 队列与 job WebSocket 控制面已实现。REST 路由承担设置、项目与任务创建、
上传和下载；产品内没有账号、登录、游客或会话鉴权。标为 `implemented` 只表示代码路径
存在，不代替运行验收。

## Purpose

提供受限 HTTP 文件接口与 WebSocket 业务网关。API 创建任务时只持久化配置快照和
queued 记录，不在 API 进程内执行媒体 pipeline。

## Trusted Boundary

- Web/API 默认只监听回环地址；HTTP 与 WebSocket 都假定调用者已经位于受信边界内；
- yukirin-server 等远程访问必须通过 Tailscale、Yukirin Gateway 或认证反向代理；
- 不得把 API/Web 直接开放到公网或不受控局域网入口；无登录不等于公开访问安全；
- `APP_SECRET_KEY` 只保护 SQLite 中的敏感值，不是调用者身份或会话凭据。

## Domain Axis (Project vs Job)

- `Project` 是长期实体（视频来源与历史运行容器）。
- `Job` 是一次运行（配置快照、状态机、事件流、产物集合）。
- 控制命令与实时事件以 `job_id` 为主轴，避免重跑时语义歧义。

## Responsibilities

- validate commands and persist project/job/config records
- serve authoritative snapshots and cursor events over WebSocket
- expose uploads, media/artifact downloads and health checks over HTTP
- read SQLite events and push them to trusted WS connections

## Interfaces

Current runtime exposes REST endpoints for settings/project/job/config/artifact and a job WebSocket
channel:

- HTTP：Provider 设置、project/job CRUD、上传、媒体/产物下载和健康检查；
- WebSocket：单个 job 的权威 snapshot、控制命令和 cursor events；
- 大文件不在 WebSocket 消息中传输。

`/ws/jobs/{job_id}` 与命令注册以
[Events and WebSocket Protocol](../10_system/events-and-websocket.md) 为准。

Status markers used below:

- `implemented`: code path observed; runtime/E2E validation is separate.
- `planned`: documented target, not in current runtime.

Key REST endpoints:

- `implemented` `GET /settings/system`, `PATCH /settings/system`；
- `implemented` `GET /projects`：以稳定的创建时间倒序返回 SQLite 项目；
- `implemented` `PATCH /projects/{project_id}`：持久化修改项目标题；
- `implemented` `POST /ingest/probe`：只探测 URL 格式，不下载；
- `implemented` `POST /jobs`：冻结配置快照并写入 queued job；
- `implemented` `POST /projects/{project_id}/jobs/upload`：在项目 workspace 暂存上传后创建 job；
- `implemented` `GET /jobs/{job_id}/source-video`：提供 workspace 视频；
- `implemented` Cookie Vault：`POST /cookies`、`GET /cookies`、
  `PATCH /cookies/{cookie_id}`、`DELETE /cookies/{cookie_id}`；
- `implemented` `POST /cookies/{cookie_id}/validate`：用具体视频页 URL 验证 cookie；
- `planned` `GET /operation-logs`：当前 runtime 只写操作记录，尚无查询端点。

底层历史表名若仍保留，只属于兼容实现细节；对外契约只使用上述 `/cookies` 路由。

## Provider Settings

- `implemented` `/provider-profiles` 提供多配置的增删改查、默认项切换和 write-only credential；
- `implemented` `POST /provider-profiles/test-draft` 使用当前表单值执行真实最小请求，不保存
  Profile 或 credential；编辑已有 Profile 时可通过 ID 只读复用已保存 credential；
- `implemented` `POST /provider-profiles/{profile_id}/test` 执行真实最小请求，只返回脱敏状态与耗时；
- `implemented` 创建 job 时只把选中的非敏感 Provider 配置与 credential reference 写入 snapshot。

`configured` 只表示结构完整且 credential reference 存在；它不证明 endpoint `reachable`、
credential/model `verified`，也不等于真实视频 E2E。

## Ingest and Artifact Notes

- Create-job path uses format IDs (`analysis_asset` + `quality_asset`)；
- create-job 接受 `cookie_id`，`cookie_file_path` 只作为迁移兼容入口；
- Web 请求不接受明文 `cookie_content`；
- cookie validate 要求具体视频页 URL，并拒绝站点首页，避免假阴性；
- `GET /jobs/{job_id}/artifacts` 只返回 readiness manifest 身份、大小与 SHA-256 均匹配的
  final deliverables；下载路由继续约束在 workspace 内。

## Control Semantics

- UI 控制始终针对一个 `job_id`；重跑产生新的 `job_id`；
- accepted 请求与 worker-confirmed applied 状态分开持久化；
- API 不能仅因写入控制标志就报告 paused/cancelled；
- heartbeat timeout 产生 `interrupted`，不能自动派发替代 attempt。

## Notes

- API 不直接实现算法，算法由 `packages/*` 提供；
- job state truth 是 SQLite-backed WebSocket snapshot，增量使用持久 event cursor；
- 进程内通知只能唤醒 gateway，不能作为恢复来源；
- `/healthz` 只证明 API liveness，不证明数据库、workspace、worker 或 provider readiness；
- `APP_SECRET_KEY` 缺失时 API 启动失败；
- 当前通用错误包括 `not_found`、`validation_error`、`config_error`、`internal_error`。
