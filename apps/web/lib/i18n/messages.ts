export type Locale = "zh" | "en";

export type MessageKey =
  | "lang.zh"
  | "lang.en"
  | "home.title"
  | "shell.controlPlane"
  | "home.subtitle.user"
  | "home.subtitle.guest"
  | "home.newProject"
  | "home.systemSettings"
  | "home.cookieVault"
  | "home.logout"
  | "home.leaveGuest"
  | "home.cookieHint"
  | "home.mockMode"
  | "home.empty"
  | "home.createFirst"
  | "home.newProjectTitlePrefix"
  | "setup.title"
  | "setup.desc"
  | "setup.username"
  | "setup.password"
  | "setup.passwordHint"
  | "setup.submit"
  | "setup.checking"
  | "setup.required"
  | "setup.already"
  | "login.title"
  | "login.desc"
  | "login.username"
  | "login.password"
  | "login.submit"
  | "login.guest"
  | "login.invalid"
  | "login.setupFirst"
  | "login.required"
  | "login.guestDisabled"
  | "login.guestEnterFail"
  | "settings.title"
  | "settings.desc"
  | "settings.back"
  | "settings.access"
  | "settings.guestMode"
  | "settings.guestCookie"
  | "settings.save"
  | "settings.saved"
  | "settings.load"
  | "settings.guestCookieKeyRequired"
  | "project.newJob"
  | "project.cookie"
  | "project.cookieNone"
  | "project.cookieNeedLogin"
  | "project.cookieUnavailable"
  | "project.cookieDisabled"
  | "project.cookieDefaultSuffix"
  | "project.summary"
  | "project.start"
  | "project.cooldown"
  | "project.authRequired"
  | "project.cooldownActive"
  | "project.history"
  | "project.noJobs"
  | "project.notFound"
  | "project.goBack"
  | "project.delete"
  | "project.deleting"
  | "project.confirmDelete"
  | "project.confirmDeleteWithActive"
  | "project.deleteFailed"
  | "project.deletePendingCancel"
  | "project.deletePendingCleanup"
  | "project.deleteInProgress"
  | "cookie.title"
  | "cookie.back"
  | "cookie.desc"
  | "cookie.add"
  | "cookie.saved"
  | "cookie.loading"
  | "cookie.loadFailed"
  | "cookie.none"
  | "cookie.default"
  | "cookie.setDefault"
  | "cookie.validate"
  | "cookie.edit"
  | "cookie.delete"
  | "cookie.created"
  | "cookie.updated"
  | "cookie.deleted"
  | "cookie.validationDone"
  | "cookie.defaultUpdated"
  | "cookie.setAsDefault"
  | "cookie.lastValidated"
  | "cookie.validateSourceLabel"
  | "cookie.validateSourcePlaceholder"
  | "cookie.validateSourceRequired"
  | "ingest.probe"
  | "ingest.probing"
  | "ingest.sourceUrl"
  | "ingest.noCookieHint"
  | "ingest.availableFormats"
  | "ingest.analysis"
  | "ingest.analysisHint"
  | "ingest.quality"
  | "ingest.qualityHint"
  | "ingest.video"
  | "ingest.audio"
  | "ingest.auto"
  | "ingest.duplicate"
  | "job.status"
  | "job.live"
  | "job.offline"
  | "job.stage"
  | "job.initializing"
  | "job.logs"
  | "job.artifacts"
  | "job.noArtifacts"
  | "job.projectLabel"
  | "job.workspaceLabel"
  | "job.copyWorkspace"
  | "job.copyWorkspaceOk"
  | "job.copyWorkspaceFail"
  | "job.keyframesTitle"
  | "job.keyframeAlt"
  | "job.keyframesZipLabel"
  | "job.keyframesZipNotFound"
  | "job.keyframesZipDownloadFailed"
  | "logs.empty"
  | "logs.level.info"
  | "logs.level.warning"
  | "logs.level.error"
  | "logs.level.unknown"
  | "control.pause"
  | "control.resume"
  | "control.cancel"
  | "control.cancelling"
  | "control.delete"
  | "control.deleteRequested"
  | "control.cancelAccepted"
  | "control.deleteDone"
  | "control.deleteRetrying"
  | "control.deleteRetryTimeout"
  | "control.deleteRetryMaxed"
  | "control.reject"
  | "control.fail"
  | "control.acceptedInfo"
  | "control.deletePendingCleanup"
  | "control.confirmDelete"
  | "projectCard.unknown"
  | "projectCard.remove"
  | "projectCard.untitled"
  | "projectCard.created"
  | "projectCard.view"
  | "projectCard.loadFailed"
  | "common.loading"
  | "common.save"
  | "common.cancel"
  | "error.createProject"
  | "error.loginFailed"
  | "error.setupFailed"
  | "error.probeFailed"
  | "cookie.required"
  | "cookie.nameRequired"
  | "cookie.namePlaceholder"
  | "cookie.textPlaceholder"
  | "cookie.replacePlaceholder"
  | "cookie.createFailed"
  | "cookie.deleteFailed"
  | "cookie.setDefaultFailed"
  | "cookie.validateFailed"
  | "cookie.updateFailed"
  | "project.idLabel"
  | "project.stageLabel"
  | "project.errorLabel"
  | "ingest.table.id"
  | "ingest.table.res"
  | "ingest.table.fps"
  | "ingest.table.vcodec"
  | "ingest.table.acodec"
  | "ingest.table.type"
  | "ingest.type.video"
  | "ingest.type.audio"
  | "ingest.type.muxed"
  | "ingest.urlPlaceholder"
  | "deliverables.title"
  | "deliverables.tabRaw"
  | "deliverables.tabPolished"
  | "deliverables.tabSummary"
  | "deliverables.notAvailable"
  | "deliverables.error"
  | "deliverables.emptyTimeline"
  | "deliverables.polishedPlaceholder"
  | "deliverables.summaryPlaceholder"
  | "deliverables.frameNoDesc";

