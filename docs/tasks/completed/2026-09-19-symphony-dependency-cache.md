# Symphony 预装验证依赖与共享下载缓存

状态：完成。负责人：Codex。更新时间：2026-09-19 UTC（北京时间 2026-09-20）。

## 目标与验收

将固定验证依赖预装进 Symphony 镜像；pip/npm 下载缓存持久化并跨任务共享。
每个 Issue 保留独立 venv 和 node_modules，保留并发上限 4 和现有工作区隔离，不中断正在执行的任务。

## 进度与决定

- [x] 新增受版本控制的镜像扩展配方及最小构建上下文入口。
- [x] 实现任务 venv 引用镜像只读验证依赖；requirements 变化时只在当前任务补装。
- [x] 无网络 Linux 镜像 4 项检查通过；pip 命中共享缓存，npm 在第二容器离线复用，实际 App Server 沙箱拒绝跨工作区写入。
- [x] 未中断 GH-3/GH-4；先同步只读依赖，任务结束且队列为空后正式切到验证镜像。合成工作区离线准备 1.703 秒，服务健康，默认模型校验通过。
- [x] quick doctor/check 通过；证据、版本和当前容器实际接入方式写入验证记录。

## 验证证据

原镜像 innovation-symphony:0.0.3 保留，新镜像 innovation-symphony:0.0.3-validation-v1，ID sha256:4098208ef5fc0d57a5292ea610ee91ed6a0e57d8e3311fa8cf77461416b1ba8f。
构建只发送 Dockerfile、requirements-review.txt、prepare_symphony_workspace.py，不发送登录文件或源码工作区。
环境证据位于 .local/symphony/environment-validation/：image-tests.log、bind-init.json、runtime-init.json、warm.json、offline.json、appserver-cache.json。
quick 命令：python scripts/harness.py doctor --profile quick、check --profile quick。阶段报告 .local/harness/20260919T160018Z-igi1txta/report.json；补写文档后的复核以最新 .local/harness 报告为准。

## 交接与恢复

原任务会话未中断，未修改其 venv 或 node_modules。任务结束后已切换验证镜像；新会话通过工作流和镜像导出 PIP_CACHE_DIR/NPM_CONFIG_CACHE，缓存由 /data 持久化。
无新增常驻辅助进程，镜像导出源容器和验证容器均已移除；保留测试证据和缓存。回退容器 innovation-symphony-before-cache 停止保留，工作流备份在 .local/symphony/environment-validation/rollback/。准备脚本故障可将 before_run 改回任务本地 venv 安装路径；不要删除其他任务环境或共享 data。镜像重建仍须避开活动任务。
