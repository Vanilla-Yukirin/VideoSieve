# yukirin-server 部署记录与运维

状态：2026-09-29 在 yukirin-server 的 `vanilla` 用户下实际部署。本文中的地址是当天核实的
Tailscale 地址；变更网络或服务前重新核对。VideoSieve 本体运行在该主机，ASR、视觉模型和
全文摘要仍是外部 Provider 调用，不随应用一起安装模型。

## 当前入口和边界

- Web：`http://yukirin-server.tailb05ab0.ts.net:3847/`
- API 与任务 WebSocket：`http://yukirin-server.tailb05ab0.ts.net:8847/`、
  `ws://yukirin-server.tailb05ab0.ts.net:8847/ws/jobs/{job_id}`
- Web 与 API 仅监听该主机的 Tailscale IP；worker 不监听网络端口。只有受信任的 tailnet
  成员可访问。产品没有登录，任何能访问 API 的程序均可操作项目、配置和 Cookie Vault。
- 同一 tailnet 的 Agent 可读私有 API 的 `/openapi.json` 获取当前接口契约，再通过 API
  创建项目和作业；不要把该入口交给不受信任的 Agent。
- 当前不是 Tailscale Serve HTTPS：`vanilla` 无权修改主机既有 Serve 配置。不要为了接入
  VideoSieve 重置已有 Gitea 等入口，也不要把服务改绑 `0.0.0.0`。

## 文件和进程

- 应用：`/home/vanilla/services/videosieve/app`，本次从 Git 提交导出，不含 `.git`；
- SQLite 与工作区：`/home/vanilla/services/videosieve/data/infra.db` 和 `data/workspaces/`；
- 私有启动配置：`app/.env.local`，权限 `0600`，其中的 `APP_SECRET_KEY` 与原 Windows
  数据库匹配，**必须与数据库一起备份**，不能提交或写进归档；
- 版本化 user systemd 单元：仓库的 `deploy/systemd/videosieve-{api,worker,web}.service`；
  服务器安装于 `~/.config/systemd/user/`。`loginctl` 已启用该用户的 linger；
- 服务器的 `videosieve-api.service.d/tailnet.conf` 和
  `videosieve-web.service.d/tailnet.conf` 仅覆写 `VIDEOSIEVE_BIND_HOST` 为当天的
  Tailscale IP。默认单元仍绑定回环地址，防止误部署到公网或普通 LAN。

API 和 worker 必须指向同一绝对 `VIDEOSIEVE_API_DATA_DIR`。Web 构建时
`NEXT_PUBLIC_API_ORIGIN` 是浏览器可访问的 Tailscale API 地址；
`VIDEOSIEVE_INTERNAL_API_ORIGIN` 是 Next.js `/api/*` 重写使用的服务器内地址。
API 只绑定 Tailscale IP 时，内部地址也必须指向该 IP，不能写 `127.0.0.1`。
修改公开 API 地址后必须重建 Web 再重启。

```bash
systemctl --user status videosieve-api videosieve-worker videosieve-web
journalctl --user -u videosieve-api -u videosieve-worker -u videosieve-web -n 100 --no-pager
curl --noproxy '*' http://yukirin-server.tailb05ab0.ts.net:8847/healthz
curl --noproxy '*' http://yukirin-server.tailb05ab0.ts.net:3847/api/projects
```

`/healthz` 只证明 API 进程活着。还应核对三个 unit、网页代理、WebSocket 快照、Provider
最小请求和真实作业。2026-09-29 迁移后，视觉和全文摘要 Provider 测试成功；服务器的
CapsWriter WS 原本对无 Token 握手返回 401。已在**服务器迁移副本**中把默认 ASR
配置指向该主机 `ws://127.0.0.1:6016`，并从现有 CapsWriter 私有环境文件读取 Token，
通过网页设置 API 加密保存；草稿及已保存配置的握手测试均成功。Token 未进入代码、
日志或此文档。本机旧数据库未随之改写。

真实作业验收使用迁移来的 104 秒视频创建独立的“部署验收 2026-09-29”项目
`p_c2fd31bb1f78`、作业 `j_0a4fd82328f5`。worker 实际领取并完成，产生 10 条 ASR
片段、1 张关键帧及画面描述、模型全文摘要；`deliverables.ready.json` 的 `ready=true`，
3 项最终产物的大小和 SHA-256 已逐项核验，Web 代理与 API 直连都能下载摘要。

## 升级和备份

升级前确认无运行中任务；停止 worker 后对 SQLite 使用 backup API 生成一致快照，并保留
对应工作区及 `APP_SECRET_KEY`。不要只复制 SQLite 主文件而遗漏 WAL。新版本先在独立
目录构建，再按 API、worker、Web 的顺序切换并复验；不要同时运行两个 worker 领取
同一数据库。Windows 原件作为迁移前副本保留，但迁移后的新增任务只在服务器数据中，
两端不能当作自动同步的同一库。

长期安装可改为 Docker Compose：API 和 worker 可使用同一 Python 镜像、不同命令，Web
使用独立 Node 镜像，三者共享**主机本地磁盘**上的数据卷和启动密钥，不引入 Redis。
容器化要先固定端口、Tailscale 私网入口、持久化卷、健康检查及停止旧 worker 的切换
流程；仅换成容器并不能代替真实 Provider 和作业验收。
