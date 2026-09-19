# V0.1 验证记录

## 2026-09-19 Symphony 首个真实任务启动修复

- GH-1 暴露安装冒烟检查未覆盖的 App Server 协议问题：`reject` 审批对象被 Codex CLI 0.154.0 拒绝。根据该二进制导出的 schema 改为 `granular`，五类字段均为 false，保留 workspace-write 与拒绝越权的规则。
- 随后发现工作流换行解析 `~r/\R/` 可能拆断中文 UTF-8 字节，使发送 turn 时出现 Jason.EncodeError；将内部模板改为等义 ASCII，中文任务正文继续由模板变量注入。握手 read_timeout_ms 从默认 5 秒调到 60 秒。
- 只重启 Symphony，保留 GH-1 工作区。2026-09-19T14:17:39Z 状态 API 显示 running、第 1 轮、有效 session_id、总 Token 16686、retry=null、last_error=null，证明实际 Issue 已进入模型执行。
- 此记录只确认真实任务成功启动，不代表首页功能完成、PR 交付或业务验收通过。

## 2026-09-19 Symphony 安装验证

- 官方 Symphony v0.0.3 Linux x86_64 发行包 SHA256 校验通过；运行镜像包含 Codex CLI 0.154.0。仅新建开发工具镜像，未重建业务镜像。
- 无凭据 memory tracker 启动成功，本机 `http://127.0.0.1:43190/` 与 `/api/v1/state` 返回 200，运行、重试与阻塞任务均为 0。
- `python scripts/harness.py doctor --profile quick` 与 `check --profile quick` 通过，检查报告在 `.local/harness/20260919T134505Z-jvxhrkrn/report.json`。此次范围为工作流、脚本和文档集成；未执行 ingestion、浏览器业务验收或数据库迁移。
- 公开发布前扫描可达历史中的 846 个 blob，检查常见凭据格式与当前本地环境配置中的秘密值，未发现匹配；这不构成任意秘密均不存在的保证。
- 用户明确授权复用本机 GitHub 和 Codex 登录后，容器 `codex login status` 确认 ChatGPT 登录，最小模型请求返回 `SYMPHONY_READY`，容器内 GitHub Issues 读取返回 HTTP 200，当前 open 条目为 0。
- 首次实际 shell 检查发现 Docker 默认 seccomp 阻止创建用户命名空间。基于官方默认配置补充 8 个嵌套沙箱所需调用后，无凭据临时容器内 bubblewrap 只读沙箱执行 Python 成功；仍保留非 root、cap-drop ALL 和 no-new-privileges。
- 用户明确授权将该 seccomp 配置应用到持有凭据的常驻容器后，Codex 在 workspace-write 沙箱中通过 shell 实际执行 `python3 -c "print(731942)"`，输出正确且退出码为 0。
- 真实 Issue 到 draft PR 尚未执行。服务启动、登录与最小模型请求不代替真实任务验收。

## 2026-09-18 Docker 内网更新

- 本次 quick doctor/check 与 ingestion profile 通过，164 项隔离 HTTP/Edge 检查通过；PostgreSQL 17.6 路径迁移回归通过。报告位于 `.local/harness/20260918T075547Z-bheby8t8/report.json`，源码指纹 `5f81da05afdf8a7b2686aa5be61ab073927f0c26bab517a05631d7602656a68f`，sourceUnchanged=true。浏览器退出时出现 Playwright CancelledError 回调日志，进程退出码 0，结构化检查全部通过。
- `docker compose --env-file config/compose.env build backend gateway` 成功，Linux Java 21 构建含 17 项测试通过，Vue 生产构建通过。随后执行 `up -d --no-deps backend gateway --wait --wait-timeout 180`，四个服务均 healthy；保留原 PostgreSQL、Redis 与命名卷。
- 后端镜像 ID：`sha256:d70abbab5d9821f95928a919029673d0c6bf8883afbb7cfc044cdcdd30958f3b`；网关镜像 ID：`sha256:90817d9152903894dcc9f2f80933ecf32f1864f29e2b619ca15916f112479f6d`。
- LAN PostgreSQL 的 V012/V013 均成功；升级前数据库备份保存在忽略目录 `.local/deployment-20260918/database.dump`。Nginx 配置检查通过。本机不经代理访问 `http://192.168.0.12:43174/` 返回 200，`/prod-api/captchaImage` 返回 code 200。
- 未重启 Windows Demo，未推送远程仓库。未执行 LAN 账号登录与另一台设备访问验证；系统拒绝读取防火墙端口规则，不能据本机 HTTP 成功宣称跨设备验收通过。

