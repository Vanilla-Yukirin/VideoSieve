# 产物实时可见与可下载长期扩展计划

本文档用于规划 VideoSieve 后续的「产物实时更新、可下载、可播放、可扩展」能力。

## 1. 背景与当前现状

当前行为：

- `GET /jobs/{job_id}/artifacts` 只能返回某一时刻的清单快照。
- Job 详情页在 WS 连接稳定时会停止轮询，前端不一定能及时拿到最新 artifacts。
- 已实现 `source.mp4` 单独播放接口（`GET /jobs/{job_id}/source-video`），但「何时出现播放器」仍依赖前端状态刷新时机。

结论：

- 文件已生成 != 前端实时可见。
- 需要标准化“产物事件”与“快照收敛”机制。

---

## 2. 目标

### 2.1 功能目标

1. 产物生成后，前端无需手动刷新即可出现。
2. 右侧产物列表中的可下载项逐步可用（先视频，后文本/json等）。
3. 不同类型产物可扩展（video/json/md/image/zip等）。

### 2.2 架构目标

1. WS 负责增量事件，HTTP Snapshot 负责最终收敛（source-of-truth）。
2. 事件契约稳定、可版本化、可回放（至少在日志层面可追踪）。
3. 前后端对“artifact 生命周期”统一建模。

---

## 3. 目标架构（推荐）

### 3.1 双通道模型

- **WS 增量通道**：推送 `artifact_ready` / `artifact_removed` / `snapshot_hint`。
- **HTTP 快照通道**：`GET /jobs/{job_id}/snapshot` 返回最终一致状态。

### 3.2 事件优先级

1. 前端收到 `artifact_ready`：先做本地增量更新。
2. 收到关键阶段事件（如 `deliverables` 完成、job succeeded）：强制拉一次 snapshot 校正。
3. WS 断线恢复后：立即拉 snapshot，消除漏事件风险。

---

## 4. 契约设计（建议）

### 4.1 WS 事件新增

新增事件类型：

- `artifact_ready`
  - payload:
    - `path: str`
    - `size_bytes: int`
    - `media_type: str | null`（可选，后续用于前端预览策略）
    - `created_at: iso8601`
- `artifact_removed`（可选，后续清理/重跑时使用）
  - payload:
    - `path: str`
    - `removed_at: iso8601`
- `snapshot_hint`
  - payload:
    - `reason: str`（如 `stage_deliverables_done`）

### 4.2 HTTP 快照增强

`JobSnapshot.artifacts[]` 逐步扩展字段（向后兼容）：

- `path`
- `size_bytes`
- `kind`（`video`/`jsonl`/`json`/`markdown`/`other`）
- `download_url`（推荐由后端生成，前端不拼接）
- `preview_url`（可选）

> 说明：现阶段可以先保留 `path/size_bytes`，第二阶段再加 `download_url`。

---

## 5. 分阶段实施计划

## 阶段 A（短期，低风险，快速收益）

目标：先解决“产物不自动出现”。

改动：

1. 前端 `useJobRealtime`：
   - 在 `event_type=stage_changed` 且进入 `deliverables` 后触发一次 `getJobSnapshot`。
   - 在 `event_type=progress` 且 `pct >= 100` 时触发一次 `getJobSnapshot`（加去抖/去重）。
2. 前端 reducer：保留现有逻辑即可。
3. 不改后端契约。

验收：

- 任务完成后无需刷新，`source.mp4` 播放区自动出现。

## 阶段 B（中期，正式事件化）

目标：建立 artifacts 增量事件。

后端改动：

1. 在产物写入点统一发 `artifact_ready`。
2. `ApiControlPlane._consume_event` 支持记录 artifact 增量状态（或触发 snapshot hint）。
3. `ws_gateway` 保持透传事件。

前端改动：

1. reducer 增加 `artifact_ready` 分支，增量更新 `state.artifacts`。
2. 收到 `snapshot_hint` 时拉一次 snapshot 收敛。

验收：

- 关键产物生成后 1~2 秒内出现在 UI。
- 刷新前后列表一致。

## 阶段 C（长期，下载与预览统一）

目标：统一 download/preview 策略。

后端改动：

1. 提供通用 artifact 下载路由（带路径安全校验）。
2. snapshot/artifacts 返回 `download_url`。
3. 对敏感或不稳定产物支持短时签名 URL（可选）。

前端改动：

1. 不再拼接下载路径，只使用 `download_url`。
2. 基于 `kind/media_type` 决定预览组件（video/json/md）。

验收：

- 可下载率、可预览率可度量。

---

## 6. 文件级改动清单（未来实施时参考）

后端：

- `apps/api/models.py`（ArtifactItem 扩展字段）
- `apps/api/service.py`（消费 artifact 事件 / snapshot 组装）
- `apps/api/ws_gateway.py`（事件透传保持）
- `apps/api/main.py`（通用下载路由，后续）
- `packages/*` 产物写入点（发送 `artifact_ready`）

前端：

- `apps/web/lib/state/jobReducer.ts`（artifact_ready/snapshot_hint 分支）
- `apps/web/lib/hooks/useJobRealtime.ts`（关键事件触发 snapshot 收敛）
- `apps/web/app/jobs/[id]/page.tsx`（下载/预览策略）
- `apps/web/lib/api/types.ts`（ArtifactItem 扩展）

测试：

- `tests/unit/test_api_runtime_entry.py`
- `tests/unit/test_api_ws_gateway.py`
- `tests/unit/test_web_reducer.ts`
- `tests/unit/test_web_ingest.ts`（必要时）

---

## 7. 风险与规避

1. **漏事件**：仅靠 WS 增量可能漏包。
   - 规避：关键节点强制 snapshot 收敛。
2. **重复事件**：artifact_ready 重复触发。
   - 规避：前端按 `path` 去重合并。
3. **路径安全**：下载接口路径穿越风险。
   - 规避：仅允许 `workspace.path(project_id, *parts)` 安全构造。
4. **扩展成本**：前端拼接 URL 难维护。
   - 规避：逐步过渡到后端返回 `download_url`。

---

## 8. 决策建议

建议按 A -> B -> C 推进，不建议一次性大改。

- A：一周内可完成（小改，收益立刻可见）
- B：在后端产物流程稳定后开展
- C：结合前端体验升级统一做

该路线兼顾当前 demo 节奏与长期可拓展性。
