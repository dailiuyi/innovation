# Symphony 环境版本与轻量自检

本页用于本机 Innovation 的受控 Agent 环境，不替代 [任务流程](17-agent-workflow.md) 或 [宿主验收](16-fast-review.md)。环境变更后做一次完整环境验收，普通任务只运行轻量自检。

## 已固化的内容

[环境清单](../deploy/symphony-environment.lock.json) 记录接受的镜像 ID、工具版本、镜像内验证依赖清单摘要、WORKFLOW、控制器脚本及编译补丁摘要。文本摘要规范化 CRLF/LF，编译模块核对原始字节。清单不含凭据，不扫描业务源码或 node_modules。

`Start` 首先检查宿主文件和镜像标签对应 ID；容器将清单只读挂载。受控任务读取有效外置计划后、首次进入 coding 前，按计划检查运行中的控制器版本、工具 PATH/版本、原生工作区、工作区临时写入、venv 导入和 Java 模块路径。失败持久化 environment_preflight_failed，不能消耗修复机会或绕过终态自动重试；修复环境后仍经 ResumeTask 显式恢复。

quick 检查 Python/Git/Codex 和验证依赖；frontend 额外检查 Node/npm；javaModules 非空时检查 JDK/Maven。自检只执行有超时的版本/导入命令和小文件校验，不安装依赖、不构建、不调用模型、不执行完整环境测试。通过只代表声明的环境就绪。

## 日常入口

```powershell
# 按现有任务计划自动选择 profile 与 Java 模块；不恢复任务、不改计划。
./scripts/symphony.ps1 Doctor -Issue 13
# 不绑定任务时，只核对所选工具与环境版本。
./scripts/symphony.ps1 Doctor -Profile frontend -Java
# 仅核对宿主版本与本地镜像 ID，不连接运行中的任务。
python scripts/symphony_environment.py verify
```

检查失败先查看具体不一致项。不得把重新 freeze 当成修复命令；它会接受当前输入作为候选基线，必须由操作者在明确环境变更后运行，并通过下面的验收。

## 变更、验收与恢复

1. 队列空闲时保存旧容器、配置和补丁，修改仓库中的配方或控制器。不能在正在编码/构建时热更新环境。
2. 如需构建镜像，将校验过的官方 Symphony v0.0.3 Linux x86_64 文件放到 `.local/symphony/downloads/symphony-v0.0.3-linux_x86_64`。`BuildBase` 会核对清单所记录的发行文件 SHA-256，再使用 [基础镜像配方](../deploy/symphony-base.Dockerfile)；随后 `Build` 使用 [验证镜像配方](../deploy/symphony.Dockerfile)。不要把含凭据的目录作为构建上下文。
3. 使用已有 `prepare_symphony_blocking_fix.py` 在无凭据临时容器中生成、编译和验证补丁。恢复既有环境优先使用下述已校验模块副本；编译补丁及其清单必须配套，不以裸旧模块覆盖当前版本。
4. 显式执行 `python scripts/symphony_environment.py freeze`，运行 quick 和 Linux 环境/隔离回归。切换空闲容器后执行 Doctor。没有通过时不接收任务；按保留的容器和脚本回退。
5. 将配方、脚本和清单一并纳入 Git。基础 Node 标签、apt 与部分传递依赖不是逐字节重现锁；源码重建可能得到不同镜像 ID，应重新测试再接受，不能修改标签来伪装原镜像。

当前可精确恢复的离线副本在 `.local/symphony/environment-lock-validation/recovery/`：`innovation-symphony-java-v2.tar`、对应 SHA-256 文件、补丁 `manifest.json` 与 `ebin/`。它们不含运行容器的凭据和用户数据，也不进入 Git。迁移机器时另行安全转移，校验归档后 `docker image load --input <镜像归档>`，再按清单 ID 核对；将补丁副本恢复到新环境 `.local/symphony/data/blocking-fix/`。任务卷、task-control 与登录资料单独保留/准备，不从镜像恢复。新机器仍须完成 Doctor 与环境验收，不把本机检查当作新机器通过。

旧容器 `innovation-symphony-before-environment-lock` 已停止保留。回退前确认队列空闲，停止并保留新容器，恢复 `.local/symphony/environment-lock-validation/rollback/` 内对应原文件，再恢复旧容器名称并启动；不得覆盖回退点之后的新任务数据。

## 并发资源

继续允许 4 个 Agent 编码。Java/前端构建测试阶段由控制器使用跨任务 OS 文件锁，默认同时 1 路；其他任务等待构建槽位，不因等待计入 Maven/Vite 命令超时。等待可取消，进程退出自动释放锁，state.buildSlot 记录 waiting/acquired/released。仅 quick 且无 Java 模块的轻量检查不占构建槽位。它不是新服务或业务任务队列。

`symphony.ps1 Start -BuildConcurrency 1` 写入 `SYMPHONY_BUILD_CONCURRENCY`，允许 1–4，未设置时控制器默认 1。变更仅在空闲切换时生效；不要只改某个任务进程的值，所有任务必须使用同一并发上限。

2026-09-20 无网络、无凭据、2 核/4 GiB 原生卷验证：单任务 Java+前端基线 28.138 秒；两个任务同时执行共 48.438 秒，每个均通过 22 项 Java 测试，前端产物与基线一致，无 OOM。吞吐提高约 16%，匿名内存峰值约 2.81 GiB、含文件缓存约 3.89 GiB，因此保持 4 个编码任务、默认串行重构建，为模型进程和调度器留余量。该结果不证明四路并发或冷下载速度。

可复用验证脚本为 [verify_symphony_concurrency.py](../scripts/verify_symphony_concurrency.py)。只在独立无网络/凭据容器运行，将原生工作区卷只读挂载为 `/seed`、新的原生验证卷挂载为 `/validation`；先初始化用户 1000 拥有的空 `run` 子目录，再执行 `--seed /seed/GH-13 --output /validation/run`。脚本拒绝非空或重叠目标，独立复制三份源码和暖依赖，检查复制的依赖哈希，先跑一次基线再跑两路并发，保留所有证据。不要对活跃的种子工作区执行，也不要复用失败运行的输出目录。

证据在 `.local/symphony/environment-lock-validation/`，实际报告文件为 `concurrency-report.json`、`doctor-final.log`、`task-gate-integration.json`、`linux-tests.log`。容器/卷 `innovation-symphony-concurrency-20260920` 已停止或闲置保留；其中 run2 是成功实验，旧失败样本保留供定位，不是通过证据。真实数据库/HTTP/浏览器验收继续使用宿主流程。
