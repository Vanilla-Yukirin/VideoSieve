有先后顺序，而且**很重要**。  
你这个阶段推荐“**分波次并行**”：

- **Wave 1（先做基础）**：W00, W01, W02
- **Wave 2（做核心模块）**：W03, W04, W05, W06
- **Wave 3（串起来）**：W07, W08
- **Wave 4（最后 UI）**：W09

原因：后面的 worker 依赖前面的契约和基础设施，不然会返工。

## 通用硬约束（所有 Worker 必须遵守）

1. 运行任何 Python 命令前先执行：`conda activate VideoSieve`
2. 包结构必须单层：`packages/<module>/*.py`，禁止 `packages/<module>/<module>/*`
3. 严格白名单改动；改到白名单外文件视为失败
4. 不提交 commit，不改 docs，不改其他 worker 负责目录
5. 输出 patch 写入本地文件：`workerXX_<topic>.patch`（不要在对话贴超长 diff）
6. 回包必须包含：
   - 变更摘要（<= 8 条）
   - 文件清单
   - patch 文件路径
   - 实测命令 + pass/fail 结果

---

## 推荐执行顺序（依赖关系）
1. W00 Bootstrap（先）
2. W01 Contracts/Core（先）
3. W02 Infra（先）
4. W03 Ingest+Hotwords
5. W04 ASR
6. W05 Keyframes+OCR
7. W06 Fusion+Deliverables
8. W07 Pipeline+Worker（依赖 3-6）
9. W08 API+WS（依赖 1/2/7）
10. W09 Web（依赖 8）

---

## 10 个 worker 初始 prompt（可直接复制）

### W00 - Bootstrap
```text
你是 Worker-00（Bootstrap）。
目标：初始化 Python monorepo 骨架与基础开发配置。
白名单路径：
- pyproject.toml
- apps/api/**
- packages/**
- workers/**
- tests/**
- .gitignore（仅必要补充）

要求：
- 建立目录骨架（apps/api, packages/contracts/core/infra/pipeline, workers, tests/unit）
- 配置 ruff/mypy/pytest（最小可运行）
- 提供一个 smoke test（例如 import contracts）

限制：
- 不实现业务逻辑
- 不改 docs 内容
- 不提交 commit

输出：
1) 变更摘要
2) unified diff patch
3) 可执行命令清单（含单测命令）
```

### W01 - Contracts/Core
```text
你是 Worker-01（Contracts/Core）。
目标：实现统一数据契约与核心状态/错误模型。
白名单路径：
- packages/contracts/**
- packages/core/**
- tests/unit/test_contracts_*.py
- tests/unit/test_state_machine_*.py

要求：
- Pydantic 定义：Project, Job, StageState, EventEnvelope, ControlCommand
- 状态机转移校验（含 invalid transition error）
- 统一错误码常量（INVALID_STATE_TRANSITION 等）
- 保持 project/job 语义严格区分

限制：
- 不调用 Redis/DB
- 不改 API/worker/web

输出：变更摘要 + unified diff + 测试命令
```

### W02 - Infra
```text
你是 Worker-02（Infra）。
目标：实现基础适配层（Redis/SQLite/Workspace）接口与最小实现。
白名单路径：
- packages/infra/**
- tests/unit/test_infra_*.py

要求：
- 抽象接口：EventBus, JobRepository, WorkspaceStore
- SQLite 最小 repository（project/job 查询更新）
- 文件系统 workspace helper（path builder）
- Redis event publisher/subscriber 抽象（先可 stub）

限制：
- 不写业务 stage 逻辑
- 不改 pipeline/api/web

输出：变更摘要 + unified diff + 测试命令
```

### W03 - Ingest + Hotwords
```text
你是 Worker-03（Ingest+Hotwords）。
目标：实现 ingest 与 hotwords 的可运行 MVP。
白名单路径：
- packages/ingest/**
- packages/hotwords/**
- tests/unit/test_ingest_*.py
- tests/unit/test_hotwords_*.py

要求：
- 先执行：conda activate VideoSieve
- ingest: 本地文件输入路径规范化 + meta 产出（先不强依赖下载器）
- hotwords: 基于标题/简介/tag 的规则抽取
- 必须复用 infra 的 workspace helper（禁止手写拼接路径）
- 输出写入 workspace 约定路径
- 产出结构符合 contracts（project/job 语义不混用）
- 目录结构必须单层：packages/ingest/*.py, packages/hotwords/*.py

限制：
- 不改 asr/keyframes/ocr/fusion
- 不接 API
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker03_ingest_hotwords.patch）
4) 测试命令与结果
```

### W04 - ASR
```text
你是 Worker-04（ASR）。
目标：实现 ASR 模块接口与最小 provider（mock/stub 可运行）。
白名单路径：
- packages/asr/**
- tests/unit/test_asr_*.py

要求：
- 先执行：conda activate VideoSieve
- 定义 ASRProvider 接口
- 实现 baseline provider（mock/stub）
- 支持 hotwords 与 language_hint 参数透传
- 产出 transcript.jsonl（含 start/end/text/lang/conf）
- 输出 JSONL 每行字段与 contracts 对齐
- 目录结构必须单层：packages/asr/*.py

限制：
- 不接真实外部云 SDK（先留 adapter 扩展点）
- 不改 pipeline/api
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker04_asr.patch）
4) 测试命令与结果
```

