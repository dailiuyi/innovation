# 安装 Symphony 并接入 GitHub

状态：完成。负责人：当前安装 Agent。更新时间：2026-09-19 UTC。

## 目标与验收

用户要求安装 Symphony，最终选择 GitHub，并要求创建公开 innovation 仓库。

- 官方稳定发行包校验、镜像构建、服务和管理页面可用。
- 配置一任务一工作区、并发 1、显式标签入队、草稿 PR 人工审查。
- 不操作日常 Demo、数据库或业务存储；不声称 Linux 已通过 Windows ingestion 验收。
- 登录与看板轮询、实际 Agent 调用分开验证。

## 进度与决定

- [x] 官方 v0.0.3 Linux x86_64 下载与 SHA256 校验。
- [x] 构建 innovation-symphony:0.0.3，包含 Codex CLI 0.154.0。
- [x] 无凭据 memory tracker 服务启动，管理页面与状态 API 返回 200。
- [x] 发布前检查 846 个 Git 历史 blob、凭据格式和本地 config/*.env 中 6 个秘密值，未发现匹配。
- [x] GitHub API 核对实际账号 dailiuyi；已创建公开仓库 dailiuyi/innovation。
- [x] 完成集成文件 quick 检查，提交 def6bd3 并公开推送 main。
- [x] 用户明确授权凭据共享；验证 Codex 登录、最小模型请求和 GitHub Issues HTTP 200。
- [x] 定位 Docker 默认 seccomp 阻止嵌套沙箱；有限放行后 bubblewrap 无凭据验证通过。
- [x] 用户明确授权兼容配置应用到常驻容器，Codex 实际 shell 命令退出码 0，输出 731942。

实际 Issue 到 draft PR 不在本次安装连通性检查中，尚未执行；后续首个真实任务仍需独立验收。

## 验证证据

起始源码 HEAD：5664f27。官方源码参考 HEAD：be10a1b79df723d6d7612b5651c8522704dafb2e。
发行包 SHA256：ea35a04a54a6d37c0cafe3f195da871e47614a8c05765b90dbb4cac32e1435ee。
历史扫描结果：忽略目录 .local/symphony/history-scan.json。
Harness doctor/check quick 已通过，最新检查报告 .local/harness/20260919T134746Z-_hnihllp/report.json。

## 交接与恢复

入口见 docs/15-symphony.md 和 scripts/symphony.ps1。凭据共享最初被自动审批拒绝，用户随后明确授权后才执行。当前已登录容器名称 innovation-symphony；无凭据临时容器已移除。仅处理本次创建的容器。

## 完成记录

已安装运行程序、配置公开仓库和三个状态标签、启动常驻服务、验证模型及命令执行。默认保持空队列；用户创建目标明确的 Issue 并添加 symphony:ready 后才领取。Windows ingestion 与真实 Issue 到 PR 仍须后续验证。
