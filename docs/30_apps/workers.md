# App: workers

状态：已实现。`workers/single_host.py` 是 SQLite 队列的独立进程入口；
`workers/celery_app.py` 只保留薄适配器名称，不表示存在 Celery 运行时。自动化测试覆盖
跨进程领取与恢复，真实媒体执行仍按 harness 单独验收。

## Purpose

独立 Python worker 在 API 进程之外消费 SQLite 持久队列，装配并调用 `packages/*`
流水线。首版单主机只运行一个 worker，一次执行一个视频 job。

```powershell
uv run python -m workers.single_host --data-dir runtime/api
```

## Responsibilities

- 启动时取得 OS 级单实例锁并注册 worker identity；
- 通过短事务原子领取 queued job，创建唯一 attempt；
- 读取并校验不可变 job config snapshot；
- 调用 pipeline stage，不在入口层实现业务算法；
- 更新心跳、stage、执行确认态、持久事件和产物索引；
- 检查 pause/cancel/delete 请求并在安全点应用；
- 受控管理 FFmpeg、yt-dlp、本地模型等子进程；
- 优雅退出时停止领取新任务，处理当前 attempt 并留下明确结束原因。

## Claim Loop

1. 以 `BEGIN IMMEDIATE` 或等价条件更新开启短事务；
2. 选取符合排序规则的 queued job；
3. 条件更新 owner、attempt 和 execution state，确保恰好一个领取者成功；
4. 提交后再加载媒体、模型或调用外部服务；
5. 空队列使用有上限的轮询退避，不能保持写事务等待。

领取协议的并发正确性必须用两个独立连接／进程测试，单对象单测不足以证明安全。

## Safety Points

- 每个 stage 开始和结束；
- FFmpeg、yt-dlp 或 provider 调用前后；
- 长循环按时间或 item 数定期检查；
- 分块 ASR／总结每个已持久化分块之间；
- 发布最终产物之前。

API 写入请求只产生 `accepted` ack。worker 到达安全点、保存恢复边界并停止／清理后，
才写 `applied` ack 和 paused/cancelled 确认态。

## Heartbeat and Recovery

- worker 与 active attempt 周期性更新心跳；
- 心跳超时只把 job 置为 `interrupted`／需要恢复；
- 超时不得自动重新入队，也不得自动启动第二个 attempt；
- 恢复前确认旧 worker 和受管理子进程均已停止；
- 校验 stage 输入／配置指纹和产物后，显式恢复到 queued；
- 外部调用可能已经收费但未保存响应，恢复记录必须保留这种不确定性。

## Artifact Publishing

- 写入 attempt 专属临时目录；
- fsync／关闭文件后执行格式、完整性和引用校验；
- 在同一文件系统内原子重命名到 canonical path；
- 再用短事务登记 artifact 和 `artifact_ready`；
- 启动恢复时检查“文件已发布但数据库未提交”的窗口，不能直接宣布成功。

## Shutdown

收到服务停止信号后：

1. 停止领取新 job；
2. 请求当前 stage 在安全点结束；
3. 在宽限期内保存状态并释放子进程；
4. 无法安全完成时把 attempt 标记 interrupted，保留诊断信息；
5. 释放单实例锁。

强制杀进程不是普通 pause/cancel 实现。

## Verification

- 两个领取者不能获得同一 job；
- API 重启不影响 active worker；
- worker 崩溃会留下 interrupted，而不是永久 running 或自动重复执行；
- accepted pause/cancel 在实际安全点前不显示 applied；
- 产物半写、SQLite busy、provider 超时和子进程退出均产生可诊断结果。