## 2026-09-18 V013 LIKE 通配符与日常库升级

前缀冲突三处改为 `starts_with`，避免路径中的 `_`、`%` 被 LIKE 当成通配符。独立 PostgreSQL 17.6 升级回归通过：`safe/asset_1` 与 `safe/assetA1/data.bin`、`dir%/x.bin` 与 `dirX/y.bin` 均保留。本机 Demo 已执行 V013，Flyway 现为 v013，`/captchaImage` 返回 200。

## 2026-09-18 V013 导出路径迁移修正

V013 未应用于日常 Demo（仍为 V012），因此直接改写未应用的 V013，未增加 V014、未改 Flyway 历史。迁移只保留已有合法相对路径，改写不安全或冲突路径；先删除唯一索引再写回，避免中间态 23505。

- 独立 PostgreSQL 17.6 带旧数据升级 15 项通过，见 [报告](validation-export-path-migration.json)。覆盖嵌套目录保持、不同目录同名、CON.txt、冒号/问号清洗碰撞、已有 `report_2026-22222222.txt` 不被覆盖、file_name 与 storage_key 不变。
- 隔离 ingestion 164 项通过，含浏览器取消后重选同一目录。Harness `.local/harness/20260918T073111Z-wiqycldx/report.json`，源码指纹 `6a99f7c8dd5128ed67f0ca57759553a90ea5cbaeec2d5b4245aadf44ab0842cf`，`sourceUnchanged=true`。
- `python scripts/harness.py doctor --profile quick` 与 `check --profile quick`、`check --profile ingestion` 通过。未操作日常 Demo、未重启日常服务。日常库没有被压平的目录需要恢复。

## 2026-09-18 文件夹上传审查修复

修复五项：启动恢复使用集合创建人并标明 SYSTEM_RECONCILIATION；删除持有草稿写锁；取消后新批次使用新 requestKey；路径前缀冲突按大小写折叠；V013 改写不安全导出路径且不改 V012 历史。

- 隔离 PostgreSQL 17.6、HTTP 与 Edge 验收 164 项通过，见 [报告](validation-ingestion.json)。Harness `.local/harness/20260918T070751Z-mxe5zmb4/report.json`。源码指纹 `1c0a772ae672a8ff14ce875140411bb52779afcd290493f3691c72d6d9cbb7a1`，`sourceUnchanged=true`。
- 新增覆盖：启动时完成未切换替换、系统恢复审计、下载/打包期间删除 409、取消批次键不能重开、大小写前缀冲突、`ar_safe_export_path`、浏览器取消后重选同一目录。
- `python scripts/harness.py doctor --profile quick`、`check --profile quick`、`check --profile frontend`、`check --profile ingestion` 通过。未操作日常 Demo、未重启日常服务。

## 2026-09-18 文件夹上传与双下载

管理员草稿支持选择文件夹替换全部文件，以及 ZIP 整包和完整清单逐文件下载。V012 增加文件集合、相对路径和 ZIP 缓存。发布与所有下载共用完整性门槛：集合非空、无未完成替换/上传/删除、全部 AVAILABLE 且存储校验通过。

