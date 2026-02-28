# TODO

## Open Issues

### 成品质资产默认选择问题
**状态**: ✅ 已完成（策略已调整为：分析低码率 + 成品高码率 + 分析优先 AVC）

**文件**: `apps/web/components/IngestProbe.tsx`

**备注**: 原描述为“分析和成品都选最好/最下面”，现已改为差异化默认策略。

---

### 缺少删除 Project 功能
**状态**: ✅ 已完成

**文件**: `apps/web/app/projects/[id]/page.tsx`, `apps/api/service.py`, `apps/api/main.py`, `apps/api/rest.py`, `packages/infra/sqlite_repository.py`

**已实现**:
- 新增 `DELETE /projects/{project_id}`（支持 `force_cancel_active`）
- project 页新增“删除项目”按钮，并与 job 页“删除任务”语义分离
- 存在活动任务时先弹窗确认；确认后自动发送 cancel，再阻塞等待并删除项目
- 删除后会清理 project 元数据、关联 jobs 与 project 工作区目录

---

### 关键帧实时更新导致页面滚动跳动
**状态**: ✅ 已完成

**文件**: `apps/web/app/jobs/[id]/page.tsx`, `apps/web/lib/hooks/useJobRealtime.ts`

**问题**: 关键帧实时到达时触发布局重排，滚动位置可能被动变化。

**已做修复**:
- 产物区默认折叠
- 图片不逐条堆在右侧
- 关键帧区使用固定滚动容器

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

### 实时日志中文化
**状态**: ✅ 已完成

**文件**: `packages/pipeline/orchestrator.py`, `apps/api/service.py`

**已实现**:
- 将 pipeline 关键日志文案改为中文（阶段开始/完成/失败、关键帧回退与异常提示等）
- 派发失败日志改为中文文案（`任务派发失败`）

---

### 日志持久化（退出重进可见历史）
**状态**: ✅ 已完成

**文件**: `packages/pipeline/orchestrator.py`, `apps/api/service.py`

**已实现**:
- 日志按 job 落盘到工作区 `logs/worker.log`
- `GET /jobs/{job_id}/snapshot` 会读取持久化日志并与内存日志合并
- 退出页面后重进仍可在日志区看到最近历史（当前保留最近 100 条）

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

### 前端主题模式（White/Dark）+ 设置持久化
**状态**: ❌ 未完成

**文件**: `apps/web/app/settings/*`, `apps/web/app/layout.tsx`, `apps/web/app/globals.css`, `apps/web/lib/api/types.ts`, `apps/api/models.py`, `apps/api/service.py`

**问题**: 当前缺少统一主题切换与用户设置持久化能力。

**期望行为**:
- 支持 white / dark 模式切换
- 在设置页提供主题选项
- 用户选择可持久化（刷新/重进后保持）
- 明确默认主题与首次加载策略（避免闪烁）

---

### 背景图片设置（用户上传）
**状态**: ❌ 未完成

**文件**: `apps/web/app/settings/*`, `apps/web/app/globals.css`, `apps/api/*`（上传与资源访问接口）

**问题**: 当前界面背景不可自定义。

**期望行为**:
- 设置页支持上传背景图片
- 上传后可立即预览并应用
- 背景配置可持久化
- 需包含基础限制：类型、大小、尺寸、存储位置与回退默认背景

---

### 左上角品牌位资源固化（Logo/Avatar 区）
**状态**: ❌ 未完成

**文件**: `apps/web/components/AppShell.tsx`（或导航组件）, `apps/web/public/*`（静态资源）

**问题**: 前端左上角“控制台”左侧区域当前未定义品牌资源规范。

**期望行为**:
- 该区域使用项目内固定资源（写死路径），如固定图片或 SVG
- 不走用户上传，不做动态配置
- 明确尺寸、对齐、深浅主题下可读性
- 作为统一品牌入口位，后续仅替换资源文件即可

---

## Completed

- ~~Cookie 解密失败状态显示问题~~ ✅
- ~~关键帧图片预览交互问题（lightbox/modal + 键盘切换）~~ ✅

---
