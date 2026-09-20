# Job State Machine

状态：job 执行与控制主路径已实现；attempt 历史和 stage 级 interrupted 仍是缺口。

## 1. 三类状态不能混用

### 1.1 执行确认态 `status`

`status` 只记录系统已经确认的执行事实：

- `queued`：已持久入队，当前没有 worker owner；
- `running`：某个 attempt 已原子领取并正在执行；
- `paused`：worker 已到达安全点、保存检查点并释放当前执行；
- `succeeded`：必要阶段与产物已经校验成功；
- `failed`：执行以明确错误结束；
- `cancelled`：worker 或协调器已确认不再执行，并完成必要清理；
- `interrupted`：原 attempt 失去可靠所有权或异常终止，需要恢复判定。

`queued/running/paused` 是执行确认态。`pause_requested`、`cancel_requested` 等不是
执行结果，不能写入同一字段伪装成已停止。

### 1.2 当前控制请求

控制意图与执行状态使用独立列保存。当前 job 行只保留最新命令：

- `pause`；
- `resume`；
- `cancel`；
- 删除等待另由 `delete_pending` 表示。

`control_version` 与 `control_ack_version` 区分请求和 worker 确认，snapshot 映射为：

- `accepted`：已持久化且当前语义合法；
- `applied`：负责执行的一方已确认动作生效；
- `rejected`：命令不合法或与当前状态冲突；
- `failed` 仍是协议保留值，当前控制路径没有独立失败历史表。

当前仅保存最新请求，不是 append-only control history。重复 `request_id` 幂等；不同请求
在并发状态变化时通过 expected status/state version 条件更新拒绝陈旧写入。

`accepted` 不能当作 `applied`。UI 可把 `running + pause_requested` 显示为“正在暂停”，
但不得显示为“已暂停”。

### 1.3 Attempt 所有权

一次领取递增 job 行的整数 `attempt`，同时写 `worker_id/claimed_at/heartbeat_at`。worker
更新状态、进度、心跳和释放所有权时都以 worker ID + attempt 做 fence。当前没有独立
attempt ID、历史状态表或 attempt 临时目录，因此只能证明陈旧 owner 不能覆盖新状态，
不能提供完整 attempt 审计。

## 2. 执行状态转换

```text
create -> queued -> running -> succeeded
                    |   |
                    |   +-> failed
                    |   +-> cancelled
                    |   +-> paused -> running
                    |
                    +-> interrupted -> queued    (显式恢复并确认旧执行已停止)
                                  \-> failed
                                  \-> cancelled

queued -> cancelled
paused -> cancelled
```

规则：

1. `queued -> running` 只能由 worker 的原子领取事务完成，并递增 attempt。
2. `running -> paused` 只能由当前 owner 在安全点保存检查点并释放执行后完成。
3. paused job 接受 resume 后仍保持 paused；worker 原子领取时直接转为 running。
4. `running -> cancelled` 必须先停止后续工作并清理受管理子进程。
5. `succeeded/failed/cancelled` 是终态；重跑创建新 job，不复活旧 job。
6. `interrupted` 阻止普通领取。只有显式恢复流程确认旧 worker 和子进程已退出、
   校验可复用产物后，才允许 `interrupted -> queued`。
7. 心跳超时只说明 owner 可疑失联。它最多把 job 标记为 `interrupted`／需要恢复，
   不能自动创建新 attempt 或重新领取仍可能运行的任务。

## 3. 控制命令应用规则

### Pause

1. API 持久化 `pause_requested`，返回 `control_ack: accepted`。
2. 当前 worker 在下一个安全点停止启动新工作，保存可恢复边界并释放资源。
3. worker 在同一短事务中写 `execution_state=paused`、请求 `applied` 和确认事件。

模型请求或本地推理不能立即中断时，job 保持 running，UI 显示“正在暂停”。

### Resume / interrupted recovery

1. paused job 接受 resume 后保持 paused，worker 下一次领取时进入 running 并确认命令；
2. interrupted job 也复用 resume 命令显式恢复为 queued；条件更新保证状态版本未变化；
3. 当前恢复入口没有记录“旧进程已停止”的外部证据，也未完整校验所有阶段产物，调用者
   和部署流程必须先确认旧 worker 已退出；
4. worker 下一次领取递增 attempt；领取前不显示 running。

### Cancel

- queued/paused job 没有 active owner 时，可由协调逻辑直接确认 cancelled；
- running job 由 owner 在安全点停止工作并清理后确认 cancelled；
- interrupted job 必须先确认旧执行已停止，再确认 cancelled。

### Delete

delete 是两阶段动作：先达到 succeeded/failed/cancelled 等可清理状态，再删除 workspace
与关联数据。清理完成前保持 `delete_requested`，并返回 `DELETE_PENDING_CLEANUP`。

## 4. Command × ExecutionState

`ALLOW` 表示可以创建请求；`NOOP` 表示返回现有结果；`ERROR` 表示拒绝。

| ExecutionState | pause | resume | cancel | delete |
| --- | --- | --- | --- | --- |
| `queued` | `NOOP` | `ERROR` | `ALLOW` | `ALLOW` |
| `running` | `ALLOW` | `NOOP` | `ALLOW` | `ALLOW` |
| `paused` | `NOOP` | `ALLOW` | `ALLOW` | `ALLOW` |
| `interrupted` | `NOOP` | `ALLOW` | `ALLOW` | `ALLOW` |
| `succeeded` | `NOOP` | `NOOP` | `NOOP` | `ALLOW` |
| `failed` | `NOOP` | `NOOP` | `NOOP` | `ALLOW` |
| `cancelled` | `NOOP` | `NOOP` | `NOOP` | `ALLOW` |

同一 request ID 必须幂等。当前 schema 只保存最新控制请求；不同 request ID 在状态版本
仍匹配时可以由后一个命令取代前一个，完整命令历史和显式冲突矩阵尚未实现。

## 5. Stage 状态

stage 状态为：

`pending -> running -> succeeded|failed|skipped`

- `skipped` 只用于配置明确禁用或依赖规则明确跳过的阶段；
- provider 失败、空响应或缺少必要配置不能标记 skipped；
- 恢复只能复用输入指纹、配置指纹和产物校验全部匹配的 succeeded stage；
- running worker 异常终止时，job 标记 interrupted；当前 checkpoint 没有独立 stage
  interrupted 值。

## 6. 版本、幂等与错误

- 每次已提交的状态变化递增 `state_version`；
- 每个命令携带稳定 `request_id`，重复请求返回同一持久结果；
- 条件更新必须校验旧 `state_version` 或 owner attempt，避免陈旧 worker 覆盖新状态；
- worker 只能更新自己持有的 attempt。

错误码至少包括：

- `INVALID_STATE_TRANSITION`；
- `ALREADY_IN_TARGET_STATE`；
- `JOB_NOT_ACTIVE`；
- `DELETE_PENDING_CLEANUP`；
- `CONTROL_CONFLICT`（已注册，当前控制路径尚未返回）；

后续新增错误码时必须先进入 `packages/core/error_codes.py` 或对应模块的稳定错误注册表，
不能只在文档中声明。
