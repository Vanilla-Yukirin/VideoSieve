# VideoSieve 架构基线

日期：2026-09-21。

本文定义 VideoSieve 面向“一台电脑或服务器、个人／少量用户”的目标架构。
架构决策和核心单机运行时已经实现；自动化测试与真实模型端到端验收仍分开记录。
本文不把“代码存在”描述为已经上线或通过真实内容验收。

旧的 Celery + Redis 长方案保留在 [ARCHITECTURE-old.md](ARCHITECTURE-old.md)，
旧重写草稿保留在 [ARCHITECTURE-rewrite.md](ARCHITECTURE-rewrite.md)。它们仅用于
追溯，不再指导实现。正式选型见
[ADR-0005](adr/ADR-0005-single-host-sqlite-worker.md)。

## 1. 产品目标与范围

给定 B 站链接或本地视频，生成可追溯的媒体知识资产：

- 带时间戳的真实转写；
- 关键帧及真实画面描述；
- 按时间轴融合的图文笔记；
- 覆盖全文、由模型实际生成的整理稿与摘要；
- 可恢复的排队、进度、暂停、继续、取消、重跑和产物查看。

首版运行范围：

- 单主机、本地磁盘、单个独立 worker 进程；
- 一个 worker 同时处理一个视频任务，多个任务可排队；
- Web 可供个人或少量受信用户访问；
- 不要求多节点调度、高可用或高写入并发。

当确实需要多台计算节点、高并发写入或高可用时，再重新评估服务端数据库和
消息队列。不能为了未经验证的未来规模提前引入 Celery、Redis 或通用工作流引擎。

## 2. 重做开始时的实现基线与迁移边界

2026-09-20 重做审计时（代码基线 `3e45fd5`），仓库是“已有实现但不完整的原型”：

- FastAPI 默认在 API 进程内启动后台线程执行 job；
- `workers/celery_app.py` 是普通 Python 适配入口，不是运行中的 Celery worker；
- `RedisEventBus` 的可用路径是进程内分发，真实 Redis 发布/订阅尚未实现；
- SQLite 已保存部分项目、任务、设置和操作记录，但尚未实现本文的持久队列、
  attempt、游标事件和独立 worker 领取协议；
- 前端当前仍大量使用 REST，并以 HTTP snapshot 加 WebSocket 增量工作；
- 暂停请求与执行器确认尚未形成可靠的跨进程闭环；
- ASR 默认 mock、画面摘要占位降级和拼接式摘要仍是待修缺陷。

当前提交已移除 API 默认后台线程执行，接入 SQLite 原子领取、attempt/心跳/显式恢复、
持久事件游标、独立 worker 和任务页 WebSocket 控制，并让三类模型漏配或失败显式暴露。
跨进程领取与恢复、WebSocket 重连和 provider 失败已有自动测试。ASR 已改为外部
CapsWriter 官方 WebSocket adapter，并删除内置模型运行时。真实视频、真实
ASR/VLM/LLM 的输出质量和进程托管仍须按 [质量门禁](QUALITY.md) 与
[harness](harness/README.md) 验收。

## 3. 目标组件

```text
浏览器
  │
  ├─ HTTP：设置、项目/任务创建、上传、下载、健康检查
  │
  └─ WebSocket：job 快照、控制、确认、进度、日志、错误事件
               │
            FastAPI
               │
          SQLite（本机）
               │
      独立 Python worker
               │
    FFmpeg / 外部 ASR / VLM / LLM
               │
       workspace（本地文件系统）
```

### 3.1 Next.js Web

- 任务页通过 WebSocket 获取 job 快照、发送控制命令并接收增量事件；
- 使用事件游标和状态版本处理重连、去重及乱序；
- 通过 HTTP 完成设置、项目/任务创建、上传、播放、下载和健康检查；
- 明确展示“请求已接收”和“worker 已确认生效”的区别。

### 3.2 FastAPI

- 管理 WebSocket 连接、命令校验与持久化；
- 创建 job 时先完整写入配置快照，再提交可领取的排队记录；
- 从 SQLite 读取一致快照与持久事件，向 WebSocket 客户端重放和推送；
- 提供受路径约束的上传、播放和产物下载；
- 不在 API 进程内执行媒体流水线。

