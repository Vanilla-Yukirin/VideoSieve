# Events and WebSocket Protocol

状态：job 级协议已实现；本文件同时列出仍未实现的保留期和慢客户端治理。

## 1. 当前边界

`/ws/jobs/{job_id}` 负责一个 job 的：

- SQLite cursor 事件重放；
- 权威 snapshot；
- 日志、进度、阶段、状态、错误和控制确认增量；
- `pause|resume|cancel|delete` 控制命令。

设置、项目/任务创建与查询、上传和下载仍使用 HTTP。大文件不通过 WS 传输。产品内不做
WebSocket 会话鉴权，连接者必须已经位于 single-host trusted boundary 内。

## 2. Client Message

连接 URL 可带 `after_cursor=<non-negative integer>`。cursor 大于当前持久事件 watermark
时，服务端以 4400 关闭；job 不存在时以 4404 关闭。

控制消息形状：

```json
{
  "command": "pause",
  "request_id": "req_01"
}
```

- `request_id` 可选，但客户端发送控制时应生成稳定值；
- 当前 job 行持久化最新 request ID、command、request/ack version；
- 同一 request ID 的重复控制请求返回同一结果，不重复推进版本。

当前协议不接收通用 `subscribe` 消息，也不在消息中接收 project/job ID 或
`schema_version`；job scope 由 URL 决定。

## 3. Persisted Event and WS Envelope

SQLite `job_events.event_id` 是全局递增 ID。发送给客户端时字段名为 `cursor`：

```json
{
  "event_type": "progress",
  "cursor": 1842,
  "state_version": 27,
  "request_id": null,
  "payload": {"stage": "asr", "pct": 42.5}
}
```

SQLite 行还保存 `channel`、`project_id`、`job_id` 和 `ts`，但当前 WS 信封不重复发送
这些路由字段，也还没有 `schema_version`。已实现的持久事件包括 `log`、`progress`、
`stage_changed`、`job_state_changed`、`error` 和 `control_ack`。

连接级 `snapshot` 不写入事件表：

```json
{
  "event_type": "snapshot",
  "cursor": 1842,
  "state_version": 27,
  "request_id": null,
  "payload": {}
}
```

## 4. 连接、重放与并发屏障

1. 服务端读取当前 watermark，并先从该 watermark 建立 SQLite 订阅；
2. 若客户端提供旧 cursor，按 cursor 升序重放 `(after_cursor, catchup_watermark]`；
3. 发送当前权威 snapshot；
4. 连接建立期间产生的 live events 先按 socket 缓冲，再按 cursor 排序放行；
5. 之后仅发送 cursor 更大的 live events。

这套屏障防止 snapshot 与 live event 交叉造成倒退。首次连接没有 cursor 时不重放历史
事件，只发送 snapshot 后继续 live stream。

当前事件表不自动裁剪，所以还没有“cursor 已过期”或 `cursor_reset` 分支。增加保留期
前必须同时实现最小可用 cursor、显式 reset 和对应契约测试。

## 5. Control Ack

`control_ack.payload` 包含：

- `request_id`（客户端提供时）、`command`、`accepted`；
- `phase`: `accepted|applied|rejected`；
- `execution_state`、`requested_action`；
- 可选 `code` 和 `reason`。

`accepted` 只表示控制请求已持久化。running job 的 pause/cancel 要等 worker 到安全点，
更新状态和确认版本后才是 applied。queued/paused 等无 owner 状态的取消可在同一事务
直接确认。

## 6. 客户端合并规则

- 保存最后处理的 cursor，重连作为 `after_cursor`；
- 非 snapshot 事件的 cursor 小于等于当前 cursor 时忽略；
- 状态事件的 `state_version` 小于当前版本时只推进 cursor，不覆盖状态；
- snapshot 覆盖当前状态字段，但不让 cursor 倒退；
- 断线时显示离线状态并自动重连，不回退到 HTTP snapshot 轮询；
- 待确认命令在断线时失败，由调用方决定是否复用原 request ID 重试。

## 7. 服务端可靠性与缺口

- SQLite `job_events` 是恢复来源；`InMemoryEventBus` 只用于测试或明确嵌入；
- SQLite 订阅遇到暂时数据库错误会重连；单个 handler 异常不会毒死后续 cursor；
- WebSocket 发送失败不回滚已提交状态，客户端通过 cursor 恢复；
- 生产事件不得把 mock、占位文本或 provider 失败包装为成功 artifact；
- 每连接发送队列上限、慢客户端断开策略和事件保留期仍待实现。