- 隔离 PostgreSQL 17.6、HTTP 与 Edge 验收 149 项通过，见 [报告](validation-ingestion.json)。Harness 报告 `.local/harness/20260918T041339Z-fdjg783q/report.json`。HEAD `b2e11821cce03f20400fcb98e04f9e4b82713cd8`，源码指纹 `05d7182833ceb228e36bbdaed1496e9df30957b1b19ceaf899d166eca53f3cf8`（工作区有未提交修改），构建 Jar SHA256 `1a3711e085cf26e840f4af17829461658e7d5f3a14a185052d22fd33c1a543e4`。
- 覆盖：失败文件拒绝发布和下载、路径穿越拒绝、文件夹替换开始/续传/清单变化 409、替换期间禁止发布下载追加、取消后恢复旧集合、切换后旧文件删除、清单还原目录、单文件与 ZIP 的 206/416/HEAD、ZIP 复用、匿名拒绝、浏览器文件夹上传与 ZIP 下载。
- `python scripts/harness.py doctor --profile quick` 与 `check --profile quick`、`check --profile frontend`、`check --profile ingestion` 均通过。契约 57 个操作、358 项设计检查。`RelativePathTest` 3 项、存储测试 13 项。
- 未执行：日常 Demo 迁移/重启、Docker 网关、磁盘写满、物理断电、客户端加载认证。空目录不保留。集合默认 200 个文件 / 500 MiB、ZIP 缓存 24 小时 / 2 GiB 为配置默认值。

## 2026-09-18 Review 默认规则

将独立 Code Review 的范围、缺陷标准、验证边界与输出约定写入 `docs/14-code-review.md`，由 AGENTS 和知识入口链接。简短的“review 当前未提交改动”默认包含暂存、未暂存及相关新增文件；功能名称作为重点，不静默忽略其他改动。默认只审查，具体调查和必要验证由 Agent 决定。

`python scripts/harness.py check --profile quick` 通过，覆盖 Harness 回归、契约一致性及本地文档链接。本轮只更新规则和文档，未执行场景发布功能审查或业务验收，未修改已有业务代码和正式 JSON 报告。

## 2026-09-18 场景发布审查修复

针对发布审查三项：刷新后重取当前草稿以同步 `published`；发布成功后通知场景列表刷新修订号；未发布时列表省略 `published` 字段（不再输出 `null`）。删除文件后的浏览器步骤改为点「刷新」并先等抽屉标题，避免整页重载时 Vite 代理 `/getInfo` 连不上后端导致登出、发布流程未执行。

- `node scripts/verify_draft_panel.mjs` 增加刷新后选中草稿发布状态同步。
- 隔离入库 115 项通过，见 [报告](validation-ingestion.json)：未发布列表无 `published` 字段、发布递增场景修订号、父表修订号更新、删除后刷新仍隐藏已删文件、发布/替换按钮流程跑完。

## 2026-09-17 场景发布指针

同一场景一份当前发布版本：发布后文件冻结、说明可改；替换后原版本回到草稿；当前发布禁止删除。V011 增加 `ar_scene` 发布指针。入口仍是场景编辑 → 版本与文件。

- 隔离 PostgreSQL 17.6、HTTP 与 Edge 验收 113 项通过，见 [报告](validation-ingestion.json)。覆盖空草稿拒绝发布、过期场景版本 409、重复发布幂等、已发布文件冻结、当前发布不能删、说明可改、替换后解冻可删、发布审计、浏览器首次发布/替换确认与取消。
- 契约检查 313 项、48 个操作；草稿面板乱序回归与 Vue 生产构建通过。Maven package 含 12 项存储测试。
- 本机 Demo 已执行 V011 并重启后端；未重建 Docker 网关。客户端加载、预览、单独下线仍未实现。

## 2026-09-17 基础 Harness

新增统一 doctor/check 入口、quick/frontend/ingestion 三种检查范围、独立运行证据和包含未提交修改的源码指纹。AGENTS 改为导航与关键约束，原开发/部署操作移入开发工作流；新增知识索引、决策记录与跨会话任务模板。