type MessageMap = Record<MessageKey, string>;

export const messages: Record<Locale, MessageMap> = {
  zh: {
    "lang.zh": "中文",
    "lang.en": "English",
    "home.title": "项目",
    "shell.controlPlane": "控制台",
    "home.subtitle.user": "你的 VideoSieve 项目本地索引。",
    "home.subtitle.guest": "游客会话（全服共享冷却生效）。",
    "home.newProject": "新建项目",
    "home.systemSettings": "系统设置",
    "home.cookieVault": "Cookie Vault",
    "home.logout": "退出登录",
    "home.leaveGuest": "退出游客",
    "home.cookieHint": "私有视频需要登录 Cookie。登录后可在 Cookie Vault 管理。",
    "home.mockMode": "当前为本地 mock 模式。启动后端并设置 NEXT_PUBLIC_API_MODE=remote 可切换到真实 API。",
    "home.empty": "本地索引中还没有项目。",
    "home.createFirst": "创建第一个项目",
    "home.newProjectTitlePrefix": "新项目",
    "setup.title": "首次初始化",
    "setup.desc": "为当前部署创建唯一管理员账号。",
    "setup.username": "用户名",
    "setup.password": "密码",
    "setup.passwordHint": "密码至少 8 位。",
    "setup.submit": "完成初始化",
    "setup.checking": "正在检查初始化状态...",
    "setup.required": "用户名和密码不能为空。",
    "setup.already": "系统已初始化，请直接登录。",
    "login.title": "登录",
    "login.desc": "登录后可管理设置并提交不受游客限制的任务。",
    "login.username": "用户名",
    "login.password": "密码",
    "login.submit": "登录",
    "login.guest": "游客进入",
    "login.invalid": "用户名或密码错误。",
    "login.setupFirst": "系统尚未初始化，请先完成初始化。",
    "login.required": "用户名和密码不能为空。",
    "login.guestDisabled": "游客模式已关闭。",
    "login.guestEnterFail": "无法进入游客模式。",
    "settings.title": "系统设置",
    "settings.desc": "配置当前部署的游客访问策略。",
    "settings.back": "返回",
    "settings.access": "访问控制",
    "settings.guestMode": "启用游客模式",
    "settings.guestCookie": "允许游客提交 cookie_id",
    "settings.save": "保存设置",
    "settings.saved": "设置已保存。",
    "settings.load": "正在加载设置...",
    "settings.guestCookieKeyRequired": "无法开启游客 Cookie 输入：服务端必须配置 GUEST_COOKIE_KEY。",
    "project.newJob": "新任务",
    "project.cookie": "Cookie",
    "project.cookieNone": "不使用 Cookie",
    "project.cookieNeedLogin": "部分视频可能需要登录，请按需选择 Cookie。",
    "project.cookieUnavailable": "Cookie 列表不可用，已降级为无 Cookie 模式。",
    "project.cookieDisabled": "系统策略已禁用游客 Cookie 输入。",
    "project.cookieDefaultSuffix": " [默认]",
    "project.summary": "启用摘要生成",
    "project.start": "开始下载与处理",
    "project.cooldown": "游客冷却：{seconds}s",
    "project.authRequired": "该操作需要登录。",
    "project.cooldownActive": "游客冷却中，请 {seconds}s 后重试。",
    "project.history": "任务历史",
    "project.noJobs": "还没有任务，先在上方启动一个。",
    "project.notFound": "项目不存在",
    "project.goBack": "返回",
    "project.delete": "删除项目",
    "project.deleting": "正在取消任务并删除项目...",
    "project.confirmDelete": "确认删除整个项目及其所有任务与产物吗？",
    "project.confirmDeleteWithActive": "当前有 {count} 个任务仍在运行。继续删除将自动取消这些任务，是否继续？",
    "project.deleteFailed": "删除项目失败，请稍后重试。",
    "project.deletePendingCancel": "任务仍在取消中，项目暂未删除。请稍后重试。",
    "project.deletePendingCleanup": "任务已取消请求，但资源仍在释放中。请稍后重试删除。",
    "project.deleteInProgress": "项目删除进行中，请稍候。",
    "cookie.title": "Cookie Vault",
    "cookie.back": "返回项目",
    "cookie.desc": "按 ID 管理登录 Cookie。提交后不回显明文。",
    "cookie.add": "添加 Cookie",
    "cookie.saved": "已保存 Cookie",
    "cookie.loading": "正在加载 Cookie...",
    "cookie.loadFailed": "加载 Cookie 失败。",
    "cookie.none": "还没有 Cookie。",
    "cookie.default": "默认",
    "cookie.setDefault": "设为默认",
    "cookie.validate": "校验",
    "cookie.edit": "编辑",
    "cookie.delete": "删除",
    "cookie.created": "Cookie 已创建。",
    "cookie.updated": "Cookie 已更新。",
    "cookie.deleted": "Cookie 已删除。",
    "cookie.validationDone": "校验完成：{status}",
    "cookie.defaultUpdated": "默认 Cookie 已更新。",
    "cookie.setAsDefault": "设为默认 Cookie",
    "cookie.lastValidated": "最近校验时间",
    "cookie.validateSourceLabel": "校验视频页 URL",
    "cookie.validateSourcePlaceholder": "https://www.bilibili.com/video/BV...",
    "cookie.validateSourceRequired": "请先填写用于校验的具体视频页 URL。",
    "ingest.probe": "探测",
    "ingest.probing": "探测中...",
    "ingest.sourceUrl": "源地址",
    "ingest.noCookieHint": "未选择 Cookie，可能无法显示高规格格式。",
    "ingest.availableFormats": "可用格式（{count}）",
    "ingest.analysis": "分析资产",
    "ingest.analysisHint": "建议：低分辨率 AVC，分析更快",
    "ingest.quality": "成品质资产",
    "ingest.qualityHint": "最终输出质量，按需选择最高分辨率",
    "ingest.video": "视频",
    "ingest.audio": "音频",
    "ingest.auto": "自动",
    "ingest.duplicate": "分析与成品配置相同，将复用下载。",
    "job.status": "状态",
    "job.live": "实时",
    "job.offline": "离线（轮询）",
    "job.stage": "阶段",
    "job.initializing": "初始化中...",
    "job.logs": "实时日志",
    "job.artifacts": "产物",
    "job.noArtifacts": "暂无产物。",
    "job.projectLabel": "项目",
    "job.workspaceLabel": "工作区",
    "job.copyWorkspace": "复制工作区路径",
    "job.copyWorkspaceOk": "已复制",
    "job.copyWorkspaceFail": "复制失败",
    "job.keyframesTitle": "关键帧 ({count})",
    "job.keyframeAlt": "关键帧",
    "job.keyframesZipLabel": "关键帧图片压缩包 ({count})",
    "job.keyframesZipNotFound": "该任务未生成关键帧压缩包（旧任务或流程未启用）。",
    "job.keyframesZipDownloadFailed": "下载失败，请稍后重试。",
    "logs.empty": "暂无日志...",
    "logs.level.info": "信息",
    "logs.level.warning": "警告",
    "logs.level.error": "错误",
    "logs.level.unknown": "日志",
    "control.pause": "暂停",
    "control.resume": "恢复",
    "control.cancel": "中断",
    "control.cancelling": "中断请求中",
    "control.delete": "删除任务",
    "control.deleteRequested": "删除请求已发送，正在尝试删除任务...",
    "control.cancelAccepted": "中断请求已发送，正在停止任务...",
    "control.deleteDone": "任务已删除。",
    "control.deleteRetrying": "删除处理中，自动重试第 {count} 次...",
    "control.deleteRetryTimeout": "删除仍在处理中，请稍后重试“删除任务”。",
    "control.deleteRetryMaxed": "自动重试已达上限，请稍后手动点击“删除任务”重试。",
    "control.reject": "命令被拒绝：{reason}",
    "control.fail": "命令发送失败",
    "control.acceptedInfo": "命令已受理：{reason}",
    "control.deletePendingCleanup": "删除处理中：文件仍被占用，请稍后重试删除。",
    "control.confirmDelete": "确认删除该任务及其产物吗？",
    "projectCard.unknown": "未知项目",
    "projectCard.remove": "从索引移除",
    "projectCard.untitled": "未命名",
    "projectCard.created": "创建于",
    "projectCard.view": "查看详情",
    "projectCard.loadFailed": "项目加载失败",
    "common.loading": "加载中...",
    "common.save": "保存",
    "common.cancel": "取消",
    "error.createProject": "创建项目失败",
    "error.loginFailed": "登录失败。",
    "error.setupFailed": "初始化失败。",
    "error.probeFailed": "探测失败",
    "cookie.required": "名称与 Netscape Cookie 文本不能为空。",
    "cookie.nameRequired": "Cookie 名称不能为空。",
    "cookie.namePlaceholder": "Cookie 名称",
    "cookie.textPlaceholder": "# Netscape cookie 文件内容",
    "cookie.replacePlaceholder": "如需替换，粘贴新的 Netscape cookie 文本（可选）",
    "cookie.createFailed": "创建失败",
    "cookie.deleteFailed": "删除失败",
    "cookie.setDefaultFailed": "设置默认失败",
    "cookie.validateFailed": "校验失败",
    "cookie.updateFailed": "更新失败",
    "project.idLabel": "ID",
    "project.stageLabel": "阶段",
    "project.errorLabel": "错误",
    "ingest.table.id": "ID",
    "ingest.table.res": "分辨率",
    "ingest.table.fps": "帧率",
    "ingest.table.vcodec": "视频编码",
    "ingest.table.acodec": "音频编码",
    "ingest.table.type": "类型",
    "ingest.type.video": "视频",
    "ingest.type.audio": "音频",
    "ingest.type.muxed": "混流",
    "ingest.urlPlaceholder": "https://www.bilibili.com/video/BV...",
    "deliverables.title": "成果预览",
    "deliverables.tabRaw": "原始转录",
    "deliverables.tabPolished": "润色稿",
    "deliverables.tabSummary": "摘要",
    "deliverables.notAvailable": "尚未生成（任务完成后可见）",
    "deliverables.error": "加载失败，请刷新页面重试",
    "deliverables.emptyTimeline": "时间线为空",
    "deliverables.polishedPlaceholder": "润色稿需要配置 LLM API，敬请期待。",
    "deliverables.summaryPlaceholder": "摘要需要配置 LLM API，敬请期待。",
    "deliverables.frameNoDesc": "（暂无图片描述，待 VLM 接入后生成）"
  },
  en: {
    "lang.zh": "中文",
    "lang.en": "English",
    "home.title": "Projects",
    "shell.controlPlane": "Control Plane",
    "home.subtitle.user": "Local index of your VideoSieve projects.",
    "home.subtitle.guest": "Guest session (shared global cooldown applies).",
    "home.newProject": "New Project",
    "home.systemSettings": "System Settings",
    "home.cookieVault": "Cookie Vault",
    "home.logout": "Logout",
    "home.leaveGuest": "Leave Guest",
    "home.cookieHint": "Private videos may require login cookies. Manage them in Cookie Vault when signed in.",
    "home.mockMode": "Running in local mock mode. Start backend and set NEXT_PUBLIC_API_MODE=remote for live API.",
    "home.empty": "No projects found in local index.",
    "home.createFirst": "Create your first project",
    "home.newProjectTitlePrefix": "New Project",
    "setup.title": "Initial Setup",
    "setup.desc": "Create the single admin account for this deployment.",
    "setup.username": "Username",
    "setup.password": "Password",
    "setup.passwordHint": "Password must be at least 8 characters.",
    "setup.submit": "Complete Setup",
    "setup.checking": "Checking setup status...",
    "setup.required": "Username and password are required.",
    "setup.already": "System is already initialized. Please login.",
    "login.title": "Login",
    "login.desc": "Sign in to manage settings and submit unrestricted jobs.",
    "login.username": "Username",
    "login.password": "Password",
    "login.submit": "Login",
    "login.guest": "Enter as Guest",
    "login.invalid": "Invalid username or password.",
    "login.setupFirst": "System is not initialized yet. Please complete setup first.",
    "login.required": "Username and password are required.",
    "login.guestDisabled": "Guest mode is disabled.",
    "login.guestEnterFail": "Unable to enter as guest.",
    "settings.title": "System Settings",
    "settings.desc": "Configure guest access for this deployment.",
    "settings.back": "Back",
    "settings.access": "Access Controls",
    "settings.guestMode": "Enable guest mode",
    "settings.guestCookie": "Allow guests to submit cookie_id",
    "settings.save": "Save Settings",
    "settings.saved": "Settings saved.",
    "settings.load": "Loading settings...",
    "settings.guestCookieKeyRequired": "Cannot enable guest cookie input: GUEST_COOKIE_KEY is required on the server.",
    "project.newJob": "New Job",
    "project.cookie": "Cookie",
    "project.cookieNone": "Do not use cookie",
    "project.cookieNeedLogin": "Some videos may require login. Choose a cookie when needed.",
    "project.cookieUnavailable": "Cookie list unavailable. Continuing in no-cookie mode.",
    "project.cookieDisabled": "Guest cookie input is disabled by system policy.",
    "project.cookieDefaultSuffix": " [default]",
    "project.summary": "Enable summary generation",
    "project.start": "Start Download & Process",
    "project.cooldown": "Guest cooldown: {seconds}s",
    "project.authRequired": "Authentication is required for this action.",
    "project.cooldownActive": "Guest cooldown active. Try again in {seconds}s.",
    "project.history": "Job History",
    "project.noJobs": "No jobs run yet. Start one above!",
    "project.notFound": "Project Not Found",
    "project.goBack": "Go Back",
    "project.delete": "Delete Project",
    "project.deleting": "Cancelling jobs and deleting project...",
    "project.confirmDelete": "Delete this project with all jobs and artifacts?",
    "project.confirmDeleteWithActive": "There are {count} active jobs. Continue and auto-cancel them before deleting the project?",
    "project.deleteFailed": "Failed to delete project. Please try again.",
    "project.deletePendingCancel": "Jobs are still cancelling. Project was not deleted yet. Please retry shortly.",
    "project.deletePendingCleanup": "Cancel was requested, but resources are still being released. Please retry deletion shortly.",
    "project.deleteInProgress": "Project deletion is in progress. Please wait.",
    "cookie.title": "Cookie Vault",
    "cookie.back": "Back to Projects",
    "cookie.desc": "Manage login cookies by id. Cookie plaintext is never shown after submit.",
    "cookie.add": "Add Cookie",
    "cookie.saved": "Saved Cookies",
    "cookie.loading": "Loading cookies...",
    "cookie.loadFailed": "Failed to load cookies.",
    "cookie.none": "No cookies yet.",
    "cookie.default": "default",
    "cookie.setDefault": "Set Default",
    "cookie.validate": "Validate",
    "cookie.edit": "Edit",
    "cookie.delete": "Delete",
    "cookie.created": "Cookie created.",
    "cookie.updated": "Cookie updated.",
    "cookie.deleted": "Cookie deleted.",
    "cookie.validationDone": "Validation completed: {status}",
    "cookie.defaultUpdated": "Default cookie updated.",
    "cookie.setAsDefault": "Set as default cookie",
    "cookie.lastValidated": "last_validated_at",
    "cookie.validateSourceLabel": "Validate Source URL",
    "cookie.validateSourcePlaceholder": "https://www.bilibili.com/video/BV...",
    "cookie.validateSourceRequired": "Please enter a concrete video page URL before validating.",
    "ingest.probe": "Probe",
    "ingest.probing": "Probing...",
    "ingest.sourceUrl": "Source URL",
    "ingest.noCookieHint": "No cookie selected. Probe may not show high-spec formats.",
    "ingest.availableFormats": "Available formats ({count})",
    "ingest.analysis": "Analysis Asset",
    "ingest.analysisHint": "Recommended: low-resolution AVC for fast analysis",
    "ingest.quality": "Quality Asset",
    "ingest.qualityHint": "Final output quality — choose highest resolution desired",
    "ingest.video": "Video",
    "ingest.audio": "Audio",
    "ingest.auto": "Auto",
    "ingest.duplicate": "Analysis and quality assets have identical configuration — the download will be reused.",
    "job.status": "Status",
    "job.live": "Live",
    "job.offline": "Offline (Polling)",
    "job.stage": "Stage",
    "job.initializing": "Initializing...",
    "job.logs": "Realtime Logs",
    "job.artifacts": "Artifacts",
    "job.noArtifacts": "No artifacts yet.",
    "job.projectLabel": "Project",
    "job.workspaceLabel": "Workspace",
    "job.copyWorkspace": "Copy workspace path",
    "job.copyWorkspaceOk": "Copied",
    "job.copyWorkspaceFail": "Copy failed",
    "job.keyframesTitle": "Keyframes ({count})",
    "job.keyframeAlt": "keyframe",
    "job.keyframesZipLabel": "Keyframe images zip ({count})",
    "job.keyframesZipNotFound": "This job does not have a keyframe images zip (old job or feature not enabled).",
    "job.keyframesZipDownloadFailed": "Download failed. Please try again later.",
    "logs.empty": "No logs available...",
    "logs.level.info": "Info",
    "logs.level.warning": "Warning",
    "logs.level.error": "Error",
    "logs.level.unknown": "Log",
    "control.pause": "Pause",
    "control.resume": "Resume",
    "control.cancel": "Interrupt",
    "control.cancelling": "Interrupting",
    "control.delete": "Delete Job",
    "control.deleteRequested": "Delete requested. Trying to remove the job...",
    "control.cancelAccepted": "Interrupt requested. Stopping task...",
    "control.deleteDone": "Job deleted.",
    "control.deleteRetrying": "Delete in progress. Auto-retry attempt {count}...",
    "control.deleteRetryTimeout": "Delete is still in progress. Please retry delete shortly.",
    "control.deleteRetryMaxed": "Auto-retry limit reached. Please manually click Delete Job again shortly.",
    "control.reject": "Command rejected: {reason}",
    "control.fail": "Command failed to send",
    "control.acceptedInfo": "Command accepted: {reason}",
    "control.deletePendingCleanup": "Delete in progress: files are still in use. Please retry shortly.",
    "control.confirmDelete": "Delete this job and its artifacts?",
    "projectCard.unknown": "Unknown Project",
    "projectCard.remove": "Remove from index",
    "projectCard.untitled": "Untitled",
    "projectCard.created": "Created",
    "projectCard.view": "View Details",
    "projectCard.loadFailed": "Failed to load project",
    "common.loading": "Loading...",
    "common.save": "Save",
    "common.cancel": "Cancel",
    "error.createProject": "Failed to create project",
    "error.loginFailed": "Login failed.",
    "error.setupFailed": "Bootstrap failed.",
    "error.probeFailed": "Probe failed",
    "cookie.required": "Name and Netscape cookie text are required.",
    "cookie.nameRequired": "Cookie name cannot be empty.",
    "cookie.namePlaceholder": "Cookie name",
    "cookie.textPlaceholder": "# Netscape cookie file text",
    "cookie.replacePlaceholder": "Paste new Netscape cookie text to replace (optional)",
    "cookie.createFailed": "Create failed",
    "cookie.deleteFailed": "Delete failed",
    "cookie.setDefaultFailed": "Set default failed",
    "cookie.validateFailed": "Validate failed",
    "cookie.updateFailed": "Update failed",
    "project.idLabel": "ID",
    "project.stageLabel": "Stage",
    "project.errorLabel": "Error",
    "ingest.table.id": "ID",
    "ingest.table.res": "Res",
    "ingest.table.fps": "FPS",
    "ingest.table.vcodec": "VCodec",
    "ingest.table.acodec": "ACodec",
    "ingest.table.type": "Type",
    "ingest.type.video": "video",
    "ingest.type.audio": "audio",
    "ingest.type.muxed": "muxed",
    "ingest.urlPlaceholder": "https://www.bilibili.com/video/BV...",
    "deliverables.title": "Results Preview",
    "deliverables.tabRaw": "Raw Transcript",
    "deliverables.tabPolished": "Polished Notes",
    "deliverables.tabSummary": "Summary",
    "deliverables.notAvailable": "Not yet generated (visible after job completes)",
    "deliverables.error": "Failed to load, please refresh and retry",
    "deliverables.emptyTimeline": "Timeline is empty",
    "deliverables.polishedPlaceholder": "Polished notes require LLM API configuration.",
    "deliverables.summaryPlaceholder": "Summary requires LLM API configuration.",
    "deliverables.frameNoDesc": "(No description yet — will be generated once VLM is connected)"
  }
};
