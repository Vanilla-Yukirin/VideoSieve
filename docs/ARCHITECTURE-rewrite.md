# VideoSieve 全面重构架构规划（v0.1）

本文件是重构后的正式架构基线，目标是把项目从“可运行原型”升级为“可持续演进的平台化工程”。

默认技术选型：`FastAPI + Redis + Celery + WebSocket + Next.js + SQLite`，并保留平滑迁移至 Postgres 的路径。

## 1. 目标、边界与原则

### 1.1 产品目标

输入 `B站链接` 或 `本地视频`，输出可复用知识资产：

- 转译稿（清洗口语与重复、结构化、保真）
- 图文交错笔记（关键帧与字幕对齐，可回填引用）
- 摘要（100-500 字）与标题
- 全流程控制（并行、日志、进度、暂停/继续/终止/删除）

### 1.2 非目标（当前阶段不做）

- 复杂多租户权限体系
- 向量检索/全文检索平台能力
- 覆盖所有视频类型的“完美抽帧”

### 1.3 架构原则（必须执行）

1. `apps` 负责运行与部署边界，`packages` 负责可复用逻辑。
2. `workers` 只负责执行入口与启动编排，不承载业务算法。
3. `infra` 隔离外部依赖（Redis/DB/Storage/Provider SDK）。
4. 重数据落盘，数据库只存索引、状态、配置快照引用。
5. 跨模块通信必须走 `contracts`，禁止裸 `dict` 自由扩散。
6. WebSocket 负责命令传输，不保证“即时中断”；中断由 pipeline 安全点保障。

## 2. 总体组件与职责

### 2.1 组件

- `apps/web`（Next.js）
  - 项目列表、详情、设置。
  - 通过 HTTP 调 API，通过 WebSocket 收事件与发控制命令。
- `apps/api`（FastAPI）
  - HTTP API：项目、任务、配置、产物访问。
  - WebSocket 网关：订阅事件并下发实时更新；接收 pause/resume/cancel/delete。
- `workers`（Celery Worker Entry）
  - 任务消费、bootstrap、信号管理、日志初始化。
- `packages/pipeline`
  - stage 编排、状态推进、中断检查、安全点、重试与断点续跑。
- `packages/infra`
  - Redis、数据库、文件存储、第三方 ASR/OCR/VLM Provider 适配。
- `Redis`
  - Celery broker。
  - 事件通道（建议 Redis Streams；可先 Pub/Sub）。
- `SQLite`（后续可迁 Postgres）
  - Project/Job/Stage/Event/Settings 等元数据。
- `workspaces/`
  - 原视频、关键帧、中间件、最终产物。

### 2.2 信息流

1. 前端创建项目 -> API 写入 `Project/Job`（`queued`）。
2. API 触发 Celery pipeline。
3. Worker 每个 stage：
   - 写 workspace 中间件/产物。
   - 更新 DB stage/job 状态。
   - 发布标准化事件到 Redis。
4. API WebSocket 网关订阅 Redis 事件并转发前端。

## 3. 仓库目录（最终版）

```text
VideoSieve/
├── apps/
│   ├── api/                    # FastAPI: HTTP + WS gateway
│   └── web/                    # Next.js frontend
├── packages/
│   ├── contracts/              # 统一数据契约: Pydantic/JSON Schema
│   ├── core/                   # 状态机、错误码、事件模型、配置快照规范
│   ├── infra/                  # Redis/DB/Storage/Provider adapters
│   ├── pipeline/               # 编排、重试、断点续跑、中断控制
│   ├── ingest/                 # 下载/本地导入
│   ├── hotwords/               # 热词生成与管理
│   ├── asr/                    # ASR 适配
│   ├── keyframes/              # 抽帧策略
│   ├── ocr/                    # OCR 适配
│   ├── fusion/                 # 时间轴对齐
│   └── deliverables/           # 转译/摘要/图文输出
├── workers/
│   └── celery_app.py           # worker 入口 + task discovery + bootstrap
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── Dockerfile.web
│   └── docker-compose.yml
├── migrations/                 # Alembic（先保留骨架）
├── tests/
│   ├── unit/
│   └── integration/
├── workspaces/                 # 运行产物（gitignore）
├── docs/
└── pyproject.toml
```

## 4. 依赖白名单（强约束）

### 4.1 允许依赖

- `contracts`: 不依赖任何内部包。
- `core`: 仅依赖 `contracts`。
- `infra`: 可依赖 `core`、`contracts`，封装外部系统。
- `ingest/hotwords/asr/keyframes/ocr/fusion/deliverables`: 可依赖 `core`、`contracts`、受控 `infra` 接口。
- `pipeline`: 可依赖全部业务包 + `core/contracts/infra`。
- `apps/api`: 可依赖 `pipeline`、`core`、`contracts`、`infra`。
- `workers`: 可依赖 `pipeline`、`infra`（入口层，不放算法）。
- `apps/web`: 只依赖 API 契约（OpenAPI 生成类型或手写 DTO）。

### 4.2 禁止依赖

- `apps/*` 直接调用 Provider SDK（例如 ASR/OCR 云 SDK）。
- 业务包直接处理 Celery 控制细节（应由 `pipeline` 统一）。
- 模块间裸 `dict` 约定字段，不经 `contracts` 定义。
- 在 worker 入口散落状态机逻辑。

