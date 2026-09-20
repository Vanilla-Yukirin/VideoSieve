# Job State Machine

状态：目标契约，独立 worker 迁移完成前不得标记为已实现。

## 1. 三类状态不能混用

### 1.1 执行确认态 `execution_state`

`execution_state` 只记录系统已经确认的执行事实：

- `queued`：已持久入队，当前没有 worker owner；
- `running`：某个 attempt 已原子领取并正在执行；
- `paused`：worker 已到达安全点、保存检查点并释放当前执行；
- `succeeded`：必要阶段与产物已经校验成功；
- `failed`：执行以明确错误结束；
- `cancelled`：worker 或协调器已确认不再执行，并完成必要清理；
- `interrupted`：原 attempt 失去可靠所有权或异常终止，需要恢复判定。

`queued/running/paused` 是执行确认态。`pause_requested`、`cancel_requested` 等不是
执行结果，不能写入同一字段伪装成已停止。

### 1.2 请求态 `requested_action`

控制意图独立保存：

- `none`；
- `pause_requested`；
- `resume_requested`；
- `cancel_requested`；
- `delete_requested`；
- `recover_requested`。

每条控制请求还拥有独立生命周期：

- `accepted`：已持久化且当前语义合法；
- `applied`：负责执行的一方已确认动作生效；
- `rejected`：命令不合法或与当前状态冲突；
- `failed`：命令合法并被接受，但执行动作失败。

`accepted` 不能当作 `applied`。UI 可把 `running + pause_requested` 显示为“正在暂停”，
但不得显示为“已暂停”。

### 1.3 Attempt 状态

一次领取产生一个不可复用的 `attempt_id`：

- `active`：worker 持有 job；
- `completed`：正常结束；
- `interrupted`：异常失联或进程退出；
- `abandoned`：恢复流程确认旧执行已终止并放弃该 attempt。

新 attempt 不能复用旧 attempt 的临时输出目录。

## 2. 执行状态转换

```text
create -> queued -> running -> succeeded
                    |   |
                    |   +-> failed
                    |   +-> cancelled
                    |   +-> paused -> queued -> running
                    |
                    +-> interrupted -> queued    (显式恢复并确认旧执行已停止)
                                  \-> failed
                                  \-> cancelled

queued -> cancelled
paused -> cancelled
```

规则：

1. `queued -> running` 只能由 worker 的原子领取事务完成，并创建新 attempt。
2. `running -> paused` 只能由当前 owner 在安全点保存检查点并释放执行后完成。
3. `paused -> queued` 是已接受 resume 的应用结果；随后由新 attempt 领取。
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

### Resume

1. 仅 paused job 可接受 `resume_requested`。
2. 协调逻辑校验检查点和配置指纹后，将 job 置为 queued，并把请求标记 applied。
3. worker 下一次领取创建新 attempt；领取前不显示 running。

### Cancel

- queued/paused job 没有 active owner 时，可由协调逻辑直接确认 cancelled；
- running job 由 owner 在安全点停止工作并清理后确认 cancelled；
- interrupted job 必须先确认旧执行已停止，再确认 cancelled。

### Delete

delete 是两阶段动作：先达到 succeeded/failed/cancelled 等可清理状态，再删除 workspace
与关联数据。清理完成前保持 `delete_requested`，并返回 `DELETE_PENDING_CLEANUP`。

### Recover

recover 只允许用于 interrupted job。恢复流程必须记录操作者／监督器、旧 attempt、
进程终止证据、产物校验结果和新的恢复边界。

## 4. Command × ExecutionState

`ALLOW` 表示可以创建请求；`NOOP` 表示返回现有结果；`ERROR` 表示拒绝。

| ExecutionState | pause | resume | cancel | delete | recover |
| --- | --- | --- | --- | --- | --- |
| `queued` | `ERROR` | `ERROR` | `ALLOW` | `ALLOW` | `ERROR` |
| `running` | `ALLOW` | `ERROR` | `ALLOW` | `ALLOW` | `ERROR` |
| `paused` | `NOOP` | `ALLOW` | `ALLOW` | `ALLOW` | `ERROR` |
| `interrupted` | `ERROR` | `ERROR` | `ALLOW` | `ALLOW` | `ALLOW` |
| `succeeded` | `ERROR` | `ERROR` | `NOOP` | `ALLOW` | `ERROR` |
| `failed` | `ERROR` | `ERROR` | `NOOP` | `ALLOW` | `ERROR` |
| `cancelled` | `ERROR` | `ERROR` | `NOOP` | `ALLOW` | `ERROR` |

同一 job 已存在未完成控制请求时，新请求必须按命令组合规则去重、合并或返回
`CONTROL_CONFLICT`，不能通过后写覆盖先写隐藏竞争。

## 5. Stage 状态

stage 状态为：

`pending -> running -> succeeded|failed|skipped|interrupted`

- `skipped` 只用于配置明确禁用或依赖规则明确跳过的阶段；
- provider 失败、空响应或缺少必要配置不能标记 skipped；
- 恢复只能复用输入指纹、配置指纹和产物校验全部匹配的 succeeded stage；
- running attempt 异常终止时，当前 stage 标记 interrupted，不伪装为 pending 或 failed。

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
- `CONTROL_CONFLICT`；
- `STALE_STATE_VERSION`；
- `ATTEMPT_OWNERSHIP_LOST`；
- `RECOVERY_REQUIRES_STOP_CONFIRMATION`。
