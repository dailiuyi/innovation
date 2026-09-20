# 需求专项优先与审查实例

状态：已完成本地实现与实例交付；人工业务验收待用户执行。负责人：Codex。

## 目标与验收

- 先执行最短需求专项，失败即停止，按风险追加回归。
- Symphony 镜像具备 JDK 21、Maven；Java 修改必须实际运行测试再交付。
- 固定 PR/提交隔离目录与准备、测试、启动、状态、停止入口。
- 独立审查通过后，提供同版本可登录的回环验收实例；不修改日常 Demo。

## 进度与决定

- 保留现有未提交 Symphony 配置改动，在其基础上增量实现。
- 使用原生 Windows 隔离进程，避免为每次审查重建业务镜像。
- 验收实例由长驻父进程管理，避免 Windows Job Object 导致启动后退出。
- 模型标签及远端 Issue/PR 不在本次变更范围内。

## 验证证据

- `test_review.py` 6 项通过；保护提交身份、脏目录、失败证据和并发生命周期。root quick 检查已包含该测试。
- Java 镜像无网络/无凭据环境测试 5 项通过；Temurin 21.0.9、Maven 3.9.11。新镜像实际执行 PR #8 登录相关 Java 测试 6 项，零失败/跳过。首次 Linux Maven 下载约 4 分 27 秒；隔离缓存 `.local/symphony/java-validation-cache`，不当成任务共享缓存已接入。
- PR #8 `78c147e54276f0caf8c28e298c69b4b88b1e77ac`：accounts 约 48 秒，23 项 Java 测试及 48 项 HTTP 断言通过，PostgreSQL 17.6；报告 `.local/reviews/pr-8/78c147e54276f0caf8c28e298c69b4b88b1e77ac/check-522f3f79efa9/report.json`。frontend 约 62 秒，通过；报告同提交目录的 `check-de025cb9408b/report.json`。两者 sourceUnchanged=true。
- 固定命令 prepare/check/serve/status/stop 已实际执行。第一次预览正常停止；最终预览 `http://127.0.0.1:9584`，目录 `preview-46c567cc8fdb`，页面/API 代理/真实登录通过，独立状态检查 healthy=true。凭据仅在该目录 credentials.json。
- 未执行浏览器全流程点击、bootstrap 所有启动边界、完整 ingestion 或其他设备访问；没有合并、推送或操作日常 Demo。

## 交接与恢复

调度空闲、ready 队列为空时已切换；健康与 gpt-6-astra/low 校验通过。旧容器 `innovation-symphony-before-java-v2` 保留。首次启动被已关闭 GH-7 自动清理阻塞；停止后将残余目录原样归档至 `.local/symphony/data/archived-workspaces/GH-7-20260920-startup-recovery`，重启恢复。原始 Symphony GH-7 工作区已被上游部分删除，不能声称完整保留；远端提交及固定审查目录不受影响。无凭据冒烟容器已停止保留。

使用 [固定流程](../../16-fast-review.md) 的 status/stop 管理本次实例。父进程被强杀或重启电脑后应核对实例状态，不能沿用旧 healthy 结论。当前本地脚本尚未提交；运行中 WORKFLOW 提供旧远端检出缺少 check_java.py 时的等价 Maven 命令。
