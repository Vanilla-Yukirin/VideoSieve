# TODO

## Frontend & Backend Issues

### 1. Cookie 解密失败状态显示问题
**文件**: `apps/api/service.py`, `apps/web/app/settings/cookies/page.tsx`

**问题**: 当 cookie 解密失败时，列表状态依然显示 `valid` 而非失败标记。即使用户点击检测，也会出现"无法通过检测"的情况，但状态未正确更新。

**期望行为**: 解密失败时应将状态标记为 `invalid` 或独立的失败状态，而不是保持 `valid`。

---

### 2. 成品质资产默认选择问题
**文件**: `apps/web/components/IngestProbe.tsx`

**问题**: 成品画质和音频的下拉栏当前默认选择第一个选项。

**期望行为**: 
- 画质选择应默认选择最好的画质（列表最下面的一项）
- 音频选择也应默认选择最好的音质（列表最下面的一项）

---

### 3. 关键帧图片预览交互问题
**文件**: `apps/web/app/jobs/[id]/page.tsx`

**问题**: 点击关键帧图片时当前会触发下载行为。

**期望行为**: 
- 点击图片应展示放大图（lightbox/modal）
- 放大后支持键盘左右键切换上一张/下一张
- 或提供左右切换按钮
- 支持关闭预览

---

### 4. 缺少删除 Project 功能
**文件**: `apps/web/app/projects/[id]/page.tsx`（及相关后端 project 删除接口）

**问题**: 当前在 job 子页面右上角"删除项目"按钮实际删除的是单个 job（单个视频），并非整个 project。即使删空所有 job，project 也不会自动删除。

**期望行为**:
- 提供明确的"删除 Project"功能（删除整个项目）
- 与"删除 Job"语义彻底区分，避免误导
- 修正现有 job 页面删除按钮的文案：当前写的是"删除项目"，实际是删除 job，应改为"删除视频"或"删除 Job"
- 可选：当 project 下所有 job 已删除后，支持自动删除该 project（或提供可配置策略）

---

### 5. 关键帧实时更新导致页面滚动跳动
**文件**: `apps/web/app/jobs/[id]/page.tsx`, `apps/web/lib/hooks/useJobRealtime.ts`

**问题**: 新建 job 后，关键帧通过 WebSocket 实时更新。每当新图片到达时，关键帧区域和右侧 artifacts 列表同时更新，触发页面重排（layout shift），导致浏览器滚动位置被动变化，界面自动向下跳动。

**期望行为**:
- 新增关键帧时不应造成页面滚动位置跳动
- 可考虑：锁定滚动位置、使用 CSS `content-visibility` 优化、或仅在用户主动滚动到底部时才加载新图片

---
