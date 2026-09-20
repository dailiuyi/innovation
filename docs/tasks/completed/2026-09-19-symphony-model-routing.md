# Symphony 模型与思考深度路由

状态：完成（远端测试 Issue 验收待授权）。负责人：Codex。更新时间：2026-09-19 UTC。

## 目标与验收

准备 Issue 的 Agent 选择 GPT 模型与思考深度；Symphony 按标签执行，默认 gpt-6-astra / low。
仅支持当前 Codex 目录中的 GPT；保留原沙箱、官方 Symphony 二进制及单任务并发。
不自动升级模型，不操作业务服务，不创建远端验收 Issue。

## 进度与决定

- [x] 实现独立 Python stdio 适配器；标签从工作流首部封装读取，首轮锁定并逐轮注入。
- [x] Linux 14 项单元/协议测试通过，包含目录失败、超时、冲突、伪造正文、双向工具转发及进程组清理。
- [x] Codex CLI 0.154.0 隔离短请求验证 Astra low 默认组合、Luna medium 显式组合；turn_context 与请求一致。
- [x] 验证当前 WORKFLOW 的实际 Solid 模板，完成工作流与容器接入；查询和默认组合校验正常。
- [x] 完成 quick 检查、证据整理及运行态核对；远端 Issue 验收未执行。

## 验证证据

证据目录：`.local/symphony/routing-validation/`，包含 catalog.json、default.json、explicit.json 与适配器审计。
短请求在无 GitHub Token 的一次性隔离容器中运行，读取只读 Codex 登录；原始 rollout 位于已移除容器内，证据保存提取的模型/深度与线程 ID，不保存凭据或提示正文。
真实 Issue 到 PR 未执行，需要单独授权创建或修改测试 Issue。
quick 命令：`python scripts/harness.py doctor --profile quick`、`python scripts/harness.py check --profile quick`；报告 `.local/harness/20260919T152334Z-pd4k03tt/report.json`，sourceUnchanged=true。
该报告 HEAD 为 a0df970d5c191c4c6ce001a4c3c50cbf1ce0e70e，源码指纹 f5bd5da00cfff7c8b15181e0fb3403bcb030124a2eba2bef6a294997bebf972c；包含未提交及新增脚本。补写文档后的复核证据留在 .local/harness。

## 交接与恢复

保留现有 docs/06-validation.md、docs/15-symphony.md 及未跟踪会话查看器改动。
已确认空队列后切换；新容器 innovation-symphony 健康，原容器 innovation-symphony-before-routing 停止保留。原工作流与启动脚本在 .local/symphony/routing-validation/rollback/；回退顺序见 Symphony 手册，不得删除 data 工作区和日志。

## 完成记录

交付适配器、模型目录/校验/短请求工具、标签工作流、只读挂载、协议测试与 quick 集成、操作手册和验证记录。无新常驻辅助进程；运行中的服务仅为切换后的 Symphony。后续需要获准的专门 Issue 才能补齐远端端到端证据。
