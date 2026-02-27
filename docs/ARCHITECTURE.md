# VideoSieve 架构规划书

> 本文件是重构阶段的架构基线（Single Source of Truth）。当实现与本文件冲突时，优先更新 ADR 与本文件，再改代码。

> 文档导航：详见 `docs/README.md`，跨模块契约集中在 `docs/10_system/`，模块细节集中在 `docs/20_modules/`。

下面是一份“规划书级别”的完整方案（偏产品/平台视角），覆盖：总体目标、组件与信息流、目录结构、任务状态机、WebSocket 双向控制、以及每个单元的任务与多分支选型。默认技术选型：**FastAPI + Redis（Docker 部署）+ Celery + WebSocket + Next.js + SQLite**；后续可平滑迁移到 Postgres。

------

# 0. 项目目标与边界

## 0.1 目标

给定 **B 站链接或本地视频**，自动生成一套可复用的“知识资产”：

- **转译稿**：去口语/重复/语气词、断句标点、结构化段落（保真）
- **图文交错笔记**：关键帧（如 PPT/板书/关键画面）与对应字幕段落对齐，支持引用回填
- **摘要**：100–500 字新闻稿式摘要 + 标题（原/重命名）
- **全流程可控**：多项目并行、实时日志、进度条、暂停/继续/终止/删除

## 0.2 非目标（先不做或可选）

- 多租户/复杂权限（先单用户或简单 token）
- 复杂检索（向量检索/全文检索）可作为后续扩展
- 追求“所有视频类型都完美抽帧”：先做可解释、可调参、可观测的策略

## 0.3 架构原则（必须执行）

1. `apps/` 负责运行与部署边界，`packages/` 负责可复用逻辑。
2. `workers/` 只负责执行入口与启动编排，不承载业务算法。
3. `packages/infra/` 隔离外部依赖（Redis/DB/Storage/Provider SDK），业务包不直接调用外部 SDK。
4. 重数据落盘，数据库只存索引、状态、配置快照引用。
5. 跨模块通信必须走 `packages/contracts/`，禁止裸 `dict` 自由扩散。
6. WebSocket 负责命令传输，不保证“即时中断”；中断由 pipeline 安全点保障。

------

# 1. 总体架构总览（组件与职责）

## 1.1 组件清单

**可部署单元（apps）**

1. **Next.js Web 前端**（`apps/web`）

- 项目卡片列表、详情页（日志/进度/产物预览）、设置面板
- 通过 HTTP 调 API，通过 WebSocket 收/发控制与事件

2. **FastAPI 后端（API + WebSocket 网关）**（`apps/api`）

- HTTP API：创建项目/任务、读取状态、下载产物、管理设置
- WebSocket：实时推送（日志、进度、阶段切换、产物就绪），接收控制指令（暂停/继续/终止/删除）

3. **Celery Workers（执行引擎）**（`workers/`，入口层；业务逻辑在 `packages/` 中）

- 实际跑下载、转写、抽帧、OCR、融合、生成产物
- 默认单 agent 统一执行（需要时可扩展并行 worker）

**基础设施**

4. **Redis**

- Celery broker（任务队列）
- 事件通道（建议 Redis Streams；可先 Pub/Sub）：worker → FastAPI → WebSocket → 前端
- 可选：短期缓存、分布式锁（防重复跑）

5. **SQLite**（后续可迁移 Postgres）

- 项目元数据、任务状态、配置版本、产物索引、错误记录
- 视频/大文件不放数据库，落盘到 workspace

6. **Workspace 文件系统（本地磁盘/挂载盘/对象存储可扩展）**

- 存原始媒体、关键帧、JSON 中间件、最终 Markdown/HTML

------

# 2. 组件之间如何传递信息（信息流/事件流）

## 2.1 数据流（“产物/中间件”落盘）

**核心原则：所有重数据落盘，数据库只存索引与状态。**

- Next.js → FastAPI：创建项目（URL/本地上传引用/参数）
- FastAPI → SQLite：写入 project/job 记录（初始 queued）
- FastAPI → Celery（通过 Redis）：发起任务链（pipeline stages）
- Worker 每完成一个 stage：
    - 写 workspace 中间件文件（JSONL/JSON/图片）
    - 更新 SQLite（stage 状态、进度、错误）
    - 向 Redis 发布事件（日志行、进度、产物链接）
