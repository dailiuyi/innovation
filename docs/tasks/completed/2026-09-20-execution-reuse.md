# Symphony 安装与构建复用

状态：完成。负责人：Codex。更新时间：2026-09-20 UTC。

## 目标与验收

在现有 harness 上提供统一 Agent 检查入口，任务工作区内复用依赖和生产构建；输入或产物变化即失效，同输入失败/超时/中断不自动重试，保留真实证据与明确交接结果。

范围：npm 安装、frontend build、工作流与运行工具接入。quick 每次重新执行；不缓存浏览器、数据库、真实业务验收，不共享任务 node_modules，不修改业务实现。

## 进度与决定

- [x] 增加任务锁、原子记录、依赖/构建输入及产物指纹。
- [x] 新增 agent_check 入口并接入 harness 前端构建。
- [x] Windows/Linux 15 项复用故障回归通过；真实独立副本安装、构建及连续完整 frontend 流程通过。
- [x] 更新工作流与手册，安装运行工具，保留宿主与业务验收边界。

已存在的 DeepSeek、调度阻塞修复、页面翻译改动全部保留。运行中的 GH-9 不在开发时被修改或重启。

## 验证证据

基线 HEAD 5806c68680212dccc3874b94a0ddd49dde080a5a；工作区含已有未提交修改。Windows 独立副本首次安装 14.4 秒；连续两次完整 frontend 入口分别 56.5 秒和 25.8 秒，第二次安装/构建均 reused，quick 与草稿面板仍实际运行，两份报告 sourceUnchanged=true。报告位于 `.local/execution-reuse-validation/.local/harness/20260920T081319Z-9y_olpn4/` 与 `20260920T081416Z-hgfroei5/`；计时汇总 `.local/execution-reuse-validation/integration-benchmark.json`。最终宿主 quick 报告见本次交付。

## 交接与恢复

入口 scripts/agent_check.py、scripts/frontend_control.py。运行记录保存在任务 .local/frontend-control 与 .local/harness。仅初次无可信安装记录时安装一次；不采信旧 dist 作为构建成功证据。

## 完成记录

新增当前 Symphony `/opt/symphony-execution` 只读工具，未来启动用只读挂载；未重启或改写 GH-9 工作区。旧会话提示不自动更新，新会话使用新入口。复用对所有模型生效，但未封禁绕过入口的任意 shell 命令；工作流明确禁止绕过。依赖完整哈希有 I/O 成本，Docker 挂载盘上的实际速度需单独测量；本次 Windows 计时不代表 Linux 实际构建速度。数据库、浏览器业务、发布及客户端行为未变也未重新验收。
