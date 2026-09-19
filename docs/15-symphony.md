# Symphony 本地安装

Symphony 在独立 Docker 容器中运行，读取 GitHub Issues，使用 Codex 执行任务。它是开发工具，不是 Spring Boot 业务服务，也不改变入库系统的单服务边界。

## 当前配置

- 官方稳定版 v0.0.3；Linux x86_64 发行包已按官方 SHA256 校验。
- Codex CLI 0.154.0；镜像 `innovation-symphony:0.0.3`。
- 审批策略使用当前 App Server 支持的 `granular`，五类审批字段均设为 false，保留拒绝越权的含义；不要直接复制上游示例中的 `reject` 对象，该 CLI 会以 unknown variant 拒绝创建会话。
- 工作流模板使用 ASCII；v0.0.3 的换行解析使用未启用 Unicode 的正则，可能拆断中文 UTF-8 字节，导致 Jason.EncodeError。中文 Issue 正文在模板解析后注入，进展说明仍要求中文。App Server 握手等待为 60 秒，适应本机首次会话初始化。
- 看板仓库 `dailiuyi/innovation`；配置见 [WORKFLOW.md](../WORKFLOW.md)。
- 一次运行一个任务，只领取带 `symphony:ready` 标签的 open Issue。
- 管理页面绑定宿主机回环地址 `http://127.0.0.1:43190/`。
- 安装文件、日志和独立工作区位于忽略目录 `.local/symphony/`，不会进入公开仓库。
- 默认交付 draft PR，等待独立审查；不自动合并或部署。

容器采用非 root 用户、移除所有宿主 capabilities 并启用 no-new-privileges。[seccomp 配置](../deploy/symphony-seccomp.json) 基于 [Docker 官方默认配置](https://github.com/moby/profiles/blob/main/seccomp/default.json)（源文件 blob：77df9d19e844f4403e41e401aca25ab28861e317，保留 [Apache-2.0 许可证](../deploy/symphony-seccomp.LICENSE)），本项目补充允许 clone、unshare、mount、umount2、pivot_root、setns、chroot、mount_setattr，以便 Codex 的 bubblewrap 在容器内建立用户命名空间与文件系统沙箱。其余默认系统调用限制保留；不使用 privileged、seccomp=unconfined 或 danger-full-access。该放行增加容器可用的命名空间调用面，适用范围仅此开发容器，用户已明确授权其在持有凭据的容器中持续使用。

## 操作

在仓库根目录用 PowerShell 运行：

```powershell
./scripts/symphony.ps1 Status
./scripts/symphony.ps1 Logs
./scripts/symphony.ps1 Stop
```

首次安装的镜像与 `.local/symphony/smoke.md` 已准备好。无凭据、无任务的运行方式：

```powershell
./scripts/symphony.ps1 StartOffline
```

已存在同名容器时不覆盖。切换模式先停止并删除该容器，再启动；独立工作区和日志保留在 `.local/symphony/data/`。不要删除该目录，也不要操作日常 Demo 容器。

```powershell
./scripts/symphony.ps1 Stop
docker rm innovation-symphony
./scripts/symphony.ps1 Start -UseHostCredentials
```

`-UseHostCredentials` 明确授权将当前 GitHub CLI Token 交给 Symphony，以及把宿主机 Codex `auth.json` 只读挂载到容器。它不会把凭据写进仓库或命令参数，但 Docker 管理员仍能读取容器环境。不要导出完整 `docker inspect` 输出。不挂载整个用户目录、Docker socket、日常数据库或项目原工作区。

GitHub Token 不传给 Codex 子进程；Agent 通过 Symphony 的 `github_api` 工具操作指定仓库。仓库范围在工作流中约束，Token 本身的权限仍由 GitHub 授权决定。可在后续改用仅授权此仓库的凭据。

宿主机 Codex 登录刷新后通常会映射到容器；若只读登录文件导致刷新失败，停止任务并重新登录、重建容器。不要把 Token 或登录文件提交到 GitHub。

## 领取与交付

1. 创建 Issue，写明目标、边界、验收和必要背景。
2. 加上 `symphony:ready`，即表示允许 Agent 在隔离工作区执行该任务。
3. Agent 完成后保存代码与证据、创建 draft PR，添加 `symphony:review` 并移除 ready 标签。
4. 需要返工时写明反馈，再添加 ready 标签。审查、合并和部署仍由负责人决定。
5. 缺少环境或需求时标记 `symphony:blocked` 并移除 ready；解决后再入队。

GitHub Issues 的 open/closed 是调度状态，标签用于领取和人工审查。这里不依赖 GitHub Projects 的自定义状态列。

## 验收限制

容器提供 Git、Node、Python 和 Codex。每个工作区自行创建 Python venv 并安装仓库验证依赖；前端任务按需执行 `npm ci`。

当前 [ingestion profile](13-harness.md) 依赖 Windows、PostgreSQL 17、JDK 21、Edge 和 `.local` 环境。容器不能据此声明入库端到端验收通过；相关任务必须返回宿主机完成隔离验收后才能接受。

管理页面 HTTP 200 只证明服务启动；Codex 登录状态不证明模型请求成功；二者都不等同于真实 Issue 到 PR 的验收。当前安装结果见 [验证记录](06-validation.md)。

## 安装来源与恢复

官方发行包：[Symphony v0.0.3](https://github.com/openai/symphony/releases/tag/v0.0.3)。本机安装配方保存在 `.local/symphony/Dockerfile`，官方源码在 `.local/symphony/source/`，下载文件在 `.local/symphony/downloads/`。这是一份本机安装，新的机器需要重新准备运行镜像和登录，不能仅 clone 仓库就直接启动。

停止 Symphony 不停止日常 Demo。容器重启策略为 `unless-stopped`，Docker 启动后会恢复未手动停止的容器；宿主机休眠或 Docker 停止期间不会领取任务。