- quick：9 个 Harness 回归用例、契约生成源一致性及递归文档链接检查通过。故障用例覆盖命令失败后跳过后续步骤、缺失/失败/空/错误结构的报告、缺失命令、超时、未提交/新增/删除源码的指纹，以及临时副本中故意引入的 OpenAPI 漂移。
- frontend：草稿面板异步乱序回归与 Vue 生产构建通过。首次沙箱执行遇到 Node 读取项目父目录的 EPERM，经授权在沙箱外运行后通过；已将路径访问探测加入预检，不将该环境错误解释成产品故障。
- ingestion：独立后端源码副本 Maven package（含存储测试）、真实 PostgreSQL 17/Redis/Spring Boot/Vite/Edge 的 88 项入库验收通过。验证使用本次构建的 Jar，原日常 Demo Jar 的 SHA256 前后相同。

运行证据按次保存在忽略的 `.local/harness/` 中；没有覆盖已有 `docs/validation-*.json`，没有重启日常 Demo 或操作 LAN Compose。上述结果不证明 Docker Nginx、客户端加载、发布、回滚或生产部署。入口用法和退出码见 [Harness 说明](13-harness.md)。

## 2026-09-17 未提交修改审查与小修复

逐项检查草稿接口鉴权、数据库约束、上传校验、物理删除及启动恢复，并核对前端请求与文档。修正草稿选择、文件列表和草稿分页的旧响应覆盖新状态问题，拒绝在当前场景下展示其他场景的草稿；同步修正 README 与本机运行手册的 Vite/Compose 入口及启动命令。

- `node scripts/verify_draft_panel.mjs` 通过：模拟请求乱序，覆盖草稿选择、文件响应、草稿列表响应、场景归属和关闭后迟到响应。
- `npm --prefix frontend run build:prod` 通过。

本次未重跑隔离后端/浏览器全链路，未重启 Demo 或重建 Docker；下列历史验收记录不作为本次全链路验证结果。

## 2026-09-17 草稿整份删除验收

草稿列表增加删除入口，确认后永久删除草稿行及其全部实际文件。V010 去掉文件删除回执对草稿行的外键。隔离 PostgreSQL 17.6、HTTP 与 Edge 验收 88 项通过，见 [报告](validation-ingestion.json)。覆盖空草稿、含文件草稿、取消确认、上传中拒绝、匿名/非管理员拒绝、重复删除 204，以及文件物理消失。Maven package 与契约检查通过。未重建 Docker 网关。

## 2026-09-17 草稿文件物理删除验收（后续需求）

运行环境更新后，V009 迁移通过、4 个 Docker 服务健康。按用户明确授权清理此前已逻辑移除的 5 个文件，共 31,450,659 字节：逐 UUID 核对 `.bin`/`.part`/`.ready` 均不存在、草稿文件行均删除，5 条完成回执和5条成功审计保留。清理仅限事先记录的5个ID，其他文件摘要核对不变；零字节互斥锁保留。精确 ID 与执行证据存于忽略目录 `.local/physical-deletion-cleanup-*.json`。

按用户后续要求，将上一节所述逻辑移除改为物理删除：删除 UUID 对应的临时/正式文件和 `ar_draft_file` 行，保留审计及 `ar_file_deletion` 幂等回执。原先“不做正式文件物理删除”的边界在草稿文件范围内被本次要求替代。

- 隔离 PostgreSQL 17.6、HTTP 与 Edge 验收 73 项通过，见 [报告](validation-ingestion.json)。新增验证实际文件/数据库行均消失、存储删除失败返回503并可重试、旧登记键无法恢复、删除前/磁盘删除后两种持久状态下的启动恢复、历史逻辑移除不自动清理、明确指定旧记录时可以物理删除，以及浏览器确认/取消与重新上传。
- 存储单元测试 12 项通过，其中新增仅删除指定 UUID 的 `.part`/`.ready`/`.bin`、其他文件保留、非普通文件路径及并发锁拒绝删除、重复删除安全。Maven package 通过。
- OpenAPI 生成与检查通过：276 项检查、46 个接口操作。