- FastAPI WebSocket 网关：
    - 订阅 Redis 事件
    - 转发给前端指定 project 的 WebSocket 连接

## 2.2 事件流（实时日志/进度/控制）

### 事件（worker → 前端）

建议统一成一套事件模型（便于 UI 卡片式渲染）：

- `log`：`{project_id, job_id, ts, level, message}`
- `progress`：`{project_id, job_id, stage, pct, eta?}`
- `stage_changed`：`{project_id, job_id, from, to}`
- `artifact_ready`：`{project_id, job_id, artifact_type, path_or_url}`
- `error`：`{project_id, job_id, stage, code, message, hint?}`
- `control_ack`：`{project_id, job_id, command, accepted, reason?}`

### 控制指令（前端 → worker）

你想要暂停/终止/删除，建议做成“控制命令”：

- `pause`：worker 在安全点（stage 边界或子步骤边界）检查并停
- `resume`：解除暂停，继续执行
- `cancel`：请求终止（软终止为主），并标记 job cancelled
- `delete`：删除项目（先 cancel，再清理 workspace 与 DB 记录）

> 注意：WebSocket 能做双向控制，但“暂停/继续”能否真正即时生效，取决于你在 worker 内部是否设计了**可中断点**（例如每 N 秒检查一次 cancel flag）。

### 控制语义（必须实现）

1. **协作式暂停**：Celery 无原生暂停，worker 必须在安全点（stage 边界或子步骤边界）轮询控制 flag。
2. **软终止优先**：`cancel` 首选软终止，确保子进程与临时资源可清理；仅极端情况下使用 `revoke(terminate=True)`。
3. **delete 两阶段**：先 cancel 并等待任务进入终态，再清理文件与 DB 记录。
4. **幂等命令**：重复 `pause/cancel/delete` 不应导致异常状态漂移或抛错。

------

# 3. 项目目录/文件夹规划

## 3.1 运行时 workspace 目录（每个项目一个工作目录）

> 说明：本节仅作总览，`docs/10_system/workspace-layout.md` 是唯一权威（canonical）定义；目录变更以该文档为准。

```
workspaces/{project_id}/
  meta/
    meta.json                 # 标题、简介、tag、来源、语言提示、时长等
    config.snapshot.json      # 本次运行使用的配置快照（可复现）
  media/
    source.mp4                # 原始或下载后文件
    audio.wav                 # 统一规格音频（16k/mono 等）
  hotwords/
    hotwords.json             # 自动+人工编辑后的热词
    vocabulary_ref.json       # 在线ASR词表ID等引用信息（如有）
  asr/
    transcript.jsonl          # 分段（必须有start/end）
    transcript.words.jsonl    # 可选：词级时间戳
  frames/
    keyframes.jsonl           # 关键帧索引（ts/path/hash/score/reason）
    images/
      slide_000001.jpg
      ...
    metrics/
      diff_curve.csv          # 可观测曲线（用于阈值调参）
  ocr/
    ocr.jsonl                 # 每张关键帧的文字块/bbox/conf
  fusion/
    timeline.json             # 对齐后的“交错序列”（下游唯一输入）
  outputs/
    clean_transcript.md
    illustrated_notes.md
    summary.json              # 100-500字摘要 + 标题
    export.html               # 可选导出
  logs/
    worker.log                # 可选：完整日志
```

## 3.2 代码仓库目录（单仓库，apps/packages/workers 分层）

```text
VideoSieve/
├── apps/
│   ├── api/                    # FastAPI: HTTP + WS gateway
│   └── web/                    # Next.js frontend
├── packages/
│   ├── contracts/              # 统一数据契约: Pydantic/JSON Schema
│   ├── core/                   # 状态机、错误码、事件模型、配置快照规范
│   ├── infra/                  # Redis/DB/Storage/Provider adapters（隔离外部依赖）
│   ├── pipeline/               # 编排、重试、断点续跑、中断控制（替代原 orchestrator）
│   ├── ingest/                 # yt-dlp、本地导入
│   ├── hotwords/               # 热词生成/管理
│   ├── asr/                    # ASR 适配层（在线/本地/LLM 兜底）
│   ├── keyframes/              # 抽帧策略（stable/scene/cluster）
│   ├── ocr/                    # OCR 适配层
│   ├── fusion/                 # 对齐与 chunk 组装
│   └── deliverables/           # 转译/翻译/摘要/图文输出
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
├── docs/                       # 规划书/调研/实验对比
└── pyproject.toml
```

