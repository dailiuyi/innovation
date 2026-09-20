# Symphony 本地安装

新增 [专项优先与固定审查入口](16-fast-review.md)。Java 执行镜像目标为 `innovation-symphony:0.0.3-java-v2`（JDK 21/Maven）；是否已切换运行容器以当前状态和验证记录为准。Java 变更须先运行实际测试再交付，宿主审查通过后交付同版人工实例。

Symphony 在独立 Docker 容器中运行，读取 GitHub Issues，使用 Codex 执行任务。它是开发工具，不是 Spring Boot 业务服务，也不改变入库系统的单服务边界。

## 当前配置

- 官方稳定版 v0.0.3；Linux x86_64 发行包已按官方 SHA256 校验。
- Codex CLI 0.154.0；基础镜像 `innovation-symphony:0.0.3`，当前执行镜像 `innovation-symphony:0.0.3-java-v2`，包含预装验证依赖、Temurin 21.0.9 和 Maven 3.9.11。
- 审批策略使用当前 App Server 支持的 `granular`，五类审批字段均设为 false，保留拒绝越权的含义；不要直接复制上游示例中的 `reject` 对象，该 CLI 会以 unknown variant 拒绝创建会话。
- 工作流模板使用 ASCII；v0.0.3 的换行解析使用未启用 Unicode 的正则，可能拆断中文 UTF-8 字节，导致 Jason.EncodeError。中文 Issue 正文在模板解析后注入，进展说明仍要求中文。App Server 握手等待为 60 秒，适应本机首次会话初始化。
- 看板仓库 `dailiuyi/innovation`；配置见 [WORKFLOW.md](../WORKFLOW.md)。
- 最多同时运行 4 个任务，各自使用独立工作区；只领取带 `symphony:ready` 标签的 open Issue。
- 管理页面绑定宿主机回环地址 `http://127.0.0.1:43190/`。
- 安装文件、日志和独立工作区位于忽略目录 `.local/symphony/`，不会进入公开仓库。
- 默认交付 draft PR，等待独立审查；不自动合并或部署。
- 模型与思考深度由 Issue 标签传给独立 stdio 适配器，缺省为 `gpt-6-astra / low`；每次调度校验当前 Codex 模型目录。

