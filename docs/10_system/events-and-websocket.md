# Events and WebSocket Protocol

状态：目标契约，当前 REST + 内存事件实现需要迁移。

## 1. 通道职责

业务会话建立后，WebSocket 是以下交互的统一通道：

- 项目和 job 列表、详情及权威快照；
- 创建、设置更新、重跑和控制命令；
- 日志、进度、状态、错误、产物和控制确认；
- 断线后的 cursor 重放与快照收敛。

HTTP 只用于页面／初始认证会话、上传、播放／下载和健康检查。大文件不通过 WS 传输。

## 2. Client Message

每个客户端请求至少包含：

```json
{
  "schema_version": "1.0",
  "message_type": "command",
  "request_id": "req_01...",
  "command": "pause",
  "project_id": "p_01...",
  "job_id": "j_01...",
  "payload": {}
}
```

- `request_id` 在客户端重试期间保持不变；
- 服务端持久化请求结果并按 `request_id` 去重；
- 重复命令不能重复创建 job、重复扣费或重复执行删除。

订阅／重连消息使用 `command=subscribe`，payload 包含需要订阅的 scope 和可选
`after_event_id`。

## 3. Persisted Event Envelope

持久事件至少包含：

```json
{
  "schema_version": "1.0",
  "event_id": 1842,
  "event_type": "progress",
  "project_id": "p_01...",
  "job_id": "j_01...",
  "state_version": 27,
  "ts": "2026-09-20T12:00:00Z",
  "request_id": null,
  "payload": {}
}
```

- `event_id` 是 SQLite 生成的单调递增 cursor，排序以它为准，不以客户端时间排序；
- `state_version` 标识事件对应的 job 状态版本；
- 业务状态变化与描述该变化的事件必须在同一个 SQLite 事务提交；
- 进度事件限频或合并，不能按每帧高频落库；
- 日志全文可以写文件，事件表保留 UI 与诊断需要的结构化窗口。

目标事件类型：

- `snapshot`：当前权威状态，含 `snapshot_event_id`；
- `log`；
- `progress`；
- `stage_changed`；
- `job_state_changed`；
- `artifact_ready` / `artifact_removed`；
- `error`；
- `control_ack`；
- `cursor_reset`。

`snapshot` 与 `cursor_reset` 可以是连接级消息，不必作为新的业务事件再次持久化。

## 4. Control Ack

`control_ack` 必须包含：

- `request_id`、`command`；
- `phase`: `accepted|applied|rejected|failed`；
- 当前 `execution_state` 和 `requested_action`；
- 可选 `code/message/hint/retryable`。

`accepted` 表示命令已经持久化，不表示 worker 已经停下。pause/cancel 只有收到
`applied` 且快照进入 paused/cancelled，UI 才能显示“已暂停／已取消”。

## 5. 首次连接和重连

### 5.1 无 cursor 或 cursor 已过期

1. 服务端在一致读取边界取得权威 snapshot 和当前 watermark `W`；
2. 发送 `cursor_reset`（首次连接可省略）和 snapshot，`snapshot_event_id=W`；
3. 随后只发送 `event_id > W` 的 live events。

客户端必须清空无法证明连续的增量状态，使用 snapshot 重建界面。

### 5.2 cursor 仍在保留期内

1. 客户端发送 `after_event_id=C`；
2. 服务端确定一致 watermark `W` 和对应 snapshot；
3. 按 event_id 重放 `(C, W]`；
4. 发送 snapshot 作为最终状态校正；
5. 随后发送 `event_id > W` 的 live events。

重放可恢复日志和过程记录，最后的 snapshot 防止状态事件使 UI 倒退。重放期间产生的
新事件在 live 阶段继续发送，不能遗漏 `W` 之后的数据。

## 6. 客户端合并规则

- 记住最后连续处理并确认的 `event_id`；
- event_id 已处理的追加事件直接去重；
- 状态更新的 `state_version` 小于当前版本时忽略；
- 收到 snapshot 时以 snapshot 的执行状态、请求态、stage、进度和产物索引为准；
- WS 断开时显示“正在重连／状态可能过期”，不能把旧缓存显示成实时状态；
- 重连采用有限退避；待确认命令可复用原 `request_id` 重发查询结果。

## 7. 服务端读取与推送

- SQLite `job_events` 是可靠事件源；进程内通知只用于唤醒读取循环；
- API 按 cursor 批量读取，不依赖 Redis Pub/Sub/Streams；
- 每个连接设置发送队列上限。慢客户端超限时断开并要求 cursor 重连，不能无限占内存；
- 事件设置明确保留期／上限。删除历史前记录每个 job 可用的最小 cursor；
- 权限变更或会话失效时关闭订阅，不能继续推送任务内容。

## 8. Failure Semantics

- SQLite 暂时 busy：受限退避重试，不能丢弃已接受命令；
- 事件序列出现缺口：发送 `cursor_reset`，不得假装连续；
- payload 无法解析：发送协议错误并保留原事件用于诊断；
- WebSocket 发送失败不回滚已经提交的业务状态；客户端通过 cursor 恢复；
- 生产事件不得把 mock、占位文本或 provider 失败包装为成功 artifact。