> 说明：`api_server` / `web_ui` 从 packages 移入 `apps/`，强调可部署单元边界；原 `orchestrator` 拆分为 `core` + `pipeline`。

## 3.3 Workspace 生命周期与清理策略

- 删除项目时，`delete` 命令不直接删除：
  1. 先执行 `cancel`。
  2. 等待任务进入可清理态（`cancelled/failed/succeeded`）。
  3. 执行 workspace 清理与 DB 删除（可选软删）。
- 重跑策略：
  - 全量重跑。
  - 从某个 stage 重跑（前序中间件复用）。
  - 基于 `config.snapshot.json` 判断可复用性。

## 3.4 依赖白名单（强约束）

### 允许依赖

- `contracts`：不依赖任何内部包。
- `core`：仅依赖 `contracts`。
- `infra`：可依赖 `core`、`contracts`，封装外部系统。
- `ingest/hotwords/asr/keyframes/ocr/fusion/deliverables`：可依赖 `core`、`contracts`、受控 `infra` 接口。
- `pipeline`：可依赖全部业务包 + `core/contracts/infra`。
- `apps/api`：可依赖 `pipeline`、`core`、`contracts`、`infra`。
- `workers`：可依赖 `pipeline`、`infra`（入口层，不放算法）。
- `apps/web`：只依赖 API 契约（OpenAPI 生成类型或手写 DTO）。

### 禁止依赖

- `apps/*` 直接调用 Provider SDK（例如 ASR/OCR 云 SDK）。
- 业务包直接处理 Celery 控制细节（应由 `pipeline` 统一）。
- 模块间裸 `dict` 约定字段，不经 `contracts` 定义。
- 在 worker 入口散落状态机逻辑。

------

# 4. 任务模型与状态机（支撑“多项目并行 + 实时进度”）

## 4.1 核心对象

- `Project`：一个视频项目（URL 或本地文件）+ 配置快照引用
- `Job`：一次运行（同一个 project 可多次 job，便于调参重跑）
- `Stage`：ingest/asr/keyframes/ocr/fusion/deliverables/export

## 4.2 状态机（建议）

- project/job 状态：`queued → running → (paused) → succeeded/failed/cancelled`
- stage 状态：`pending → running → succeeded/failed/skipped`

> 进度计算：建议以 stage 权重（例如 ingest 5%、asr 35%、keyframes 20%、ocr 15%、fusion 10%、deliverables 15%）+ stage 内子步骤百分比综合。

------

# 5. 模块拆解：每个单元的任务、目标、分支选项与实现路径（设计级）

下面每个单元都按同一模板写：**目标 / 输入输出 / 可选方案（分支）/ 关键参数与可观测性 / 风险与兜底**。

------

## 5.1 单元 A：Ingest（B站链接/本地导入）

### 目标

把“来源”统一成标准化媒体与 meta，为后续流程提供稳定输入。

### 输入/输出

- 输入：B站 URL 或本地视频 +（可选）标题/简介
- 输出：`media/source.mp4`、`media/audio.wav`、`meta/meta.json`

### 方案分支

**A1：yt-dlp Python 集成（主线）**

- 分支：
    - A1-1 不登录：公开视频
    - A1-2 登录：cookiefile/cookies-from-browser（你已接受 Docker/环境差异，属于部署问题）
    - A1-3 清晰度策略：
        - 低清优先（节省带宽与存储，OCR可能足够）
        - 高清存档（后处理用低清，存档用高清）
        - 自适应升级（如果 OCR 可读性低→二次下载更高清）

**A2：本地上传**

- 分支：
    - 只上传视频
    - 上传视频+补充 meta（标题、简介、语言提示）

### 可观测性

- 下载速度、失败原因（地区/权限/限速）、最终分辨率与码率
- 音频提取规格（采样率、声道）

### 风险/兜底

- 下载失败：重试、切换格式、提示需要登录 cookie
- 音频异常：重新抽取或降噪（后续再加）

------

