# Deployment

状态：单机目标部署。各运行单元只有在启动、重启和故障验收通过后才算可用。

## 1. Runtime Units

首版部署由四部分组成：

- Next.js Web；
- FastAPI API / WebSocket gateway；
- 独立 Python worker；
- 同一主机上的 SQLite 数据库和 workspace 本地磁盘。

不启动 Redis、Celery worker 或 broker。`workers/celery_app.py` 的历史文件名不代表
Celery 已被采用，迁移时应提供清楚的独立 worker 启动入口。

可以先用本机进程运行，也可以分别容器化 API/Web/worker。无论采用哪种方式，SQLite
文件与 workspace 必须位于同一主机的可靠本地文件系统。

## 2. Process Isolation

- API 和 worker 是独立进程，API 重启不能终止媒体任务；
- worker 使用 OS 服务管理器和单实例锁，首版禁止多个实例同时运行；
- API 与 worker 使用各自 SQLite 连接，启用 WAL、`foreign_keys=ON` 和 busy timeout；
- 长计算和网络调用在事务外执行；
- API 与 worker 必须解析到同一个 canonical workspace root；
- 不把 SQLite 数据库放在 NFS/SMB 等网络共享上供多主机访问。

Windows 可使用受管理后台服务／进程；Linux 可使用 systemd 或等价服务管理器。具体启动
命令只有在代码入口实现并实际验证后才写入 `how_to_run.md`。

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

HTTP 健康检查只报告服务运行与依赖就绪，不充当业务状态查询：

- API liveness：事件循环可响应；
- API readiness：数据库可读写、迁移版本匹配、workspace 可访问；
- worker heartbeat：最近心跳、当前 attempt 和单实例锁 owner；
- Web health：静态资源可提供。

worker 心跳超时只触发告警并把 active job 标记为 interrupted／需要恢复，不能自动
重新领取可能仍在执行的任务。

## 6. Startup Order

1. 校验备份／迁移前置条件；
2. 初始化或迁移 SQLite schema；
3. 启动 API 并通过 readiness；
4. 启动单个 worker，确认锁和 heartbeat；
5. 启动 Web 或开放入口；
6. 用 WebSocket 建连、snapshot 和 cursor 重连检查验证控制面。

若 worker 尚未就绪，API 可以接受浏览和下载，但创建 job 必须明确显示排队原因或拒绝，
不能在 API 内悄悄回退为后台线程执行。

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
- worker 异常退出后 job 进入 interrupted，不出现双执行；
- WebSocket 断线后通过递增 cursor 恢复；
- HTTP 上传／下载与 WS 业务控制使用一致的访问权限；
- SQLite busy、磁盘满、凭据缺失、模型失败都有明确健康或任务错误；
- 使用真实视频与真实 provider 完成一次端到端验收。
