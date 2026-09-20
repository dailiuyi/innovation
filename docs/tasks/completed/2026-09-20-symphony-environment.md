# Symphony 环境版本、自检与并发验证

状态：完成。负责人：当前本机 Agent。

## 目标与验收

用户授权补齐版本固化、轻量环境自检、一次并发验证。保持当前单机单仓库、每任务独立依赖及宿主验收，不新增 Worker/队列，不合并或部署业务。

- 显式生成版本清单，普通启动/检查只核对，不自行接受版本漂移。
- 任务编码前检查所选工具链、原生卷、工作区可写与 Python 验证依赖；不扫描 node_modules，不下载软件。
- 独立、无网络/凭据的 2 核 4 GiB 容器，复制只读 GH-13 源码和暖依赖，执行一次串行基线与两个并发 Java/前端构建；记录测试数、源码/产物指纹、内存和 OOM。

## 进度与恢复

版本清单、自检及测试已实现并应用。旧容器 innovation-symphony-before-environment-lock 停止保留，工作区卷不改；工具原副本在 .local/symphony/environment-lock-validation/rollback。

并发测试容器 innovation-symphony-concurrency-20260920，独立卷 innovation-symphony-concurrency-20260920；初次测试空卷权限不正确，在实际构建前失败，已保留旧测试容器并改用初始化好的 run 子目录。发现空卷首次挂载复制可能恢复目录属主，启动脚本增加初始化标记防止再次覆盖。

无 Issue 入队、PR 修改或模型推理；GH-13 只作为只读测试样本。Symphony 已恢复，Doctor 通过，默认 4 个编码 Agent、1 路 Java/前端构建；纯 quick 不占槽位。


## 验证证据与完成记录

- 环境清单：deploy/symphony-environment.lock.json；恢复说明：docs/18-symphony-environment.md。
- Linux 环境/版本/路由/生命周期 46 项通过，最终生命周期 18 项补充回归通过；Windows 版本 6 项与生命周期 18 项通过；quick 门禁通过。
- 实际 Task.begin 自检：正常通过；移除 Java/Maven PATH 后在 coding 前阻塞。最终 Doctor 约 0.569 秒，没有包扫描或安装。
- 并发实验：2 核/4 GiB，单任务 28.138 秒，两任务共 48.438 秒；每个 22 项 Java 测试通过，源码与前端产物指纹一致，OOM 为零。暖依赖验证，不代表四路并发、冷安装或宿主业务验收。
- 详细证据：.local/symphony/environment-lock-validation/；恢复镜像归档约 596 MB，归档 SHA-256 和补丁模块已保留。失败测试样本未删除。
- 新文件和运行工具按任务范围提交；Codex Trace 相关未提交修改保留，不包含在本任务版本中。未推送、合并、部署 Demo，也未重新调度 GH-13。
