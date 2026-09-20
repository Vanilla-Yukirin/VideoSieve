# Deployment

状态：单机目标部署。各运行单元只有在启动、重启和故障验收通过后才算可用。

## 1. Runtime Units

首版部署由四部分组成：

- Next.js Web；
- FastAPI API / WebSocket gateway；
- 独立 Python worker；
- 同一主机上的 SQLite 数据库和 workspace 本地磁盘。

不启动 Redis、Celery worker 或 broker。独立 worker 入口为
`python -m workers.single_host`；薄执行适配器位于 `workers/runtime.py`。

可以先用本机进程运行，也可以分别容器化 API/Web/worker。无论采用哪种方式，SQLite
文件与 workspace 必须位于同一主机的可靠本地文件系统。

## 2. Process Isolation

- API 和 worker 是独立进程，API 重启不能终止媒体任务；
- worker 入口已经使用单实例文件锁；正式部署还需配置 OS 服务管理器；
- API 与 worker 使用各自 SQLite 连接，启用 WAL、`foreign_keys=ON` 和 busy timeout；
- 长计算和网络调用在事务外执行；
- API 与 worker 必须解析到同一个 canonical workspace root；
- 不把 SQLite 数据库放在 NFS/SMB 等网络共享上供多主机访问。

Windows 可使用受管理后台服务／进程；Linux 可使用 systemd 或等价服务管理器。当前
开发启动命令见 `how_to_run.md`；正式服务托管仍需在目标环境验证退出、重启和日志行为。

## 3. Storage

至少持久化：

- SQLite 主文件及 WAL/SHM 同目录；
- workspace 原始媒体、中间结果、最终产物和必要日志；
- 受保护的 secret store 或环境注入配置。

备份必须把数据库一致性与 workspace 文件版本对应起来。仅复制 SQLite 主文件可能遗漏
WAL 内容；运行中备份使用 SQLite backup API 或经过验证的停机流程。

产物写到临时路径并原子发布。数据库和 workspace 容量不足都应阻止领取新任务并返回
明确诊断，不能继续生成半文件。

## 4. Configuration and Secrets

API 最低启动配置包括：

- `APP_SECRET_KEY`；
- SQLite 路径；
- workspace 根目录；
- Web origin / cookie / session 安全策略。

worker 最低启动配置包括：

- 同一 SQLite 路径和 workspace 根目录；
- worker identity、轮询和心跳参数；
- FFmpeg/ffprobe 等外部工具路径；
- job snapshot 中 provider 所引用的真实凭据或本地模型路径。

模型 key、cookie 和 token 不使用 `NEXT_PUBLIC_*`，不写入普通 job snapshot。前端公开
配置只包含公开 origin、版本或 UI feature hint。

## 5. Health and Readiness

当前 `GET /healthz` 只返回 API liveness。它不检查数据库可写、schema、workspace、
worker 或 provider，因此不能作为 readiness 证明。active job 行会保存 worker ID、当前
attempt 和 heartbeat；仓库目前没有独立 worker registry，也没有空闲 worker heartbeat
或 readiness endpoint。部署验收需要另外检查 worker 进程/锁，并创建受控任务观察领取。

worker 心跳超时只触发告警并把 active job 标记为 interrupted／需要恢复，不能自动
重新领取可能仍在执行的任务。

## 6. Startup Order

1. 校验备份／迁移前置条件；
2. 初始化或迁移 SQLite schema；
3. 启动 API，检查 liveness，并另行验证数据库与 workspace；
4. 启动单个 worker，确认第二实例会被锁拒绝，再用受控任务验证领取与 heartbeat；
5. 启动 Web 或开放入口；
6. 用 WebSocket 建连、snapshot 和 cursor 重连检查验证控制面。

若 worker 尚未启动，API 当前仍会接受 job 并保持 queued；它不会在 API 内回退为后台
线程，也还不会显示“无 worker”的专用排队原因。

## 7. Upgrade and Recovery

- 升级前停止领取新任务；
- 让 active attempt 在安全点结束，或明确标记 interrupted；
- 备份数据库与 workspace 元数据；
- 运行版本化迁移后再启动新进程；
- 不跨不兼容 schema 版本自动恢复旧 job；
- interrupted job 由显式恢复操作处理，确认旧进程已停止并校验产物。

回滚必须同时考虑代码、数据库 schema 和产物 schema。只有代码回滚而数据库不可逆迁移
时，不得声称可回滚。

## 8. Deployment Acceptance

- 冷启动和重启后 queued job 保留；
- API 单独重启时 worker 当前任务继续；
- worker heartbeat 超时后，另一个正在运行的 worker 轮询会把 job 标为 interrupted；
  若没有 worker 进程，状态不会自行推进，部署监控必须检测进程退出；
- WebSocket 断线后通过递增 cursor 恢复；
- HTTP 上传／下载与 WS 业务控制使用一致的访问权限；
- SQLite busy、磁盘满、凭据缺失、模型失败都有明确健康或任务错误；
- 使用真实视频与真实 provider 完成一次端到端验收。