### W05 - Keyframes + OCR
```text
你是 Worker-05（Keyframes+OCR）。
目标：实现 keyframes 与 ocr baseline。
白名单路径：
- packages/keyframes/**
- packages/ocr/**
- tests/unit/test_keyframes_*.py
- tests/unit/test_ocr_*.py

要求：
- 先执行：conda activate VideoSieve
- keyframes: 先实现可运行 stable sampling baseline
- ocr: 先实现 OCR adapter 接口 + mock provider
- 输出 keyframes.jsonl / ocr.jsonl 路径正确
- reason 字段与 contracts 对齐
- 目录结构必须单层：packages/keyframes/*.py, packages/ocr/*.py

限制：
- 不做复杂算法优化（先跑通）
- 不改 fusion/deliverables
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker05_keyframes_ocr.patch）
4) 测试命令与结果
```

### W06 - Fusion + Deliverables
```text
你是 Worker-06（Fusion+Deliverables）。
目标：实现 timeline 组装与文档产出。
白名单路径：
- packages/fusion/**
- packages/deliverables/**
- tests/unit/test_fusion_*.py
- tests/unit/test_deliverables_*.py

要求：
- 先执行：conda activate VideoSieve
- fusion: transcript/keyframe/ocr -> timeline.json
- deliverables: clean_transcript.md, illustrated_notes.md, summary.json
- 图文占位符策略：[[frame:...]]
- 输出路径遵循 workspace 规范
- 依赖输入以 W03/W04/W05 已落地契约为准，不自行发明新字段
- 目录结构必须单层：packages/fusion/*.py, packages/deliverables/*.py

限制：
- 不改 pipeline/api/web
- 不扩展到 UI 样式层
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker06_fusion_deliverables.patch）
4) 测试命令与结果
```

### W07 - Pipeline + Worker
```text
你是 Worker-07（Pipeline+Worker）。
目标：串联 stage 编排，支持 pause/resume/cancel 的协作式语义。
白名单路径：
- packages/pipeline/**
- workers/**
- tests/unit/test_pipeline_*.py

要求：
- 先执行：conda activate VideoSieve
- stage orchestration（ingest->...->deliverables）
- safety points（外部调用前后/长循环周期检查）
- checkpoint 与 rerun-from-stage 基础能力
- 事件发布与 control_ack 对齐 contracts
- 控制语义遵循 state-machine 矩阵（invalid transition 返回明确错误码）
- delete 采用两阶段（cancel -> terminal -> cleanup）
- 目录结构必须单层：packages/pipeline/*.py, workers/*.py

限制：
- 不改 API routes/web
- 不引入与 docs 冲突的新状态机
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker07_pipeline_worker.patch）
4) 测试命令与结果
```

### W08 - API + WebSocket
```text
你是 Worker-08（API+WS）。
目标：实现 job 维度控制面 API 与 WS 网关。
白名单路径：
- apps/api/**
- tests/unit/test_api_*.py

要求：
- 先执行：conda activate VideoSieve
- REST: project/job 创建查询、job snapshot、artifact list
- WS 主通道：/ws/jobs/{job_id}
- 控制命令：pause/resume/cancel/delete（job scoped）
- WS 断连时语义与 snapshot 规则一致
- snapshot 至少包含：job status、current stage、progress、latest logs、artifact list
- event bus 为 best-effort 时，UI 仍可通过 snapshot 收敛状态
- 目录结构必须单层：apps/api/*.py（可按包内模块平铺）

限制：
- 不改 web 前端
- 不重写 pipeline 逻辑
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker08_api_ws.patch）
4) 测试命令与结果
```

### W09 - Web
```text
你是 Worker-09（Web）。
目标：实现最小但可用的前端控制台（项目列表 + project详情 + job详情 + 控制面板）。
白名单路径：
- apps/web/**
- tests/unit/test_web_*.ts (或对应框架)
- tests/integration/test_web_flow_*.ts (可选)

要求：
- 若需要 Node 依赖，先确认包管理器与 lockfile；无 lockfile 时默认 npm。
- 页面进入先拉 HTTP snapshot
- 再订阅 job WS 增量事件
- 控制按钮作用于明确 job_id
- 显示日志、进度、产物列表
- 信息架构最少包含：
  - Projects 列表（project 级摘要）
  - Project 详情（历史 jobs + 当前选中 job）
  - Job 详情（stage/progress/logs/artifacts + controls）
- 交互语义：
  - WS 断开时自动回退 snapshot 轮询
  - command 发送后必须有 pending/ack 状态反馈（与 control_ack 对齐）
  - UI 不得把 project 级操作误发到错误 job
- 视觉与样式（必须明确，不要通用脚手架风格）：
  - 使用 CSS 变量定义主题色、语义色、间距与圆角
  - 字体不要用默认系统/Inter/Roboto/Arial 直出，需给出明确字体策略与回退链
  - 卡片/时间线/日志区要有层级对比，避免纯白平面
  - 提供轻量动效（加载入场、列表渐进）但不影响可读性
  - 同时适配桌面与移动端（至少 360px 宽度可用）
- 目录结构保持清晰：页面、组件、hooks、api client 分层，不把 WS 协议细节散落到 UI 组件

限制：
- 不改后端 API 协议
- 不引入 docs 未定义的命令语义
- 不改 docs
- 不 commit

输出：
1) 变更摘要（<=8条）
2) 文件清单
3) patch 文件路径（worker09_web.patch）
4) 测试命令与结果

验收参考：`docs/web-review-checklist.md`
```