## 5.2 单元 B：Hotwords（热词生成与管理）

### 目标

为 ASR 提供“可控偏置”，提升专有名词/术语命中率；并且可人工编辑与版本化。

### 输入/输出

- 输入：`meta.json`（标题/简介/tag）
- 输出：`hotwords/hotwords.json`（含权重/语言/别名），在线ASR还会有 `vocabulary_ref.json`

### 方案分支

**B1：规则抽取（稳定、成本低）**

- 从标题/简介/tag 抽关键短语
- 中英混杂：分别做候选集
- 去除停用词、过短词、过泛词

**B2：小模型/LLM 精炼（提高质量）**

- 做候选合并、同义扩展、权重建议
- 典型输出结构：`[{text, lang, weight, aliases[]}]`

**B3：用户编辑（UI 必须有）**

- 增删改、权重拖动、保存版本（v1/v2）

### 可观测性

- 热词数量、覆盖率（ASR 结果中热词命中次数）、错误召回（误命中）

### 风险/兜底

- 热词过多导致噪声：限制数量上限，权重分层（核心/次要/低权）

------

## 5.3 单元 C：ASR（转写）

### 目标

得到带时间戳的高质量字幕段落（必要时词级），并为后续对齐提供可靠的时间轴。

### 输入/输出

- 输入：`audio.wav` + `hotwords.json` + language hint
- 输出：`asr/transcript.jsonl`（必须 start/end/text/lang/conf），可选 `words.jsonl`

### 方案分支（按你的约束：CPU 省算力 + 热词 + 可扩展）

**C1：在线 ASR（推荐作为默认主线）**

- 优点：热词/领域词表更可控；不占你服务器 CPU；整体吞吐稳定
- 分支：
    - C1-1 流式实时（更适合“边跑边看日志/进度”）
    - C1-2 离线批处理（更简单，适合长音频）
    - C1-3 词表管理（vocabulary_id 复用、按项目生成）

**C2：本地 CPU ASR（可选备用）**

- 适用：离线需求强、对隐私敏感
- 风险：速度/质量不可保证；热词能力可能弱于在线引擎

**C3：LLM/多模态模型做 ASR（兜底/二次校正）**

- 用途：对“在线ASR明显错误的片段”做局部重转写；或者对外语/噪声段修复
- 成本：可控但需要策略（只对低置信度段触发）

### 可观测性

- 段落置信度分布、低置信度比例
- 热词命中率
- 时长对齐误差（总时长/末尾漂移）

### 风险/兜底

- 在线调用失败：重试与断点续跑
- 质量不足：对低置信度段触发“二次转写”（C3）

------

## 5.4 单元 D：Keyframes（关键帧/幻灯片抽取）

### 目标

从长视频中抽取“信息密度高、适合 OCR/笔记”的少量代表帧；避免 PPT 动画中间态；支持讲师画面/3b1b 动画等复杂场景。

### 输入/输出

- 输入：`source.mp4`
- 输出：`frames/keyframes.jsonl` + `frames/images/*.jpg` + `frames/metrics/diff_curve.csv`

### 方案分支（你要求“手写算法 + 可调阈值 + 可观测”）

**D1：Stable-frame（稳定段检测，PPT/课件主线）**

- 核心：计算相邻帧差异（像素差/SSIM/感知哈希距离），寻找连续低变化区间
- 截帧点：稳定区间中位帧或末端帧
- 关键参数：
    - 采样 fps（2–5fps 起步）
    - 稳定阈值（diff/hash distance）
    - 连续稳定帧数 N（过滤动画）
    - 去重最小间隔（避免同页重复）

**D2：ROI 稳定检测（讲课视频主线升级）**

- 只在“屏幕/投影区域”计算差异，避免讲师走动导致误判
- ROI 获取策略：
    - 规则/统计法（时间方差找静态区域）
    - 边缘/矩形检测（偏传统CV）
- 输出依旧走 D1 的稳定段逻辑

**D3：Scene-cut（剪辑视频补充策略）**

- 用于镜头切换明显的内容；对 PPT 不敏感
- 常作为 D1 的补充，而不是主力

**D4：聚类代表帧（3b1b 等持续动画）**

- 不能依赖“稳定段”，改用“相似帧聚类”
- 每簇选中心帧，控制总帧数上限
- 兜底：固定间隔采样（例如每 10–15 秒）