## 5. 运行时 workspace 规范

```text
workspaces/{project_id}/
  meta/
    meta.json
    config.snapshot.json
  media/
    source.mp4
    audio.wav
  hotwords/
    hotwords.json
    vocabulary_ref.json
  asr/
    transcript.jsonl
    transcript.words.jsonl
  frames/
    keyframes.jsonl
    images/*.jpg
    metrics/diff_curve.csv
  ocr/
    ocr.jsonl
  fusion/
    timeline.json
  outputs/
    clean_transcript.md
    illustrated_notes.md
    summary.json
    export.html
  logs/
    worker.log
```

### 5.1 生命周期与清理策略

- 删除项目时：`delete` 命令不直接删除。
  1) 先执行 `cancel`。
  2) 等待任务进入可清理态（`cancelled/failed/succeeded`）。
  3) 执行 workspace 清理与 DB 删除（可选软删）。
- 重跑策略：
  - 全量重跑。
  - 从某 stage 重跑（前序中间件复用）。
  - 基于 `config.snapshot.json` 判断可复用性。

## 6. 任务模型与状态机

### 6.1 核心对象

- `Project`: 视频项目（来源、元信息、配置引用）。
- `Job`: 一次运行实例（同一 Project 可多 Job）。
- `Stage`: `ingest/hotwords/asr/keyframes/ocr/fusion/deliverables/export`。

### 6.2 状态机

- Job: `queued -> running -> paused -> running -> succeeded|failed|cancelled`
- Stage: `pending -> running -> succeeded|failed|skipped`

### 6.3 进度计算

- 默认权重：
  - ingest 5%
  - hotwords 5%
  - asr 30%
  - keyframes 20%
  - ocr 15%
  - fusion 10%
  - deliverables 15%
- 总进度 = stage 权重 * stage 内子步骤百分比累计。

## 7. WebSocket 双向控制与事件协议

### 7.1 事件（worker -> frontend）

- `log`: `{project_id, job_id, ts, level, message}`
- `progress`: `{project_id, job_id, stage, pct, eta?}`
- `stage_changed`: `{project_id, job_id, from, to}`
- `artifact_ready`: `{project_id, job_id, artifact_type, path_or_url}`
- `error`: `{project_id, job_id, stage, code, message, hint?}`
- `control_ack`: `{project_id, job_id, command, accepted, reason?}`

### 7.2 控制命令（frontend -> backend -> worker）

- `pause`
- `resume`
- `cancel`
- `delete`

### 7.3 关键语义（必须实现）

1. **协作式暂停**：Celery 无原生暂停，worker 必须在安全点轮询控制 flag。
2. **软终止优先**：`cancel` 首选软终止，确保子进程与临时资源可清理。
3. **delete 两阶段**：先 cancel，再清理文件与 DB。
4. **幂等命令**：重复 `pause/cancel/delete` 不应导致异常状态漂移。

## 8. 模块职责摘要

- `ingest`: URL 下载、本地导入、音频标准化。
- `hotwords`: 规则抽取 + 模型精炼 + 用户编辑版本。
- `asr`: 在线优先，本地兜底，低置信度段可二次校正。
- `keyframes`: stable/ROI/scene/cluster 混合策略，输出可观测指标。
- `ocr`: OCR 主线，必要时 VLM 补充语义。
- `fusion`: 基于时间窗与章节边界组装 timeline，保留证据链。
- `deliverables`: 转译、摘要、图文交错输出与占位符回填。
- `pipeline`: 串联 stage、管理重试、断点续跑、控制命令生效点。

## 9. 可观测性与错误治理

### 9.1 最小观测集

- 项目级：总耗时、最终状态、失败 stage。
- stage 级：开始/结束时间、重试次数、失败码。
- 算法级：
  - ASR 低置信度比例、热词命中率。
  - keyframe 数量、重复率、diff 曲线。
  - OCR 低置信度比例。

### 9.2 错误规范

- 统一错误码：`PROVIDER_TIMEOUT`、`DOWNLOAD_FORBIDDEN`、`OCR_EMPTY` 等。
- 错误返回包含 `code/message/hint/retryable`。
- 所有错误必须可关联 `project_id + job_id + stage`。

## 10. 里程碑（执行建议）

- `M1`: ingest + asr + deliverables（转译/摘要）+ 并行 + 进度 + cancel。
- `M2`: keyframes（stable + 指标）+ 前端预览。
- `M3`: ocr + fusion + illustrated notes。
- `M4`: ROI/cluster、ASR 二次校正、策略自动兜底。

## 11. ADR 列表（建议在 docs/adr 维护）

1. ADR-001: apps/packages/workers/infra 边界。
2. ADR-002: 控制协议与协作式中断安全点。
3. ADR-003: workspace 生命周期（复用/清理/删除）。
4. ADR-004: Redis 事件总线选择（Pub/Sub 到 Streams 的迁移策略）。

---

本文件为当前重构阶段的唯一架构真相源（Single Source of Truth）。当实现与本文件冲突时，优先更新 ADR 与本文件，再改代码。
