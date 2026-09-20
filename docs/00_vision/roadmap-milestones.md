# Roadmap and Milestones

状态：目标路线，未完成项不能按文档标记为已实现。

## P0 - 契约与质量基线

- 明确当前实现、目标设计、自动测试与真实验收的边界
- 固化状态机、WS cursor、配置快照、错误和产物契约
- 建立不可被 skip 或累计分数绕过的仓库 harness

## P1 - 可信模型闭环

- 生产路径移除 ASR mock 和画面摘要占位成功
- 真实 ASR + frame summary + overall summary
- 原始证据、模型生成结果和 provider 元数据分开保存

## P2 - 单机可靠执行

- SQLite 持久队列、独立 Python worker 和 attempt ownership
- 请求态与执行确认态分离
- 递增事件 cursor、WS snapshot/replay 和 interrupted 显式恢复

## P3 - 关键帧与图文交错

- stable-frame（先全帧）
- diff 曲线与关键帧预览
- VLM-only frame summary + timeline + illustrated notes

## P4 - 复杂视频与运行收尾

- ROI stable、聚类代表帧
- ASR 二次校正与策略兜底
- Windows/Linux 目标环境复现、部署与真实视频验收

## Exit Criteria

- 每个阶段有可验证产物
- 所有控制命令区分 accepted 与 worker-confirmed applied
- worker/API 重启、WS 断线和半写产物场景通过进程级测试
- 真实 ASR/VLM/LLM 结果通过人工内容抽查