### 3.3 SQLite

SQLite 是单机上的协调与事实存储。当前 schema 保存：

- `projects` 和 `jobs`；job 行包含 stage、progress、错误、owner、attempt 计数与心跳；
- 当前控制命令、request ID、版本以及 worker 确认版本；
- 带单调游标的 `job_events`；
- 设置、Provider credential、Cookie Vault 和操作记录。

当前没有独立的 `job_stages`、`job_attempts` 或 `artifacts` 表。阶段检查点和配置快照
位于 workspace；最终产物由 `deliverables.ready.json` 索引，API 会核对文件大小和
SHA-256 后才暴露。attempt 历史若以后需要，须另做 schema 迁移，不能从当前 attempt
计数推导完整审计记录。

数据库不保存视频、音频、图片或大段模型输入输出。长耗时下载、解码、推理和网络
调用不得占用数据库事务。

### 3.4 独立 Python worker

- 以短事务原子领取一个 queued job；
- 从不可变 job 配置快照构建流水线；
- 在昂贵调用前后、阶段边界和长循环内检查控制请求；
- 在 job 行保存当前 attempt、stage、状态与心跳，并持久化事件；
- 崩溃或进程终止后留下可识别的 `interrupted` 证据，等待人工或受控恢复；
- 不承载业务算法，算法继续位于 `packages/*`。

首版用 OS 级单实例锁限制一个 worker。不能仅因心跳超时就重复派发一个可能仍在
运行的任务；恢复前必须确认旧 worker 及受管理子进程已经退出。

### 3.5 本地 workspace

重数据按 project/job 隔离，规范以
[workspace-layout.md](10_system/workspace-layout.md) 为准。当前 deliverables 先写同目录
generation 临时文件，全部校验后逐个原子替换 canonical 文件，并把 readiness manifest
最后发布。其它中间阶段尚未统一成 attempt 专属临时目录。

## 4. 端到端信息流

1. 浏览器通过 HTTP 创建项目或任务；本地文件先上传到该项目的受限 staging 目录，
   创建请求只引用服务端返回的 staging 路径。
2. API 校验输入，冻结 job 配置快照；快照写入成功后才在 SQLite 提交 queued job。
3. worker 通过条件更新原子领取 job，创建 attempt，将确认状态改为 running。
4. worker 执行固定流水线：
   `ingest -> hotwords -> asr -> keyframes -> frame_summary -> fusion -> deliverables`。
5. 每个阶段把重数据写入 workspace，把状态、进度和错误写入 SQLite；
   进度事件需要限频或合并。
6. API 按 `event_id` 读取持久事件并通过 WebSocket 推送。内存通知可以减少轮询延迟，
   但不能成为可靠性或恢复的前提。
7. 浏览器重连时携带最后确认的事件游标。服务端重放该 cursor 之后的现存事件，再发送
   权威快照。当前事件表不裁剪；实现保留期时必须补 cursor reset 协议。

## 5. 接口边界

当前接口边界是：

- HTTP：设置、项目与 job 的创建/查询/删除、Cookie Vault、上传、媒体/产物下载，
  以及当前仅表示 API 进程存活的 `/healthz`；
- WebSocket：单个 job 的权威 snapshot、cursor 重放、实时进度/日志/错误和
  pause/resume/cancel/delete 控制；
- 项目列表和设置目前仍是 HTTP，不把尚未实现的全业务 WS 写成现状。

产品内没有账号、登录、游客或会话鉴权。HTTP 文件传输和 WebSocket 控制都假定调用者
已经进入 single-host trusted boundary。Web/API 默认只绑定回环地址；远程访问必须由
Tailscale、Yukirin Gateway 或认证反向代理提供外层访问控制。不要通过 WebSocket 传输
大视频或产物文件，也不要把下载 URL 当作业务状态真相。

## 6. 状态、控制与确认

job 的执行状态只表示系统已经确认的事实；请求态独立记录。详细契约见
[state-machine.md](10_system/state-machine.md)。

