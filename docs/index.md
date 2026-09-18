# 仓库知识入口

本页负责导航；具体行为以对应实现、迁移、契约和同版本验证证据共同确认。发现文档与代码不一致时先说明差异，不把旧设计直接变成当前需求。

| 要回答的问题 | 入口 | 使用边界 |
|---|---|---|
| 当前后台实现了什么 | [资源入库闭环](12-resource-ingestion.md)、[项目介绍](../README.md) | 已有场景、账号、私有入库和场景发布指针；预览、客户端加载未实现 |
| 当前平台如何组成 | [当前架构](11-current-platform-architecture.md) | 结合现行实现核对；后续设计不等于已有能力 |
| 如何开发、启动、打包 | [开发工作流](development-workflow.md)、[本机手册](08-demo-runbook.md)、[容器手册](10-local-infrastructure.md) | 日常 Demo、隔离验收、LAN Compose 是不同环境 |
| 应该跑什么检查 | [Harness 使用说明](13-harness.md) | profile 通过只覆盖声明的范围 |
| 如何审查改动 | [Code Review 默认规则](14-code-review.md) | 短提示指定范围与重点，默认独立审查、不修改 |
| 以前验证过什么 | [验证记录](06-validation.md) | 历史报告不证明当前未提交修改 |
| API 与数据库在哪里 | [OpenAPI](../contracts/openapi.yaml)、[数据库说明](../database/README.md) | API 按 implemented/candidate 区分；实际迁移在 backend 的 db/demo |
| 为什么作出某项决定 | [决策记录](decisions/README.md) | 记录原因、约束和重新考虑的条件 |
| 如何跨会话交接 | [任务管理](tasks/README.md) | 任务记录进度，完成后归档 |

`docs/01` 至 `docs/05`、`docs/07`、根目录 `database/migrations/` 和 runtime-manifest 示例包含历史候选设计。它们的结构检查可以通过，但不表示当前 Spring Boot 已提供相应接口。

新增长期规则时指定对应文档和验证方式。优先补一个能发现实际错误的检查，避免反复追加大段提示词。尚不能自动检查的约束，明确由任务负责人审查。
