# Symphony DeepSeek API 接入

状态：完成。负责人：Codex。更新时间：2026-09-20 UTC。

## 目标与验收

用户授权使用指定本地密钥文件及官方 `https://api.deepseek.com`，继续由 Codex 执行 Symphony 任务，显式选择 `deepseek-flash`。官方该 ID 当前对应 V4.1-Flash，不新增未经确认的别名；保留 GPT 默认路由。

## 进度与决定

- 模型标签选择提供商；首轮建立保留原策略/工具的 DeepSeek 线程，映射协议线程 ID，后续轮次固定复用。无需修改上游 Symphony。
- 密钥存入忽略的本地 secrets 文件，只读挂载；不会在命令参数、报告或审计中输出，shell 环境排除密钥变量。
- 新容器已启用；旧容器 `innovation-symphony-before-deepseek` 停止保留。没有提交、推送、远端 Issue 写入或日常 Demo 变更。

## 验证证据

见 [验证记录](../../06-validation.md) 的 2026-09-20 DeepSeek 段落。隔离两轮与合成动态工具、运行容器两个提供商真实 smoke、Linux 18 项回归、Windows quick 均通过；源码改动保留在工作区，最终 quick 报告记录当前 HEAD、指纹和 sourceUnchanged。

## 交接与恢复

下一次准备任务时使用 `symphony:model:deepseek-flash`、`symphony:effort:high`，组合验证后最后加 ready。路由和回退规则见 [手册](../../15-symphony.md)。运行容器由 `scripts/symphony.ps1 Stop` 停止；无需停止日常 Demo。真实开发 Issue 到 draft PR 不属于已完成的合成验收，仍待按任务验收。