**D5：混合策略（建议最终默认）**
优先级建议：

1. ROI Stable（如果能得到 ROI）
2. 全帧 Stable
3. Scene-cut 补充
4. 若产出过少 → 聚类/定时采样兜底

### 可观测性（这是你调参的核心）

- `diff_curve.csv`：timestamp vs diff/hash_dist
- keyframe 数量、平均间隔、重复率
- 每张 keyframe 的 `reason`（stable/scene/cluster/sample）

### 风险/兜底

- 动画多 → 稳定段太少：自动降门槛或触发兜底采样
- 讲师遮挡 → ROI 失败：回退到全帧策略

------

## 5.5 单元 E：VLM 画面理解（关键帧描述+文字提取）

### 目标

对每张关键帧发起一次 VLM 请求，直接返回自由文本结果，用于“画面描述 + 可见文字提取”。

### 输入/输出

- 输入：`frames/images/*.jpg`
- 输出：`ocr/ocr.jsonl`（`summary_text` + `blocks` + `provider` + `lang` + `conf`）

### 方案分支

**E1：VLM-only（默认）**

- 单次请求同时完成“描述画面 + 提取文字”
- 不强制模型返回 JSON，直接保留原始自由文本

### 可观测性

- 每帧 VLM 响应耗时、失败率
- 非空 `summary_text` 覆盖率

### 风险/兜底

- 模型网络失败或超时：写入离线占位文本，保持流水线不中断

------

## 5.6 单元 F：Fusion（时间对齐与交错序列组装）

### 目标

把 ASR、关键帧、OCR 统一成一个“时间轴 timeline”，下游只读 timeline 即可生成任何产物。

### 输入/输出

- 输入：`transcript.jsonl`、`keyframes.jsonl`、`ocr.jsonl`
- 输出：`fusion/timeline.json`

### 方案分支

**F1：基于时间窗口的对齐（默认）**

- 对每个关键帧 `t`，取附近 `[t-Δ, t+Δ]` 的字幕段作为上下文
- Δ 可配置（例如 10–30 秒）

**F2：以关键帧作为章节边界**

- 当关键帧出现时切分 chunk（更适合 PPT 换页形成的自然段落）

**F3：证据链（建议纳入 timeline）**

- 每个 chunk 显式记录引用源：
    - transcript segment ids
    - frame ids
    - OCR block ids
        这样后续输出能回溯证据，便于纠错与再生成。

### 可观测性

- 每个 chunk 包含的字幕时长、关键帧数量、OCR 文本长度
- 对齐覆盖率（有帧但无字幕/有字幕但无帧的比例）

------

## 5.7 单元 G：Deliverables（转译/翻译/摘要/图文交错输出）

### 目标

把 timeline 转成用户可消费的最终文档，并支持可回填的图片引用。

### 输入/输出

- 输入：`timeline.json`
- 输出：
    - `clean_transcript.md`
    - `illustrated_notes.md`
    - `summary.json`
    - （可选）`export.html`

### 方案分支

**G1：转译（同语言清洗，必须有）**

- 去口癖、重复、断句、补标点
- 保持原意不扩写（扩写另做“讲义版”）

**G2：翻译（可选）**

- 推荐顺序：先转译→再翻译→（可选）目标语言再润色
- 中英混讲：按段落语言分别处理

**G3：摘要（必须有）**

- 100–500 字 + 标题策略：
    - 原标题
    - 重命名标题
    - 或 “原标题 + 重命名标题”并存

**G4：图文交错（你的核心体验之一）**

- 模型输出只允许使用占位符引用：
    - `[[frame:slide_000123]]`
- 后处理器把占位符替换为真实图片链接/相对路径
- 这样你能保证一致性与可修复性

### 可观测性

- 文档长度、段落数量、引用帧数量
- 可读性检查：是否存在未解析占位符、是否丢失 chunk

------

## 5.8 单元 H：Orchestrator（编排、并发、断点续跑、取消）

### 目标

把所有模块串起来，并提供：

- 多项目并行（Celery worker 并发）
- 断点续跑（stage 成功则跳过）
- 暂停/继续/取消（控制面板）
- 失败后重试与错误归因

### 方案分支