容器采用非 root 用户、移除所有宿主 capabilities 并启用 no-new-privileges。[seccomp 配置](../deploy/symphony-seccomp.json) 基于 [Docker 官方默认配置](https://github.com/moby/profiles/blob/main/seccomp/default.json)（源文件 blob：77df9d19e844f4403e41e401aca25ab28861e317，保留 [Apache-2.0 许可证](../deploy/symphony-seccomp.LICENSE)），本项目补充允许 clone、unshare、mount、umount2、pivot_root、setns、chroot、mount_setattr，以便 Codex 的 bubblewrap 在容器内建立用户命名空间与文件系统沙箱。其余默认系统调用限制保留；不使用 privileged、seccomp=unconfined 或 danger-full-access。该放行增加容器可用的命名空间调用面，适用范围仅此开发容器，用户已明确授权其在持有凭据的容器中持续使用。

## 操作

### 实时会话详情（只读）

在另一个终端运行 `python scripts/symphony_viewer.py`，打开 `http://127.0.0.1:43191/`。
页面每两秒读取独立 Codex 会话日志，可切换会话、搜索已加载记录、展开工具调用及返回结果、跟随最新记录和暂停刷新。
页面暂停只影响显示，不暂停 Agent。历史记录分批加载；调度状态单独读取 43190 的只读接口，调度离线时仍可浏览日志。
服务仅绑定本机回环地址，不提供控制任务或修改文件的接口，也不需要重启 Symphony。
工具输出以日志实际保存的内容为准，已截断内容无法还原；不展示模型内部推理。
终端关闭或按 Ctrl+C 即停止详情服务；下次需要时重新运行上述命令。会话日志不会删除。

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

## 模型与思考深度

准备 Issue 的 Agent 先运行以下命令读取当前容器账号可用的 GPT 模型及各自支持的思考深度，按用户明确选择或任务复杂度选定组合，在正文写一句选择理由，并校验后设置标签。选择流程发生在需求准备阶段，Symphony 执行阶段不再调用模型评估器。

```powershell
./scripts/symphony.ps1 Models
./scripts/symphony.ps1 ValidateModel -Model gpt-6-astra -Effort low
```

简单文案、样式和局部修改优先轻量模型及低深度；常规交互和接口任务使用均衡组合；权限、迁移、并发及复杂重构提高能力与思考深度。实际候选以目录为准，不维护另一份静态可用模型清单。目录暂时不可读时先记录默认组合，等执行前校验通过再入队，不猜测替代模型。

标签格式（严格按下列小写前缀）：

- `symphony:model:gpt-6-astra`
- `symphony:effort:low`

用户明确指定优先于 Agent 判断。每种前缀最多一个标签；变更时替换旧标签，不叠加。缺少模型标签时使用 `gpt-6-astra`，缺少深度标签时使用 `low`。重复、空值、未知或非 GPT 模型、不支持的深度均阻止推理调用，不静默回退。正文中的模型示例不是配置。确认目标、验收与组合后，最后添加 `symphony:ready`；该文档不授权自行创建或修改远端任务。

适配器只解析工作流开头的 `SYMPHONY_ROUTING_V1` 元数据区；标识符和每个标签由 Solid `url_encode` 编码。它在 App Server 初始化后读取完整分页 `model/list`，首轮解析并校验标签，将 `model` 和 `effort` 写入每次 `turn/start`。同一会话的后续轮次固定复用组合，修改标签要到下一次调度才生效。目录失败或 30 秒内未完成读取会明确失败，沿用 Symphony 自身退避，不增加自动换模型重试。

`scripts/symphony_codex_adapter.py` 和查询脚本通过独立只读挂载运行在 `/opt/symphony-routing/`；任务工作区中的同名文件不参与执行。协议输出只走 stdout，结构化审计追加到 `.local/symphony/data/logs/model-routing.jsonl`，记录 Issue、线程、请求组合、默认来源、接受/拒绝和完成状态，不写提示正文或凭据。`turn_accepted` 只证明请求被接受；实际模型/深度应核对对应 Codex rollout 的 `turn_context`，实际业务完成仍需任务验收。

### 路由验证与恢复

quick profile 包含无网络、无凭据的假 App Server 协议测试；Linux 另验证 SIGTERM 后子进程树清理。真实短请求可在独立 home/工作区的同版本容器中运行 `symphony_model_probe.py smoke --output <证据路径>`；无标签验证默认组合，加 `--model` 和 `--effort` 验证显式组合。脚本核对真实 rollout 的模型和深度，不能仅凭回复文本判断通过。`catalog` 与 `validate` 子命令只查询目录，不发起推理请求。

首次从旧版本接入需在 running/retrying 均为 0 且 ready 队列为空时重建 Symphony 容器以增加挂载；以后只读挂载的脚本更新只影响新进程。保留旧容器、原工作流及 data，不操作 Demo/LAN Compose。

2026-09-19 本机回退点：旧容器 `innovation-symphony-before-routing`（已停止），原工作流与启动脚本在 `.local/symphony/routing-validation/rollback/`。回退时先确认空队列，停止新容器并改名保留，将备份工作流恢复到根目录，再将旧容器改回 `innovation-symphony` 并启动，检查 43190 健康。旧容器绑定根目录工作流，所以必须先恢复工作流；两个容器不能同时运行。不要删除 data，也不要直接用备份目录里的启动脚本启动（其相对路径以 scripts 目录为基础）。

## 验收限制

容器提供 Git、Node、Python、Codex、JDK 21 和 Maven。Java 依赖使用任务自己的 `.local/m2`，首次下载仍有冷启动成本；禁止用“镜像有 Java”代替实际执行测试。Python 验证依赖预装在镜像的只读 venv 中，各任务仍拥有自己的轻量 venv；前端任务按需执行 `npm ci --prefer-offline --no-audit --no-fund`，node_modules 不共享。

当前 [ingestion profile](13-harness.md) 依赖 Windows、PostgreSQL 17、JDK 21、Edge 和 `.local` 环境。容器不能据此声明入库端到端验收通过；相关任务必须返回宿主机完成隔离验收后才能接受。

管理页面 HTTP 200 只证明服务启动；Codex 登录状态不证明模型请求成功；二者都不等同于真实 Issue 到 PR 的验收。当前安装结果见 [验证记录](06-validation.md)。

## 安装来源与恢复

官方发行包：[Symphony v0.0.3](https://github.com/openai/symphony/releases/tag/v0.0.3)。基础镜像配方保存在 `.local/symphony/Dockerfile`，验证依赖扩展配方见 [symphony.Dockerfile](../deploy/symphony.Dockerfile)，官方源码在 `.local/symphony/source/`，下载文件在 `.local/symphony/downloads/`。这是一份本机安装，新的机器需要重新准备基础镜像和登录，不能仅 clone 仓库就直接启动。

### 预装验证依赖与下载缓存

运行 `./scripts/symphony.ps1 Build` 构建验证镜像；只向 Docker 发送配方、`scripts/requirements-review.txt` 和环境准备脚本，不发送仓库、登录或任务日志。基础镜像必须已存在。依赖变更后重新 Build，空闲时切换容器，不重建业务镜像。

2026-09-20 首次接入时 GH-3/GH-4 正在执行，先从已验收的新镜像同步两个新增只读 `/opt` 目录，未中断任务。两个任务结束且 ready 队列、running/retrying 均为空后，正式切换到验证镜像，健康与默认模型校验通过。旧容器 `innovation-symphony-before-cache` 停止保留；工作流备份在 `.local/symphony/environment-validation/rollback/`。回退需先确认空闲，停止新容器并改名保留，再将此旧容器恢复原名称并启动；data 和缓存不删除。

同日完成 Java 镜像切换，直接回退容器为 `innovation-symphony-before-java-v2`（停止保留）；当前容器健康与默认模型校验通过。上游在启动时同步清理已关闭 Issue 的目录，Windows 挂载盘上的大量小文件可使健康接口长时间未开放。GH-7 被部分清理后的剩余目录已保留至 `.local/symphony/data/archived-workspaces/GH-7-20260920-startup-recovery`，停止清理、归档后重启约 6 秒内恢复健康。不要盲目重复启动或直接删除工作区；先核对关闭状态、备份证据并在调度停止时处理。上游自动清理机制本次未修改。

依赖和 pip 安装在 `/opt/symphony-validation/venv`，由 root 所有，任务不可修改；实际安装版本记录在 `/opt/symphony-validation/installed.txt`。每次执行前，`before_run` 创建或检查工作区 `.local/venv`，用 `.pth` 引用镜像依赖，不复制 pip，不再次下载同一依赖。依赖清单与镜像一致时直接使用；清单变化时在任务自己的 venv 中补装，保留镜像和其他任务环境。旧镜像没有准备脚本时保留原安装方式作为过渡，不能把过渡路径当成已启用预装环境。

共享下载缓存随现有 `/data` 挂载持久化：宿主 `.local/symphony/data/cache/pip` 和 `cache/npm` 对应 `/data/cache/pip`、`/data/cache/npm`，通过 `PIP_CACHE_DIR`、`NPM_CONFIG_CACHE` 指定，容器重建后保留。沙箱仅额外放行这两个缓存目录；任务 venv、node_modules 和锁文件仍各自独立。缓存命中减少下载，首次遇到的新包仍需联网，仓库克隆和 npm 解包也仍需执行。

镜像验收在无网络、无凭据的临时容器运行 `python3 -m unittest discover -s /tests -p test_symphony_environment.py -v`，只读挂载 scripts 为 `/tests`，挂载隔离数据目录为 `/data`，使用本仓库 Symphony seccomp 配置。该检查验证离线初始化、任务依赖隔离、缓存路径及 Codex CLI 沙箱可写范围；Windows quick 不替代该 Linux 镜像验收。

停止 Symphony 不停止日常 Demo。容器重启策略为 `unless-stopped`，Docker 启动后会恢复未手动停止的容器；宿主机休眠或 Docker 停止期间不会领取任务。
