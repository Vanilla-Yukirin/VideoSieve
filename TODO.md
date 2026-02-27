# TODO

## Open Issues

### 成品质资产默认选择问题
**状态**: ✅ 已完成（策略已调整为：分析低码率 + 成品高码率 + 分析优先 AVC）

**文件**: `apps/web/components/IngestProbe.tsx`

**备注**: 原描述为“分析和成品都选最好/最下面”，现已改为差异化默认策略。

---

### 缺少删除 Project 功能
**状态**: ❌ 未完成

**文件**: `apps/web/app/projects/[id]/page.tsx`（及后端 project 删除接口）

**问题**: 当前 job 页面删除按钮是 job 级，不是 project 级；删空 job 后 project 仍保留。

**期望行为**:
- 提供明确的“删除 Project”功能（删除整个项目）
- 与“删除 Job”语义彻底区分，避免误导
- 保持 job 页按钮文案与行为一致（删除 Job）
- 可选：project 下无 job 时支持自动删除（或可配置策略）

---

### 关键帧实时更新导致页面滚动跳动
**状态**: 🟡 已缓解（待实测确认）

**文件**: `apps/web/app/jobs/[id]/page.tsx`, `apps/web/lib/hooks/useJobRealtime.ts`

**问题**: 关键帧实时到达时触发布局重排，滚动位置可能被动变化。

**已做修复**:
- 产物区默认折叠
- 图片不逐条堆在右侧
- 关键帧区使用固定滚动容器

**待确认**:
- 是否完全消除滚动跳动需实测体感判定

---

### 关键帧压缩包下载 404 交互优化
**状态**: ✅ 已完成

**文件**: `apps/web/app/jobs/[id]/page.tsx`, `apps/web/lib/i18n/messages.ts`

**问题**: 旧实现直接跳下载地址，404 时会进入错误页面。

**已实现**:
- 将“关键帧压缩包下载”改为按钮点击逻辑
- 点击后先 `HEAD` 探测下载接口状态
- 若 404：弹窗提示“该任务未生成关键帧压缩包（旧任务或流程未启用）”
- 若成功：使用浏览器原生下载（`window.location.assign(...)`）
- 若其他失败：弹窗提示“下载失败，请稍后重试”

---

### 实时日志 i18n（汉化）
**状态**: ❌ 未完成

**文件**: `apps/web/components/LogViewer.tsx`, `apps/web/lib/i18n/messages.ts`

**问题**: 实时日志存在英文/原始码直出，阅读成本高。

**期望行为**:
- 关键日志事件支持 i18n 映射（至少中英文）
- 保留原始日志字段用于排障（例如展开查看）

---

### 日志持久化（退出重进可见历史）
**状态**: ❌ 未完成

**文件**: `apps/api/*`, `apps/web/lib/hooks/useJobRealtime.ts`, `apps/web/components/LogViewer.tsx`

**问题**: 当前实时日志为会话态，退出页面后重进看不到历史日志。

**期望行为**:
- 日志持久化（数据库或文件）
- 进入 job 页面时先拉取历史日志，再增量叠加实时日志
- 提供最近 N 条或分页加载策略

---

### 实时日志栏与产物侧边栏布局重构
**状态**: 🟡 架构待定

**文件**: `apps/web/app/jobs/[id]/page.tsx`, `apps/web/components/LogViewer.tsx`

**问题**: 当前日志区与产物区布局在可读性、扩展性上仍不理想。

**期望行为**:
- 重构信息层级与布局分区（含桌面/移动端）
- 在架构未定前先产出候选方案，再确定实现

---

### 接入 ASR / Frame Summary / Overall Summary API 并做脚本测试
**状态**: ❌ 未完成

**文件**: `packages/asr/*`, `packages/frame_summary/*`, `packages/deliverables/*`, `scripts/*`, `apps/web/app/settings/*`

**问题**: 目前链路未完成完整外部 API 接入与多路径验证。

**关键区分**:
- `Frame Summary API`: 必须是 VLM（支持视觉输入），用于图片级摘要
- `Overall Summary API`: 可为 LLM 或 VLM，用于全局总结（与 frame summary 分离，不要求同一服务）

**期望行为**:
- 完成 ASR API 接入
- 完成 Frame Summary API（VLM）接入
- 完成 Overall Summary API 接入
- 增加脚本测试覆盖不同开关组合与输入路径

---

### 设置页支持双 Summary API 配置与视觉能力开关
**状态**: ❌ 未完成

**文件**: `apps/web/app/settings/*`, `apps/web/lib/api/types.ts`, `apps/api/models.py`, `apps/api/service.py`

**问题**: 当前设置模型配置无法清晰区分 frame summary 与 overall summary。

**期望行为**:
- 增加两套配置：
  - `Frame Summary API`（必填且必须支持视觉）
  - `Overall Summary API`（可 LLM 或 VLM）
- 为 `Overall Summary API` 增加“支持视觉输入”勾选项
- 运行时根据该勾选决定是否向 overall summary 传原图

---

### 创建 Job 界面增加处理开关 + Project/Job 网页端命名
**状态**: ❌ 未完成

**文件**: `apps/web/app/projects/[id]/page.tsx`, `apps/web/app/jobs/[id]/page.tsx`, `apps/web/lib/api/types.ts`, `apps/api/models.py`, `packages/infra/sqlite_repository.py`

**问题**:
- 创建 job 时流程开关不足，无法按需组合 ASR / 关键帧 / 图片摘要 / 全文总结
- 当前主要展示 ID，缺少可编辑显示名

**期望行为**:
- 创建 job 增加勾选项：
  - 开启 ASR
  - 开启关键帧
  - 使用 VLM 提取图片摘要
  - 使用大模型进行全文 Summary
- Summary 输入按开关组合动态决定：
  - 未开启关键帧 -> 不传图片
  - 开启关键帧但未开启图片摘要 -> 仅文本链路
  - 开启图片摘要 -> 图片摘要与文本共同参与总结
- Project 与 Job 支持网页端重命名（显示名），ID 继续作为内部稳定标识

---

## Completed

- ~~Cookie 解密失败状态显示问题~~ ✅
- ~~关键帧图片预览交互问题（lightbox/modal + 键盘切换）~~ ✅

---