**H1：固定 pipeline（线性 stage 链）**

- ingest → hotwords → asr → keyframes → ocr → fusion → deliverables
- 简单可靠，适合 MVP

**H2：条件分支 pipeline（推荐中期）**

- 根据视频类型/抽帧产出情况动态选择策略：
    - 帧太少 → 触发兜底采样/聚类
    - OCR 质量差 → 触发更高清下载
    - ASR 置信度低 → 触发二次转写

**H3：可重跑粒度**

- 全量重跑
- 从某个 stage 重跑（保留前序中间件）

### 可观测性

- stage 用时、失败率、重试次数
- 任务队列长度、worker 利用率

------

# 6. 前端页面与交互规划（你要的 4 点对应到 UI）

## 6.1 页面结构

1. **Projects 列表页（卡片式）**

- 卡片字段：标题、来源、状态、当前 stage、进度条、最近日志摘要
- 操作：打开详情 / 暂停 / 继续 / 取消 / 删除 / 重跑（可选）

2. **Project 详情页**

- 实时日志窗口（WebSocket）
- 进度与阶段时间线
- 关键帧预览（缩略图网格）
- 产物下载（Markdown/HTML/JSON）
- 参数快照查看（本次运行配置）

3. **Settings 设置页**

- API key、供应商选择、默认并发、默认抽帧策略阈值、存储策略
- 配置版本：保存/回滚
- “测试连接/健康检查”（可选）

## 6.2 WebSocket 双向控制与能力边界

- 可以做：暂停/继续/取消/删除、实时日志与进度
- 需要设计：控制命令的生效点（安全点轮询），以及“取消后的清理策略”（先停任务，再删 workspace）

------

# 7. 里程碑建议（避免一次性被复杂度压垮）

你说要“逐个击破”，建议按平台能力优先级推进：

**M1（最小闭环 + 平台骨架）**

- ingest + 在线 ASR + deliverables（转译+摘要）
- 多项目并行、实时日志、进度条、取消

**M2（加入关键帧：可观测调参）**

- stable-frame（先全帧）+ diff 曲线
- UI 增加关键帧预览

**M3（VLM 画面理解 + 图文交错）**

- VLM-only frame summary + timeline + illustrated_notes

**M4（复杂视频适配）**

- ROI stable、聚类代表帧、ASR 二次校正策略

------

# 8. 你要求的“选项分支很多”——报告写法建议

在最终研究报告里，每个模块用统一表格/小节写：

- 需求点（性能/质量/成本/可解释）
- 方案 A/B/C（你上面这些分支）
- 取舍维度（CPU、网络、成本、工程复杂度、可观测性）
- 推荐默认路径 + 触发兜底条件（if/else 规则）

这样读者会觉得“全面但不散”。

------

## 8.1 可观测性与错误治理（工程必备）

### 最小观测集

- 项目级：总耗时、最终状态、失败 stage。
- stage 级：开始/结束时间、重试次数、失败码。
- 算法级：
  - ASR 低置信度比例、热词命中率。
  - keyframe 数量、重复率、diff 曲线。
  - OCR 低置信度比例。

### 错误规范

- 统一错误码：`PROVIDER_TIMEOUT`、`DOWNLOAD_FORBIDDEN`、`OCR_EMPTY` 等。
- 错误返回包含 `code/message/hint/retryable`。
- 所有错误必须可关联 `project_id + job_id + stage`。

## 8.2 ADR 列表（建议在 `docs/adr/` 维护）

1. ADR-001：apps/packages/workers/infra 边界划分。
2. ADR-002：控制协议与协作式中断安全点。
3. ADR-003：workspace 生命周期（复用/清理/删除）。
4. ADR-004：Redis 事件总线选择（Pub/Sub 到 Streams 的迁移策略）。

------

如果你希望下一步更具体一点（仍然不谈代码实现），我可以把这份规划书再补两块“更像正式方案”的内容：

1. **统一的数据契约（timeline.json / transcript.jsonl / keyframes.jsonl 的字段定义与示例）**
2. **配置系统（settings）分层：全局默认、项目覆盖、job 快照、版本回滚策略**

------

本文件为当前重构阶段的架构真相源（Single Source of Truth）。实现方案发生变更时，先更新 ADR 与本文件，再改代码。
