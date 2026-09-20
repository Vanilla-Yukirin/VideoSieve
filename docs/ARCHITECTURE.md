# VideoSieve 架构基线

日期：2026-09-20。

本文定义 VideoSieve 面向“一台电脑或服务器、个人／少量用户”的目标架构。
架构决策已经确定，代码迁移仍在进行；除“当前实现”小节外，本文的目标行为
不得被描述为已经上线或通过端到端验收。

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

后续提交可能逐项修复这些基线缺陷，完成状态以对应代码、自动测试和真实验收证据为准。
本文中的完整独立 worker、SQLite 事件重放、纯 WebSocket 业务控制等仍是目标契约，
不能因局部类或测试出现就整体标成“已实现”。详细缺陷与实施顺序见
[单机重做方案](00_vision/rebuild-plan.md)。

## 3. 目标组件

```text
浏览器
  │
  ├─ HTTP：页面/会话引导、上传、下载、健康检查
  │
  └─ WebSocket：业务快照、命令、确认、进度、日志、产物事件
               │
            FastAPI
               │
          SQLite（本机）
               │
      独立 Python worker
               │
    FFmpeg / ASR / VLM / LLM
               │
       workspace（本地文件系统）
```

### 3.1 Next.js Web

- 建立会话后，通过 WebSocket 获取项目／任务快照、发送业务命令并接收增量事件；
- 使用事件游标和状态版本处理重连、去重及乱序；
- 通过 HTTP 上传源文件、播放／下载大文件，并访问健康检查或初始登录引导；
- 明确展示“请求已接收”和“worker 已确认生效”的区别。

### 3.2 FastAPI

- 管理认证、WebSocket 会话、命令校验与持久化；
- 创建项目和 job 时，原子写入配置快照引用与排队记录；
- 从 SQLite 读取一致快照与持久事件，向 WebSocket 客户端重放和推送；
- 提供受路径约束的上传、播放和产物下载；
- 不在 API 进程内执行媒体流水线。

### 3.3 SQLite

SQLite 是单机上的协调与事实存储，保存：

- `projects`、`jobs` 和 `job_stages`；
- 控制请求及其 accepted/applied/rejected 状态；
- `job_attempts`、worker 心跳和结束原因；
- 带单调游标的 `job_events`；
- 产物索引、配置版本和操作记录。

数据库不保存视频、音频、图片或大段模型输入输出。长耗时下载、解码、推理和网络
调用不得占用数据库事务。

### 3.4 独立 Python worker

- 以短事务原子领取一个 queued job；
- 从不可变 job 配置快照构建流水线；
- 在昂贵调用前后、阶段边界和长循环内检查控制请求；
- 保存 attempt、stage、状态、事件和产物引用；
- 崩溃或进程终止后留下可识别的 `interrupted` 证据，等待人工或受控恢复；
- 不承载业务算法，算法继续位于 `packages/*`。

首版用 OS 级单实例锁限制一个 worker。不能仅因心跳超时就重复派发一个可能仍在
运行的任务；恢复前必须确认旧 worker 及受管理子进程已经退出。

### 3.5 本地 workspace

重数据按 project/job 隔离，规范以
[workspace-layout.md](10_system/workspace-layout.md) 为准。产物先写 attempt 专属临时路径，
校验完整后再原子发布，并在短事务内记录产物索引与成功事件。

## 4. 端到端信息流

1. 浏览器建立 WebSocket 会话，发送带 `request_id` 的创建命令；本地文件本体先通过
   HTTP 上传，命令只引用已经确认的上传对象。
2. API 校验输入和模型能力配置，冻结 job 配置快照，在同一短事务中写入 queued job、
   命令结果和事件。
3. worker 通过条件更新原子领取 job，创建 attempt，将确认状态改为 running。
4. worker 执行固定流水线：
   `ingest -> hotwords -> asr -> keyframes -> frame_summary -> fusion -> deliverables`。
5. 每个阶段把重数据写入 workspace，把状态、进度、错误和产物引用写入 SQLite；
   进度事件需要限频或合并。
6. API 按 `event_id` 读取持久事件并通过 WebSocket 推送。内存通知可以减少轮询延迟，
   但不能成为可靠性或恢复的前提。
7. 浏览器重连时携带最后确认的事件游标。服务端重放仍在保留期内的事件，并发送
   权威快照；若游标已过期则明确要求从快照重置。

## 5. 接口边界

目标协议中，HTTP 只承担：

- Web 页面、静态资源及初始认证／会话引导；
- 本地媒体上传；
- 源视频播放和产物下载；
- liveness/readiness 健康检查。

以下业务交互统一使用 WebSocket：

- 项目和 job 的列表、详情与当前快照；
- 创建 job、更新业务设置和阶段重跑；
- pause/resume/cancel/delete；
- 日志、进度、状态、错误与产物索引增量。

HTTP 文件传输和 WebSocket 控制共享同一认证与授权规则。不要通过 WebSocket 传输
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

事件保存在 SQLite，`event_id` 单调递增并作为 cursor。事件信封至少包含：

- `schema_version`、`event_id`、`event_type`；
- `project_id`、`job_id`、`state_version`；
- `ts`、`payload`，命令相关事件另含 `request_id`。

快照是状态事实，持久事件用于增量、审计和有限期重放；两者都通过 WebSocket 传给
已建立会话的客户端。`state_version` 小于客户端当前版本的状态更新必须被忽略，日志等
追加事件按 `event_id` 去重。

断线恢复和游标过期规则以
[events-and-websocket.md](10_system/events-and-websocket.md) 为准。

## 8. SQLite 并发与恢复约束

- 数据库文件必须位于本机磁盘，不能放到网络文件系统供多机同时使用；
- 启用 WAL、每连接 `foreign_keys=ON` 和合理的 `busy_timeout`；
- API 与 worker 使用独立连接，只做短事务；
- 业务状态变化与对应持久事件必须在同一事务提交，不能出现“状态已变但没有 cursor”窗口；
- API 负责会话、命令、job 创建和业务配置写入；
- worker 负责领取、attempt、stage、执行状态、产物和执行事件写入；
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

- `apps/api`：认证、WS/HTTP 边界、命令和文件访问；
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
