# 安装 Symphony 并接入 GitHub

状态：进行中。负责人：当前安装 Agent。更新时间：2026-09-19 UTC。

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
- [ ] 完成集成文件检查和公开推送。
- [ ] 获取明确凭据共享授权后验证认证与 GitHub 轮询。
- [ ] 实际 Issue 到 draft PR：尚未执行，不因服务启动而判定通过。

## 验证证据

起始源码 HEAD：5664f27。官方源码参考 HEAD：be10a1b79df723d6d7612b5651c8522704dafb2e。
发行包 SHA256：ea35a04a54a6d37c0cafe3f195da871e47614a8c05765b90dbb4cac32e1435ee。
历史扫描结果：忽略目录 .local/symphony/history-scan.json。
Harness doctor quick 已通过；check quick 待执行。

## 交接与恢复

入口见 docs/15-symphony.md 和 scripts/symphony.ps1。凭据共享验证曾被自动审批拒绝：宿主机 Codex auth.json 只读挂载到新容器需要明确用户授权；未绕过拒绝。
当前无凭据验证容器为 innovation-symphony-smoke，后续换成固定名称 innovation-symphony；不操作其他容器。
