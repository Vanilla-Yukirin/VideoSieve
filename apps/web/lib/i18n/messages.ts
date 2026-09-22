export type Locale = "zh" | "en";

export type MessageKey =
  | "lang.zh"
  | "lang.en"
  | "home.title"
  | "shell.controlPlane"
  | "home.subtitle"
  | "home.newProject"
  | "home.systemSettings"
  | "home.cookieVault"
  | "home.cookieHint"
  | "home.empty"
  | "home.projectListLoadFailed"
  | "home.createFirst"
  | "home.newProjectTitlePrefix"
  | "setup.title"
  | "setup.checking"
  | "setup.stepProviders"
  | "setup.providerTitle"
  | "setup.providerDesc"
  | "setup.finish"
  | "setup.apiUnavailable"
  | "setup.retry"
  | "setup.profileRequirement"
  | "setup.ready"
  | "setup.missingProfiles"
  | "setup.savedNotVerified"
  | "setup.summaryOptional"
  | "setup.summaryEnable"
  | "setup.asrEndpointRequired"
  | "setup.vlmBaseUrlRequired"
  | "setup.vlmModelRequired"
  | "setup.vlmApiKeyRequired"
  | "setup.summaryBaseUrlRequired"
  | "setup.summaryModelRequired"
  | "setup.summaryApiKeyRequired"
  | "settings.title"
  | "settings.desc"
  | "settings.back"
  | "settings.save"
  | "settings.saved"
  | "settings.load"
  | "settings.asrSection"
  | "settings.asrDescription"
  | "settings.asrProvider"
  | "settings.asrProviderUnconfigured"
  | "settings.asrProviderCapsWriter"
  | "settings.asrEndpoint"
  | "settings.asrWebSocketHint"
  | "settings.asrEndpointRequired"
  | "settings.asrLanguage"
  | "settings.asrTimeout"
  | "settings.asrContext"
  | "settings.asrTokenHint"
  | "settings.asrTokenConfigured"
  | "settings.asrTokenNotConfigured"
  | "settings.asrToken"
  | "settings.asrUnconfiguredHint"
  | "settings.vlmSection"
  | "settings.vlmBaseUrl"
  | "settings.vlmModel"
  | "settings.vlmApiKeyHint"
  | "settings.vlmApiKey"
  | "settings.vlmPromptZh"
  | "settings.vlmPromptEn"
  | "settings.vlmPromptReset"
  | "settings.vlmConcurrency"
  | "settings.vlmRpm"
  | "settings.summarySection"
  | "settings.summaryBaseUrl"
  | "settings.summaryModel"
  | "settings.summaryApiKeyHint"
  | "settings.summaryApiKey"
  | "settings.credentialConfigured"
  | "settings.credentialNotConfigured"
  | "settings.credentialPlaceholder"
  | "settings.credentialKeepHint"
  | "settings.clearCredential"
  | "settings.clearCredentialMarked"
  | "settings.connectionNotVerified"
  | "settings.summaryPromptZh"
  | "settings.summaryPromptEn"
  | "settings.summaryMaxInputChars"
  | "settings.processingTitle"
  | "settings.processingDescription"
  | "providers.sectionTitle"
  | "providers.sectionDescription"
  | "providers.capabilityAsr"
  | "providers.capabilityFrame"
  | "providers.capabilityOverall"
  | "providers.asrDescription"
  | "providers.frameDescription"
  | "providers.overallDescription"
  | "providers.capswriterAvailable"
  | "providers.aliyunPlanned"
  | "providers.aliyunOption"
  | "providers.add"
  | "providers.empty"
  | "providers.default"
  | "providers.credentialConfigured"
  | "providers.credentialOptional"
  | "providers.credentialMissing"
  | "providers.setDefault"
  | "providers.test"
  | "providers.testing"
  | "providers.testSucceeded"
  | "providers.testFailed"
  | "providers.edit"
  | "providers.delete"
  | "providers.addTitle"
  | "providers.editTitle"
  | "providers.displayName"
  | "providers.template"
  | "providers.custom"
  | "providers.protocol"
  | "providers.serviceUrl"
  | "providers.apiRoot"
  | "providers.apiRootHint"
  | "providers.capswriterUrlHint"
  | "providers.model"
  | "providers.credential"
  | "providers.credentialNotSaved"
  | "providers.keepCredential"
  | "providers.optionalCredential"
  | "providers.credentialHint"
  | "providers.useDefault"
  | "providers.required"
  | "providers.modelRequired"
  | "providers.saveFailed"
  | "providers.deleteFailed"
  | "providers.confirmDelete"
  | "project.newJob"
  | "project.cookie"
  | "project.cookieNone"
  | "project.cookieHint"
  | "project.cookieUnavailable"
  | "project.cookieDefaultSuffix"
  | "project.summary"
  | "project.asrProfile"
  | "project.frameProfile"
  | "project.overallProfile"
  | "project.profileMissing"
  | "project.profileOptional"
  | "project.profileDefaultSuffix"
  | "project.profileLoadFailed"
  | "project.profileRequiredHint"
  | "project.start"
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
  | "project.rename"
  | "project.renamePlaceholder"
  | "project.renameRequired"
  | "project.renameFailed"
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
  | "cookie.statusUnknown"
  | "cookie.statusValid"
  | "cookie.statusExpired"
  | "cookie.statusInvalid"
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
  | "ingest.networkVideo"
  | "ingest.localUpload"
  | "ingest.chooseVideo"
  | "ingest.selectedFile"
  | "ingest.context"
  | "ingest.optional"
  | "ingest.contextPlaceholder"
  | "ingest.contextHint"
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
  | "job.closePreview"
  | "job.previousImage"
  | "job.nextImage"
  | "job.downloadImage"
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
  | "common.dismiss"
  | "error.createProject"
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
  | "deliverables.emptyPolished"
  | "deliverables.frameNoDesc";

