# 基础 Harness

先按 [专项优先流程](16-fast-review.md) 执行需求对应的最短检查，再按风险选择 profile。Java 专项使用 `scripts/check_java.py`；账号 HTTP 与同提交人工实例使用 `scripts/review.py`。通用 ingestion 不替代专项验收，也不是所有改动的默认门槛。

Harness 把仓库约束、验证脚本与交接记录组织成统一工作流。当前版本提供人工触发的验证入口，不调度模型、不自动修复、不合并、不部署。

## 使用

在仓库根目录运行（入口也支持从其他目录调用）：

```powershell
python scripts/harness.py doctor --profile quick
python scripts/harness.py check --profile quick
python scripts/harness.py doctor --profile frontend
python scripts/harness.py check --profile frontend
python scripts/harness.py doctor --profile ingestion
python scripts/harness.py check --profile ingestion
```

| Profile | 检查范围 | 前置条件 |
|---|---|---|
| quick（默认） | Harness 故障回归、审查工具回归、Symphony 模型路由协议回归、OpenAPI/Schema/示例、生成源一致性、AGENTS/README/docs 递归本地链接 | Python 3.11+、Git、requirements-review 中的契约验证依赖 |
| frontend | quick + 草稿面板乱序响应回归 + Vue 生产构建 | Node、npm、已通过 npm ci 安装的前端依赖 |
| ingestion | quick + 草稿面板回归 + 当前后端源码独立 Maven package（含测试）+ 原有隔离入库 API/Edge 验收 | Windows、项目 .local 中 PostgreSQL 17/JDK 21、Maven、Redis、Node、前端依赖、psycopg、Playwright、Edge |

`doctor` 只探测所选 profile 的必要环境，不安装依赖、不启动应用、不连接日常数据库。Python 同时搜索当前解释器和 `.local/python`；缺依赖时按输出提示准备。版本和路径沿用已有入库脚本的约定。Node 还会对现有回归脚本进行路径访问探测；如沙箱拒绝读取项目父目录，应申请对应命令的沙箱外权限，不修改业务代码绕过限制。

`ingestion` 把后端源码复制到本次运行目录，排除旧 target，再用项目 `.local/m2` 缓存离线打包；不覆盖正在运行的 Jar。缺少 Maven 缓存时 package 会失败，需要先按开发工作流准备依赖后重跑，不自动联网安装。测试使用随机回环端口、新数据库、新存储目录和合成账号。不会启动 Docker、重建网关或操作现有 Demo 账号。

## 报告与完成判定

每次调用创建独立 `.local/harness/<UTC时间>-<随机标识>/`，保存 `report.json`、逐步日志、专项证据和必要的构建产物。目录沿用 `.local/` 忽略规则，不自动清理。日志和测试目录可能包含运行时敏感信息，应留在本机；正式共享前检查脱敏。

- `passed` / 退出码 0：所选范围执行通过；doctor 的通过仅表示环境就绪。
- `failed` / 退出码 1：命令失败、契约漂移、断链或证据不完整/不通过。
- `blocked` / 退出码 2：缺环境、超时、中断、清理未完成，或检查过程中源码变化。
- `skipped`：前置检查阻塞或前一步未通过，后续没有执行；不能当成通过。

报告包含 UTC 时间、命令、工作目录、退出码、日志路径、Git HEAD 及包含未提交/未忽略新增文件的源码 SHA256。开始和结束指纹必须一致；恢复任务时需重新核对指纹，不能仅凭旧 HEAD 或旧绿色报告宣告完成。忽略的运行时文件和依赖不属于源码指纹；环境结果仅对应本次本机环境。

契约和入库步骤同时要求进程成功与非空、全部通过的结构化证据。不读取过去的报告补齐结果。每步有时限，遇错停止后续步骤；超时/中断尝试停止本次子进程树，并停止本次证据目录下遗留的 PostgreSQL。主机崩溃或直接强杀整个 harness 无法保证执行清理，应检查该运行目录和进程，不得扩大到日常 Demo。

现有 `verify_design.py` 和 `verify_ingestion.py` 新增 `--report-dir`；未指定时保留写入 docs 的旧行为。入库脚本另支持 `--backend-jar`。只有 harness 的 ingestion profile 保证先构建当前源码，再验收该产物；单独运行旧命令仍需自行确认 Jar 来源。

## 怎么选检查

文档、契约、规则修改先跑 quick。纯文案/按钮还需按开发工作流检查引用该控件的选择器；frontend profile 不代替人工视觉检查。前端行为改动跑 frontend；涉及入库、文件删除、恢复、审计或对应鉴权时跑 ingestion。账号等其他业务仍需对应专项验收，当前 harness 不宣称覆盖所有业务。

入库 profile 不运行历史候选七表数据库验收；候选结构校验不属于已实现业务的数据库证明。Docker Nginx 路由、LAN、真实客户端加载仍需独立验收。

正式证据的保存和引用遵循 [证据索引](evidence/README.md)。将真实验收摘要加入 [验证记录](06-validation.md)；需要提交专项 JSON 时只提升人工核对后的证据，避免把本机绝对路径或敏感日志一起提交。扩展入口时先明确测试环境、副作用和完成证据，再加入 profile。以后是否接 CI 或 Agent 调度，见 [基础决策](decisions/0001-harness-baseline.md)。