- `queued/running/paused` 是执行确认态；
- `pause_requested/cancel_requested/resume_requested/delete_requested` 是请求态；
- 请求入库且通过合法性检查，只能确认 `accepted`；
- pause 已接受时，job 仍可能是 running，UI 应显示“正在暂停”；
- worker 到达安全点、保存检查点并释放当前执行后，才把 job 确认为 paused；
- cancel 已接受时，job 仍可能在清理子进程；清理完成后才确认为 cancelled；
- resume 从已验证边界重新入队，下一 attempt 领取后才重新确认为 running；
- delete 必须等待执行停止与文件写入结束，再执行清理并确认；
- worker 失联后进入 `interrupted` 恢复态，不能因心跳超时自动重新领取。

所有命令携带稳定 `request_id`。重复发送同一请求必须返回同一持久结果，不能执行两次。

## 7. 事件与断线恢复

事件保存在 SQLite，`event_id` 单调递增并作为 cursor。数据库行包含 channel、
project/job、event type、payload、timestamp、state version 和可选 request ID。当前
WebSocket 信封发送 `event_type`、`cursor`、`state_version`、`request_id` 和 `payload`；
`schema_version` 尚未加入线上信封。

快照是状态事实，持久事件用于增量、审计和有限期重放；两者都通过 WebSocket 传给
已建立连接的客户端。`state_version` 小于客户端当前版本的状态更新必须被忽略，日志等
追加事件按 `event_id` 去重。

断线恢复和游标过期规则以
[events-and-websocket.md](10_system/events-and-websocket.md) 为准。

## 8. SQLite 并发与恢复约束

- 数据库文件必须位于本机磁盘，不能放到网络文件系统供多机同时使用；
- 启用 WAL、每连接 `foreign_keys=ON` 和合理的 `busy_timeout`；
- API 与 worker 使用独立连接，只做短事务；
- 业务状态变化与对应持久事件必须在同一事务提交，不能出现“状态已变但没有 cursor”窗口；
- API 负责连接、控制命令、job 创建和业务配置写入；
- worker 负责领取、当前 attempt、stage、执行状态和执行事件写入；
- 写冲突必须按受限退避重试，耗尽后产生明确错误；
- checkpoint 只是 WAL 维护，不等于任务崩溃恢复；
- 外部模型调用无法承诺 exactly-once，必须保存已确认分块并展示不确定调用。

## 9. 模型与产物可信性

- 生产路径必须显式选择真实 ASR/VLM/LLM provider；mock 只能通过测试注入；
- 缺配置、鉴权失败、超时、异常、畸形或空响应不能转成成功占位内容；
- 原始转写、原始模型响应／元数据与模型改写产物分开保存；
- 摘要需要覆盖完整输入，长视频按预算分段总结后再汇总，记录来源覆盖；
- 必要阶段失败时 job 不能报告完整成功，已经完成的真实中间产物仍可查看；
- 产物发布必须经过完整写入、格式校验和引用一致性检查。

## 10. 代码边界

- `apps/api`：WS/HTTP 边界、命令和文件访问；
- `apps/web`：页面、WS 客户端状态机与文件传输 UI；
- `workers`：独立进程启动、依赖装配和任务领取循环；
- `packages/contracts`：跨模块类型和协议；
- `packages/core`：状态机、错误和配置规则；
- `packages/infra`：SQLite、workspace、provider 等适配；
- `packages/pipeline`：阶段编排、恢复和安全点；
- 其余 `packages/*`：各业务算法与产物生成。

路由和 worker 入口保持薄；跨模块数据走显式契约；业务包不读取 Web 状态、直接操作
WebSocket 或依赖具体 SQLite ORM 实现。

## 11. 实施门槛

每个目标能力都必须经历“契约更新、代码实现、自动测试、真实验收”四个层级。至少验证：

- 两个领取者不能领取同一 job；
- API 重启不终止 worker，队列与事件可恢复；
- worker 崩溃被识别，任务不会永久伪装为 running；
- pause/cancel 的 accepted 与 applied 不混淆；
- WS 重连不会漏掉保留期内事件，也不会用旧状态覆盖新状态；
- 损坏或半写产物不会被宣布 ready；
- 真实视频经过真实 ASR、VLM 和 LLM，失败不会生成模拟成功。

测试文件存在、mock 测试通过或 Markdown 链接正确，都不能替代真实运行验收。