type MessageMap = Record<MessageKey, string>;

export const messages: Record<Locale, MessageMap> = {
  zh: {
    "lang.zh": "中文",
    "lang.en": "English",
    "home.title": "项目",
    "shell.controlPlane": "控制台",
    "home.subtitle": "SQLite 中保存的 VideoSieve 项目。",
    "home.newProject": "新建项目",
    "home.systemSettings": "系统设置",
    "home.cookieVault": "Cookie Vault",
    "home.cookieHint": "私有视频可能需要站点 Cookie，可在 Cookie Vault 管理。",
    "home.empty": "还没有项目。",
    "home.projectListLoadFailed": "无法从服务端加载项目；当前显示浏览器中的旧缓存。",
    "home.createFirst": "创建第一个项目",
    "home.newProjectTitlePrefix": "新项目",
    "setup.title": "首次初始化",
    "setup.checking": "正在检查初始化状态...",
    "setup.stepProviders": "处理服务配置",
    "setup.providerTitle": "配置处理服务",
    "setup.providerDesc": "先添加语音识别和画面摘要配置。密钥只写入加密存储，不会回显。",
    "setup.finish": "开始使用",
    "setup.apiUnavailable": "无法连接 VideoSieve API。请确认 API 已启动后重试。",
    "setup.retry": "重新检查",
    "setup.profileRequirement": "必须至少添加一个 ASR 配置，以及一个已保存密钥的画面摘要配置；每类的默认配置会用于新任务。CapsWriter Token 可留空。",
    "setup.ready": "基础配置已齐全。你仍可先点击“测试连接”做一次真实请求。",
    "setup.missingProfiles": "请先补齐 ASR 配置，并为至少一个画面摘要配置保存 API Key。",
    "setup.savedNotVerified": "保存与验证是两个状态；请使用“测试连接”发起真实的最小请求。",
    "setup.summaryOptional": "整体摘要配置是选填项，可以稍后在系统设置中添加。",
    "setup.summaryEnable": "现在配置整体摘要服务",
    "setup.asrEndpointRequired": "请填写 CapsWriter WebSocket 地址。",
    "setup.vlmBaseUrlRequired": "请填写视觉模型 API 端点。",
    "setup.vlmModelRequired": "请填写视觉模型名称。",
    "setup.vlmApiKeyRequired": "请填写视觉模型 API Key，或保留已有密钥。",
    "setup.summaryBaseUrlRequired": "请填写摘要模型 API 端点。",
    "setup.summaryModelRequired": "请填写摘要模型名称。",
    "setup.summaryApiKeyRequired": "请填写摘要模型 API Key，或保留已有密钥。",
    "settings.title": "系统设置",
    "settings.desc": "配置当前部署的外部处理服务。",
    "settings.back": "返回",
    "settings.save": "保存设置",
    "settings.saved": "设置已保存。",
    "settings.load": "正在加载设置...",
    "settings.asrSection": "语音识别（ASR）",
    "settings.asrDescription": "VideoSieve 只负责适配外部 ASR 服务，不下载或运行语音模型。",
    "settings.asrProvider": "服务提供方",
    "settings.asrProviderUnconfigured": "未配置",
    "settings.asrProviderCapsWriter": "CapsWriter（WS）",
    "settings.asrEndpoint": "服务地址",
    "settings.asrWebSocketHint": "使用 CapsWriter 官方 WebSocket 协议。",
    "settings.asrEndpointRequired": "选择 CapsWriter 后必须填写服务地址。",
    "settings.asrLanguage": "语言（auto 表示自动）",
    "settings.asrTimeout": "超时时间（秒）",
    "settings.asrContext": "识别上下文（选填）",
    "settings.asrTokenHint": "Token 为选填项，仅在 CapsWriter 服务要求鉴权时填写。",
    "settings.asrTokenConfigured": "当前已配置 Token。",
    "settings.asrTokenNotConfigured": "当前未配置 Token，原版 CapsWriter 可直接使用。",
    "settings.asrToken": "CapsWriter Token",
    "settings.asrUnconfiguredHint": "未配置时，任务会明确失败并提示先选择 ASR 服务。",
    "settings.vlmSection": "视觉语言模型（VLM）",
    "settings.vlmBaseUrl": "API 端点",
    "settings.vlmModel": "模型名称",
    "settings.vlmApiKeyHint": "API Key 会加密保存，页面不会回显原值。",
    "settings.vlmApiKey": "视觉模型 API Key",
    "settings.vlmPromptZh": "帧描述提示词（中文）",
    "settings.vlmPromptEn": "帧描述提示词（英文）",
    "settings.vlmPromptReset": "重置为默认",
    "settings.vlmConcurrency": "最大并发请求数",
    "settings.vlmRpm": "每分钟请求上限（RPM，0 = 不限速）",
    "settings.summarySection": "整体摘要模型（LLM）",
    "settings.summaryBaseUrl": "API 端点",
    "settings.summaryModel": "模型名称",
    "settings.summaryApiKeyHint": "API Key 会加密保存，页面不会回显原值。",
    "settings.summaryApiKey": "摘要模型 API Key",
    "settings.credentialConfigured": "已配置",
    "settings.credentialNotConfigured": "未配置",
    "settings.credentialPlaceholder": "留空则保留当前密钥",
    "settings.credentialKeepHint": "输入新值会替换现有密钥；留空不会修改。",
    "settings.clearCredential": "清除已保存的密钥",
    "settings.clearCredentialMarked": "保存设置后将清除该密钥。",
    "settings.connectionNotVerified": "保存配置不会验证连接；请通过实际任务确认服务可用。",
    "settings.summaryPromptZh": "整体摘要提示词（中文）",
    "settings.summaryPromptEn": "整体摘要提示词（英文）",
    "settings.summaryMaxInputChars": "单轮最大输入字符数",
    "settings.processingTitle": "处理参数",
    "settings.processingDescription": "调整并发、限速和提示词；服务地址、协议、模型与密钥在上方配置档案中管理。",
    "providers.sectionTitle": "Provider 配置",
    "providers.sectionDescription": "可保存多套服务配置、指定每类默认项，并用真实最小请求验证连接。",
    "providers.capabilityAsr": "语音识别（ASR）",
    "providers.capabilityFrame": "画面摘要（VLM）",
    "providers.capabilityOverall": "整体摘要（LLM，可选）",
    "providers.asrDescription": "音频转写服务。VideoSieve 不内置或下载 ASR 模型。",
    "providers.frameDescription": "逐帧理解需要支持图像输入的模型。",
    "providers.overallDescription": "根据转录与画面描述生成完整摘要。",
    "providers.capswriterAvailable": "可用：CapsWriter（WebSocket），兼容原版无鉴权服务和可选 Bearer Token。",
    "providers.aliyunPlanned": "预留：阿里云百炼（HTTP，计划中），当前版本不会创建不可用配置。",
    "providers.aliyunOption": "阿里云百炼（HTTP，计划中）",
    "providers.add": "添加配置",
    "providers.empty": "尚未添加配置。",
    "providers.default": "默认",
    "providers.credentialConfigured": "密钥已保存",
    "providers.credentialOptional": "Token 选填",
    "providers.credentialMissing": "未保存密钥",
    "providers.setDefault": "设为默认",
    "providers.test": "测试连接",
    "providers.testing": "正在发起真实测试请求...",
    "providers.testSucceeded": "测试成功，耗时 {latency} ms。",
    "providers.testFailed": "测试失败。",
    "providers.edit": "编辑",
    "providers.delete": "删除",
    "providers.addTitle": "添加 Provider 配置",
    "providers.editTitle": "编辑 Provider 配置",
    "providers.displayName": "配置名称",
    "providers.template": "接口模板",
    "providers.custom": "自定义兼容接口",
    "providers.protocol": "接口协议",
    "providers.serviceUrl": "WebSocket 服务地址",
    "providers.apiRoot": "API 根地址",
    "providers.apiRootHint": "填写 API 根地址，通常以 /v1 结尾；不要填写 /chat/completions、/responses 或 /messages。",
    "providers.capswriterUrlHint": "填写 ws:// 或 wss:// 地址。原版 CapsWriter 默认无需 Token。",
    "providers.model": "模型 ID",
    "providers.credential": "API Key / Token",
    "providers.credentialNotSaved": "未保存",
    "providers.keepCredential": "留空保留当前密钥",
    "providers.optionalCredential": "选填；原版 CapsWriter 无需填写",
    "providers.credentialHint": "密钥加密保存且不会回显；保存配置本身不代表连接已验证。",
    "providers.useDefault": "设为此能力的默认配置",
    "providers.required": "请填写配置名称和服务地址。",
    "providers.modelRequired": "请填写模型 ID。",
    "providers.saveFailed": "保存 Provider 配置失败。",
    "providers.deleteFailed": "删除 Provider 配置失败。",
    "providers.confirmDelete": "确认删除配置“{name}”吗？历史任务的快照不会被修改。",
    "project.newJob": "新任务",
    "project.cookie": "Cookie",
    "project.cookieNone": "不使用 Cookie",
    "project.cookieHint": "部分视频可能需要站点 Cookie，请按需选择。",
    "project.cookieUnavailable": "Cookie 列表不可用，已降级为无 Cookie 模式。",
    "project.cookieDefaultSuffix": " [默认]",
    "project.summary": "启用摘要生成",
    "project.asrProfile": "ASR 配置",
    "project.frameProfile": "画面摘要配置",
    "project.overallProfile": "整体摘要配置",
    "project.profileMissing": "没有可用配置",
    "project.profileOptional": "未配置（选填）",
    "project.profileDefaultSuffix": " [默认]",
    "project.profileLoadFailed": "Provider 配置加载失败，请刷新或前往系统设置检查。",
    "project.profileRequiredHint": "开始任务前必须先在系统设置中添加 ASR 与画面摘要配置。",
    "project.start": "开始下载与处理",
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
    "project.rename": "编辑项目名称",
    "project.renamePlaceholder": "输入项目名称",
    "project.renameRequired": "项目名称不能为空。",
    "project.renameFailed": "项目名称保存失败，请重试。",
    "cookie.title": "Cookie Vault",
    "cookie.back": "返回项目",
    "cookie.desc": "按 ID 管理站点 Cookie。提交后不回显明文。",
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
    "cookie.statusUnknown": "未校验",
    "cookie.statusValid": "有效",
    "cookie.statusExpired": "已过期",
    "cookie.statusInvalid": "无效",
    "cookie.defaultUpdated": "默认 Cookie 已更新。",
    "cookie.setAsDefault": "设为默认 Cookie",
    "cookie.lastValidated": "最近校验时间",
    "cookie.validateSourceLabel": "校验视频页 URL",
    "cookie.validateSourcePlaceholder": "https://www.bilibili.com/video/BV...",
    "cookie.validateSourceRequired": "请先填写用于校验的具体视频页 URL。",
    "ingest.probe": "探测",
    "ingest.probing": "探测中...",
    "ingest.sourceUrl": "源地址",
    "ingest.noCookieHint": "无需 Cookie 也可探测公开视频；登录、会员或高码率格式可能不会显示。",
    "ingest.availableFormats": "可用格式（{count}）",
    "ingest.analysis": "分析资产",
    "ingest.analysisHint": "建议：低分辨率 AVC，分析更快",
    "ingest.quality": "成品质资产",
    "ingest.qualityHint": "最终输出质量，按需选择最高分辨率",
    "ingest.video": "视频",
    "ingest.audio": "音频",
    "ingest.auto": "自动",
    "ingest.duplicate": "分析与成品配置相同，将复用下载。",
    "ingest.networkVideo": "网络视频",
    "ingest.localUpload": "本地上传",
    "ingest.chooseVideo": "选择视频文件",
    "ingest.selectedFile": "已选择",
    "ingest.context": "背景信息",
    "ingest.optional": "（可选）",
    "ingest.contextPlaceholder": "粘贴视频简介、评论或其他背景资料...",
    "ingest.contextHint": "用于补充本地视频无法自动获取的简介、评论等上下文信息。",
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
    "job.closePreview": "关闭预览",
    "job.previousImage": "上一张图片",
    "job.nextImage": "下一张图片",
    "job.downloadImage": "下载图片",
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
    "common.dismiss": "关闭通知",
    "error.createProject": "创建项目失败",
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
    "deliverables.emptyPolished": "润色稿为空",
    "deliverables.frameNoDesc": "（暂无图片描述，待 VLM 接入后生成）"
  },
  en: {
    "lang.zh": "中文",
    "lang.en": "English",
    "home.title": "Projects",
    "shell.controlPlane": "Control Plane",
    "home.subtitle": "VideoSieve projects saved in SQLite.",
    "home.newProject": "New Project",
    "home.systemSettings": "System Settings",
    "home.cookieVault": "Cookie Vault",
    "home.cookieHint": "Private videos may require site cookies. Manage them in Cookie Vault.",
    "home.empty": "No projects yet.",
    "home.projectListLoadFailed": "Could not load projects from the server; showing the old browser cache.",
    "home.createFirst": "Create your first project",
    "home.newProjectTitlePrefix": "New Project",
    "setup.title": "Initial Setup",
    "setup.checking": "Checking setup status...",
    "setup.stepProviders": "Processing services",
    "setup.providerTitle": "Configure processing services",
    "setup.providerDesc": "Add speech recognition and frame-summary profiles first. Credentials are write-only and stored encrypted.",
    "setup.finish": "Start using VideoSieve",
    "setup.apiUnavailable": "Cannot reach the VideoSieve API. Start the API and try again.",
    "setup.retry": "Check again",
    "setup.profileRequirement": "Add at least one ASR profile and one frame-summary profile with a saved API key. Defaults are used for new jobs; the CapsWriter token is optional.",
    "setup.ready": "The required profiles are ready. You can run a real connection test before continuing.",
    "setup.missingProfiles": "Add an ASR profile and save an API key for at least one frame-summary profile.",
    "setup.savedNotVerified": "Saved and verified are separate states. Use Test connection for a real minimal request.",
    "setup.summaryOptional": "The overall-summary profile is optional and can be added later in System Settings.",
    "setup.summaryEnable": "Configure the overall summary service now",
    "setup.asrEndpointRequired": "Enter the CapsWriter WebSocket endpoint.",
    "setup.vlmBaseUrlRequired": "Enter the vision model API endpoint.",
    "setup.vlmModelRequired": "Enter the vision model name.",
    "setup.vlmApiKeyRequired": "Enter the vision model API key or keep the existing key.",
    "setup.summaryBaseUrlRequired": "Enter the summary model API endpoint.",
    "setup.summaryModelRequired": "Enter the summary model name.",
    "setup.summaryApiKeyRequired": "Enter the summary model API key or keep the existing key.",
    "settings.title": "System Settings",
    "settings.desc": "Configure external processing services for this deployment.",
    "settings.back": "Back",
    "settings.save": "Save Settings",
    "settings.saved": "Settings saved.",
    "settings.load": "Loading settings...",
    "settings.asrSection": "Speech Recognition (ASR)",
    "settings.asrDescription": "VideoSieve adapts external ASR services and does not download or run speech models.",
    "settings.asrProvider": "Provider",
    "settings.asrProviderUnconfigured": "Not configured",
    "settings.asrProviderCapsWriter": "CapsWriter (WS)",
    "settings.asrEndpoint": "Service endpoint",
    "settings.asrWebSocketHint": "Uses the official CapsWriter WebSocket protocol.",
    "settings.asrEndpointRequired": "A service endpoint is required when CapsWriter is selected.",
    "settings.asrLanguage": "Language (auto for detection)",
    "settings.asrTimeout": "Timeout (seconds)",
    "settings.asrContext": "Recognition context (optional)",
    "settings.asrTokenHint": "The token is optional and only needed when the CapsWriter service requires authentication.",
    "settings.asrTokenConfigured": "A token is currently configured.",
    "settings.asrTokenNotConfigured": "No token is configured; upstream CapsWriter works without one.",
    "settings.asrToken": "CapsWriter token",
    "settings.asrUnconfiguredHint": "Jobs fail explicitly and ask for ASR configuration while no provider is selected.",
    "settings.vlmSection": "Vision Language Model (VLM)",
    "settings.vlmBaseUrl": "API Endpoint",
    "settings.vlmModel": "Model Name",
    "settings.vlmApiKeyHint": "The API key is stored encrypted and is never shown again.",
    "settings.vlmApiKey": "Vision model API key",
    "settings.vlmPromptZh": "Frame Prompt (Chinese)",
    "settings.vlmPromptEn": "Frame Prompt (English)",
    "settings.vlmPromptReset": "Reset to default",
    "settings.vlmConcurrency": "Max Concurrent Requests",
    "settings.vlmRpm": "Requests per Minute (RPM, 0 = unlimited)",
    "settings.summarySection": "Overall Summary Model (LLM)",
    "settings.summaryBaseUrl": "API Endpoint",
    "settings.summaryModel": "Model Name",
    "settings.summaryApiKeyHint": "The API key is stored encrypted and is never shown again.",
    "settings.summaryApiKey": "Summary model API key",
    "settings.credentialConfigured": "Configured",
    "settings.credentialNotConfigured": "Not configured",
    "settings.credentialPlaceholder": "Leave blank to keep the current credential",
    "settings.credentialKeepHint": "Enter a new value to replace the saved credential; leave blank to keep it.",
    "settings.clearCredential": "Clear saved credential",
    "settings.clearCredentialMarked": "This credential will be cleared when you save settings.",
    "settings.connectionNotVerified": "Saving does not verify connectivity; confirm the service with a real job.",
    "settings.summaryPromptZh": "Overall Summary Prompt (Chinese)",
    "settings.summaryPromptEn": "Overall Summary Prompt (English)",
    "settings.summaryMaxInputChars": "Maximum input characters per request",
    "settings.processingTitle": "Processing parameters",
    "settings.processingDescription": "Tune concurrency, rate limits, and prompts. Manage endpoints, protocols, models, and credentials in the profiles above.",
    "providers.sectionTitle": "Provider profiles",
    "providers.sectionDescription": "Save multiple service profiles, choose a default for each capability, and verify them with real minimal requests.",
    "providers.capabilityAsr": "Speech Recognition (ASR)",
    "providers.capabilityFrame": "Frame Summary (VLM)",
    "providers.capabilityOverall": "Overall Summary (LLM, optional)",
    "providers.asrDescription": "Audio transcription service. VideoSieve does not bundle or download an ASR model.",
    "providers.frameDescription": "Per-frame understanding requires a model with image input.",
    "providers.overallDescription": "Produces a complete summary from the transcript and frame descriptions.",
    "providers.capswriterAvailable": "Available: CapsWriter (WebSocket), compatible with upstream no-auth servers and optional Bearer tokens.",
    "providers.aliyunPlanned": "Reserved: Alibaba Cloud Model Studio (HTTP, planned). This version will not create an unusable profile.",
    "providers.aliyunOption": "Alibaba Cloud Model Studio (HTTP, planned)",
    "providers.add": "Add profile",
    "providers.empty": "No profiles yet.",
    "providers.default": "default",
    "providers.credentialConfigured": "credential saved",
    "providers.credentialOptional": "token optional",
    "providers.credentialMissing": "credential missing",
    "providers.setDefault": "Set default",
    "providers.test": "Test connection",
    "providers.testing": "Sending a real test request...",
    "providers.testSucceeded": "Test succeeded in {latency} ms.",
    "providers.testFailed": "Test failed.",
    "providers.edit": "Edit",
    "providers.delete": "Delete",
    "providers.addTitle": "Add provider profile",
    "providers.editTitle": "Edit provider profile",
    "providers.displayName": "Profile name",
    "providers.template": "API template",
    "providers.custom": "Custom compatible endpoint",
    "providers.protocol": "API protocol",
    "providers.serviceUrl": "WebSocket service URL",
    "providers.apiRoot": "API root",
    "providers.apiRootHint": "Enter the API root, usually ending in /v1. Do not include /chat/completions, /responses, or /messages.",
    "providers.capswriterUrlHint": "Enter a ws:// or wss:// URL. Upstream CapsWriter does not require a token by default.",
    "providers.model": "Model ID",
    "providers.credential": "API key / token",
    "providers.credentialNotSaved": "not saved",
    "providers.keepCredential": "Leave blank to keep the current credential",
    "providers.optionalCredential": "Optional; upstream CapsWriter works without it",
    "providers.credentialHint": "Credentials are encrypted and never displayed again. Saving does not mean the connection was verified.",
    "providers.useDefault": "Use as the default for this capability",
    "providers.required": "Enter a profile name and service URL.",
    "providers.modelRequired": "Enter a model ID.",
    "providers.saveFailed": "Failed to save provider profile.",
    "providers.deleteFailed": "Failed to delete provider profile.",
    "providers.confirmDelete": "Delete profile “{name}”? Existing job snapshots are not changed.",
    "project.newJob": "New Job",
    "project.cookie": "Cookie",
    "project.cookieNone": "Do not use cookie",
    "project.cookieHint": "Some videos may require a site cookie. Choose one when needed.",
    "project.cookieUnavailable": "Cookie list unavailable. Continuing in no-cookie mode.",
    "project.cookieDefaultSuffix": " [default]",
    "project.summary": "Enable summary generation",
    "project.asrProfile": "ASR profile",
    "project.frameProfile": "Frame-summary profile",
    "project.overallProfile": "Overall-summary profile",
    "project.profileMissing": "No available profile",
    "project.profileOptional": "Not configured (optional)",
    "project.profileDefaultSuffix": " [default]",
    "project.profileLoadFailed": "Could not load provider profiles. Refresh or check System Settings.",
    "project.profileRequiredHint": "Add ASR and frame-summary profiles in System Settings before starting a job.",
    "project.start": "Start Download & Process",
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
    "project.rename": "Edit project name",
    "project.renamePlaceholder": "Enter a project name",
    "project.renameRequired": "Project name cannot be empty.",
    "project.renameFailed": "Failed to save the project name. Please try again.",
    "cookie.title": "Cookie Vault",
    "cookie.back": "Back to Projects",
    "cookie.desc": "Manage site cookies by id. Cookie plaintext is never shown after submit.",
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
    "cookie.statusUnknown": "Not validated",
    "cookie.statusValid": "Valid",
    "cookie.statusExpired": "Expired",
    "cookie.statusInvalid": "Invalid",
    "cookie.defaultUpdated": "Default cookie updated.",
    "cookie.setAsDefault": "Set as default cookie",
    "cookie.lastValidated": "last_validated_at",
    "cookie.validateSourceLabel": "Validate Source URL",
    "cookie.validateSourcePlaceholder": "https://www.bilibili.com/video/BV...",
    "cookie.validateSourceRequired": "Please enter a concrete video page URL before validating.",
    "ingest.probe": "Probe",
    "ingest.probing": "Probing...",
    "ingest.sourceUrl": "Source URL",
    "ingest.noCookieHint": "Public videos can be probed without a cookie; login, membership, or high-bitrate formats may be unavailable.",
    "ingest.availableFormats": "Available formats ({count})",
    "ingest.analysis": "Analysis Asset",
    "ingest.analysisHint": "Recommended: low-resolution AVC for fast analysis",
    "ingest.quality": "Quality Asset",
    "ingest.qualityHint": "Final output quality — choose highest resolution desired",
    "ingest.video": "Video",
    "ingest.audio": "Audio",
    "ingest.auto": "Auto",
    "ingest.duplicate": "Analysis and quality assets have identical configuration — the download will be reused.",
    "ingest.networkVideo": "Online Video",
    "ingest.localUpload": "Local Upload",
    "ingest.chooseVideo": "Choose Video File",
    "ingest.selectedFile": "Selected",
    "ingest.context": "Background Context",
    "ingest.optional": "(optional)",
    "ingest.contextPlaceholder": "Paste a video description, comments, or other background material...",
    "ingest.contextHint": "Adds context that cannot be fetched automatically for a local video, such as its description or comments.",
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
    "job.closePreview": "Close preview",
    "job.previousImage": "Previous image",
    "job.nextImage": "Next image",
    "job.downloadImage": "Download image",
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
    "common.dismiss": "Dismiss notification",
    "error.createProject": "Failed to create project",
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
    "deliverables.emptyPolished": "Polished notes are empty",
    "deliverables.frameNoDesc": "(No description yet — will be generated once VLM is connected)"
  }
};