删除恢复测试在隔离目录注入两种中断后的持久状态；不声称已经验证物理断电和磁盘硬件故障。

## 2026-09-17 草稿文件移除验收

新增 V008 逻辑移除迁移、管理员 DELETE 接口、文件行“移除”按钮和确认框。正式文件与历史元数据保留，不执行物理删除。隔离 PostgreSQL 17.6、HTTP 和 Edge 浏览器入库验收共 65 项通过，包含取消/确认、刷新后保持移除、重新添加、上传中拒绝移除、旧幂等键不能恢复、重启不会恢复、匿名/非管理员拒绝与审计只记一次；详见 [当前验收报告](validation-ingestion.json)。Maven package 和 Docker 前端构建通过；契约检查 275 项、46 个操作通过。

## 2026-09-17 资源入库闭环验收

本轮新增场景下的版本草稿、多个文件登记与上传、大小/SHA256 校验、失败重试、重启对账和后台文件明细。实现边界见 [资源入库说明](12-resource-ingestion.md)，完整证据见 [入库验收报告](validation-ingestion.json)。

- `scripts/verify_ingestion.py`：47 项通过。使用新建私有目录和随机回环端口的 PostgreSQL 17.6、Redis、Spring Boot、Vite、Edge，不修改现有 Demo。覆盖双文件与刷新持久化、正式文件读取校验、大小/摘要错误、请求幂等与并发、真实网络中断、上传中强制终止后重启、`.ready`/已正式落盘但数据库未确认的恢复、匿名/非管理员鉴权及操作审计。浏览器另验证跨 2 MiB 分块的 SHA256、失败原因和重试入口。
- Maven 完整 `package` 成功，`LocalArtifactStorageTest` 10 项通过；Vue 生产构建通过。
- `scripts/generate_contracts.py` 与 `scripts/verify_design.py` 通过；OpenAPI 0.3.0 区分本轮已实现草稿入库接口与历史候选发布接口。

本轮 Docker 引擎不可用，未对修改后的 Nginx 上传转发路径执行容器验收；本轮结果不替代 9 月 16 日容器验收，也不证明物理断电、磁盘写满、真实 Addressables 加载或生产部署。下文保留各阶段的历史结果，涉及“尚未实现上传”的描述指当时状态。

## 2026-09-17 通用资源传输参考框架

运行 `python scripts/test_artifact_transfer.py`，15 项隔离测试通过。使用临时合成二进制文件和回环 HTTP 服务，覆盖整文件下载、缓存复用、真实连接中断后的续传、强 ETag 变化时从头下载、缺失/弱 ETag 与损坏检查点、Content-Range 异常、HEAD/206/416、503 保留部分文件、错误摘要拒绝交付、完整部分文件恢复、已有目标保护及同目标写入锁。

打包格式尚未确定，只有 `PackageCodec` 扩展接口，没有 ZIP 或其他打包/解包实现。测试不涉及真实 AR 包、手机 SDK、生产 Nginx、Spring Boot 下载接口、上传续传或并发容量。既有服务和数据库未修改。边界与运行方式见 [资源传输框架](11-artifact-transfer-reference.md)。

## 2026-09-17 账号删除验收

在 `innovation-infra-check` 隔离容器内执行 `scripts/verify_account_delete.py`，Edge 无头浏览器与实际接口的 18 项检查全部通过。覆盖删除确认和取消、未登录拒绝、禁止删除当前账号和最后一个有效管理员、删除后登录及旧凭证失效、禁止启用和重置已删除账号、账号名保留、历史场景审计保留、已停用引导账号删除，以及系统操作日志记录。测试后恢复隔离引导账号并逻辑删除生成的测试账号，没有修改日常环境的账号数据。结果见 [账号删除验证报告](validation-account-delete.json)。前后端镜像构建通过。

## 2026-09-16 场景删除验收

场景列表新增删除按钮和包含场景名称的确认窗口。后端使用 V006 增量迁移增加逻辑删除字段，删除与审计写入处于同一事务。

在 `innovation-infra-check` 隔离容器中执行 `scripts/verify_scene_delete.py`，使用 Edge 无头浏览器与实际 HTTP 接口完成 17 项检查，全部通过。覆盖取消不发请求、取消保留场景、确认只提交一次、未登录拒绝、缺少或过期修订号拒绝、删除后列表与详情隐藏、禁止再次编辑和启用、保留操作人和历史审计，以及并发删除只有一个成功请求。结果见 [场景删除验证报告](validation-scene-delete.json)。本次未运行依赖旧本机测试账号的 `verify_demo.py`，其中已补充删除时审计失败的事务回滚用例，尚待该隔离环境复验。

前端生产构建、后端 Maven 打包及已有 10 项存储单元测试通过。

## 2026-09-16 Docker 与本地存储基础设施验收

本次新增单机 Docker Compose 和本地 `ArtifactStorage` 基础组件，使用 Windows Docker Desktop 的 Linux 引擎完成隔离验收。测试项目固定为 `innovation-infra-check`、入口固定为 `127.0.0.1:18082`，使用独立配置、容器和命名卷，没有连接现有本机 Demo 数据库。详细运行边界见 [基础设施说明](10-local-infrastructure.md)。

- 本地存储单元测试 10 项通过：覆盖暂存与正式文件隔离、大小和 SHA256 校验、配置上限、传输中断清理、服务重启后的遗留暂存识别、重复提交不覆盖、确认阶段崩溃恢复、同长度损坏识别、并发锁及非法路径/非普通文件拒绝。
- Linux 容器内完整 Maven 打包及上述 10 项测试通过，Vue3 生产构建通过，前后端镜像构建成功。宿主机再次完整打包时，所有模块编译与测试通过，最后因本机后端正在使用目标 Jar，Spring Boot 插件无法重命名产物；未停止现有 Demo，也未清理或覆盖其运行产物。
- [基础设施报告](validation-infrastructure.json)记录 24 项通过：只有网关映射宿主端口，数据库与 Redis 位于 internal 网络，Redis 会话数据使用临时文件系统；后端使用 UID 10001；Nginx 配置有效；前端、登录和场景写入可用；现有上传入口仍关闭；暂存、正式文件及内部路径均不能通过网关读取。
- 强制重建四个容器后，隔离库中的合成场景和成品卷中的合成文件及其摘要保持不变。这个结果验证命名卷跨容器重建持久性，不等于备份恢复、断电恢复或跨物理主机迁移。
- 生成契约与设计检查通过，共 225 项、37 个操作；所有资源和发布接口继续标记为“候选：尚未实现”，顶层说明已明确旧云存储/昼夜契约等待真实成品与客户端加载约定。

当前没有真实成品、上传/版本/发布/下载 API、客户端渲染、磁盘写满、断电、物理 Linux 主机迁移或内网多设备测试。`AR_STORAGE_MAX_BYTES` 当前仅为基础设施测试值，不构成产品上传限制。Redis 7.4.5、PostgreSQL 17.6 和应用容器已共同启动验证，但尚未形成生产运维与高可用承诺。

## 2026-09-16 管理后台 Demo 验收

本次使用项目隔离的 Java 21.0.12.1、PostgreSQL 17.6、Redis 3.0.504 和 Microsoft Edge；后端 Spring Boot 3.5.16，前端 Vue3。服务只在本机验证，未部署服务器。

- [框架 HTTP 报告](validation-framework.json)：23 项复验通过，覆盖登录、同权账号、菜单分页、日志日期筛选、接口关闭、最后管理员保护、改密/禁用/退出/过期失效及密码哈希不外泄。首次引导账号创建与自动停用也已在初始验收中通过。
- [场景及数据库报告](validation-demo.json)：18 项通过，包括并发更新冲突、审计操作人、审计失败的业务回滚、审计追加约束和数据校验。
- [浏览器报告](validation-browser.json)：登录、新建、编辑、停用、查看审计与退出全部通过，未捕获页面脚本错误。截图保存在本机 `.local/scenes-browser.png`。
- [初始化报告](validation-initialization.json)：独立空库初始化后再次启动，迁移、账号、菜单、角色及场景数量一致，没有重复灌入。
- [契约报告](validation-contracts.json)：检查通过，37 个操作按已实现/候选区分，管理接口使用 Bearer；生成源、OpenAPI、Schema 与示例一致。准确检查数量以报告为准。
- Java 21 Maven 打包和前端生产构建通过。没有把 Maven 无测试类的构建结果当成业务测试，业务依据上述 HTTP/真实数据库/浏览器检查。

一万条合成场景数据下，单次 `EXPLAIN ANALYZE` 执行时间：列表 0.018 ms、名称筛选 0.458 ms、主键详情 0.007 ms。完整计划见数据库报告。测试数据事务回滚；这是本机查询采样，不是并发压测或端到端响应时间，不用于承诺生产吞吐。

运行环境与命令见 [启动说明](08-demo-runbook.md)，维护差异见 [上游适配记录](09-upstream-adaptation.md)。这一段记录的是管理后台 Demo 当时的状态；后续 Docker 和本地存储基础设施结果见本文上一节。资源上传、版本发布和客户端仍未验收。

## 以下为原云存储与昼夜候选设计的历史记录

## 已完成的检查

[数据库检查报告](validation-database.json)记录了 7 张表和 31 项检查的通过结果，覆盖版本冻结、文件约束、场景及昼夜归属、双连接发布互斥、并发版本冲突、回滚、撤销和审计。

这些检查在独立临时 PostgreSQL 18.4 实例上执行，实例已停止。设计目标为 PostgreSQL 17，仍需在目标版本上复验。

[契约检查报告](validation-contracts.json)记录 OpenAPI、运行清单 Schema 与示例、生成源一致性、Session 和 CSRF 声明、数据表及本地链接的检查结果。接口共包含 23 个操作，具体检查数量以报告为准。

检查结果验证当前候选结构的一致性，不表示成品格式或文件管理粒度已经确认。

## 验证限制

当前尚未部署，Spring Boot 应用尚未实现。HTTP 登录、对象存储实际读写与校验、内容制作工具、客户端渲染、现场定位、服务器容量和备份恢复均未验收。系统结构图和数据库关系图已生成 PNG 和 SVG，并检查 PNG 的文字、连线与布局。数据库关系已对照 SQL 外键核对；其余 Mermaid 图尚未进行图形渲染检查。

本次文档重写不改变 SQL 行为，沿用现有数据库验证记录；接口元数据与文档链接通过设计检查重新验证。

## 复现命令

在仓库根目录执行：

```powershell
python -m pip install -r scripts/requirements-review.txt
python scripts/generate_contracts.py
python scripts/verify_design.py
python scripts/verify_database.py --pg-bin 'C:/Program Files/PostgreSQL/17/bin'
```

按实际安装位置调整 PostgreSQL 路径，并在报告中保留实际测试版本。依赖位于其他目录时，执行前配置 `PYTHONPATH`。

数据库脚本只启动自身的临时实例，结束后停止，不连接业务数据库。

## 架构与工作流补充审查

[补充审查](07-design-review.md)核对了架构、数据库、工作流、接口和防御措施的实现成本。[审查证据](design-review-evidence.json)来自新的独立临时 PostgreSQL 18.4 实例，原有 31 项检查通过，额外 5 项检查确认了空并发版本号、普通表写权限绕过发布入口、审计写入影响历史访问资格，以及撤销时递增版本号被拒绝的边界行为。实例已停止，原有数据库验证报告保持不变。

补充报告的通过状态表示成功复现所描述的行为，不表示这些风险已经修复。运行角色的权限由测试构造，不能视为实际部署配置；应用、目标 PostgreSQL 17、对象存储及客户端仍未验证。

本轮另行核对三份生成产物与生成源一致、接口共 23 个、36 个本地文档链接有效，并通过文风检查。当前 Python 环境缺少完整 Schema 校验依赖，未重新执行完整的 OpenAPI 和 JSON Schema 验证。

## GH-1 首页操作指引（2026-09-19）

首页新增平台用途、四步操作路径、按已有权限与动态路由展示的常用入口和发布提示。核对了当前页面名称与菜单迁移。Linux 实现自查及 Windows 待验收步骤见 [首页验收说明](evidence/issue-1/README.md)。真实登录、目标页面、浏览器菜单 150% 缩放及 Windows ingestion 尚未验收；本次未部署，未操作日常 Demo 或真实账号/存储。

## 2026-09-19 PR #2 简单审查、构建与内网部署

- 用户明确授权 review、构建、合并和部署。审查 head 062a1493a88ff3d4d5c64b97e21fb26e8aaf75d4，与当时 main a0df970 的合并候选；未发现实质缺陷。核对首页三个权限及路由、动态路由加载时机、四步操作名称及发布边界。主工作区其他未提交修改未纳入。
- Windows 隔离目录 .local/pr2-release：npm ci 成功；使用 PYTHONPATH 指向已有 .local/python 依赖后 doctor quick、check quick、check frontend 均通过。frontend 报告 .local/harness/20260919T145118Z-2kgfytra/report.json，sourceUnchanged=true，包含 draft-panel 和生产构建。首次 doctor 因隔离目录缺 Python 依赖阻塞，未作为通过证据。
- Docker gateway 生产构建通过，镜像 innovation-gateway:pr2-062a149。PR 合并提交 e92ceed746b5c1ee485fae850a6449cd5ecb1ad9；部署用 frontend/deploy/compose 与合并主分支无差异。
- 保留原镜像 innovation-gateway:before-pr2，以新镜像更新 infra-v1，仅执行 compose up -d --no-deps --no-build gateway。后端、数据库、Redis 未重建。网关 healthy，/healthz 与 /index HTTP 200；实际 HTTP 获取 index-BYBCSCSi.js 含操作步骤、发布前请留意。
- 地址 http://192.168.0.12:43174/index 。已有 Chrome 页刷新后进入登录页；未绕过登录，登录后真实点击、权限差异及第二台 LAN 设备访问仍未验证。此前人工确认的是隔离组件视觉效果，不等同完整业务验收。本次没有数据库改动或数据库版本验收。

## GH-4 默认展示发布版本文件（2026-09-19）

新增默认发布版本选择、发布成功后的文件切换及场景初始化过期响应防护；保留手动选择和发布冻结规则。[自查范围与 Windows 验收步骤](evidence/issue-4/README.md)记录命令和限制。组件模拟回归已通过；最终 harness 结果见本任务 PR/Issue 进展记录。真实登录点击、Windows ingestion 与独立审查待完成，不代表业务验收通过。无数据库变更，未部署。
## GH-3 场景操作记录中文动作（2026-09-19）

核对当前后端全部 21 种动作，前端集中映射中文，未知代码保留原文；不修改接口、数据库、刷新或详情处理。实现自查、合成记录组件截图、完整映射和 Windows 待验收步骤见 [GH-3 验证说明](evidence/issue-3/README.md)。真实登录页面、Windows ingestion 和独立审查仍待完成；未合并、未部署。
