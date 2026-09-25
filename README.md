# innovation-ar-resource-platform

V0.1 面向第一阶段的 AR 场景展示：团队制作场景内容，管理员上传、预览和发布，用户扫码后下载内容并播放。

当前已实现 PostgreSQL 管理后台、Docker Compose 部署和本地文件存储基础组件。包含若依 Spring Boot 3 后端、Vue3 前端、登录与同权账号、日志、场景管理及审计。资源入库已接入：场景下创建版本草稿、上传多个文件、校验与登记、失败重试、启动对账、后台查询，以及同一场景一份当前发布版本（替换发布、已发布文件冻结）。客户端下载、预览和单独下线尚未实现。

本轮实现范围和验收以 [资源入库闭环](docs/12-resource-ingestion.md)为准；架构背景见 [技术选型、数据库、后端平台与作业流](docs/11-current-platform-architecture.md)。部署和运维操作见 [Docker 部署与存储基础设施](docs/10-local-infrastructure.md)。原云存储、昼夜、AR 坐标和多文件设计保留为历史候选材料，不能直接作为当前实现要求。

本机 Vite 开发入口为 http://127.0.0.1:43174；当前局域网 Docker Compose 入口为 http://192.168.0.12:43174（未覆盖配置时 Compose 默认绑定 http://127.0.0.1:18081）。新数据库首次使用 `bootstrap` 和私密配置中的引导密码登录，创建第一个日常管理员以后，引导账号自动停用。旧本机 Demo 的数据不会自动进入 Docker 数据库。

[上游来源与适配记录](docs/09-upstream-adaptation.md)说明固定版本与维护边界。下面的 V0.1 方案概览包含后续能力，不能作为当前已实现功能清单。

## 方案概览

| 内容 | 设计 |
|---|---|
| 后端架构 | 一个 Spring Boot 应用，按功能分包 |
| 数据存储 | PostgreSQL 保存业务数据，本地持久卷保存成品；通过存储接口隔离实现 |
| 内容制作 | 人工完成扫描、GS 重建、编辑和构建，平台接收成品 |
| 内容发布 | 目标为人工发布与回滚；内容变体及文件契约待真实成品确认 |
| 后台权限 | 每人独立账号，具有相同管理员权限，操作记录到人 |

已确定保留“场景—内容版本—成品文件”的分离。文件管理粒度待成品交付格式确认后决定；本轮支持草稿关联多个独立文件，不解析包内模型、音频、catalog 或共享依赖。旧候选 SQL 与关系图不参与当前初始化。

[打开交互式汇报页面](docs/presentation.html)：以示例场景演示后端架构、数据模型和发布流程，可本地打开。

## 阅读顺序

1. [当前架构基线](docs/11-current-platform-architecture.md)：技术选型、数据库、后端平台和作业流。
2. [Docker 部署与本地存储](docs/10-local-infrastructure.md)：启动、存储约定、验证和迁移操作。
3. [验证记录](docs/06-validation.md)：已经完成的检查及验证限制。
4. [Demo 启动与维护](docs/08-demo-runbook.md)：旧本机进程模式和维护说明。

`docs/01` 至 `docs/05`、`docs/07` 及交互式汇报页面记录旧云存储与昼夜候选方案，供历史评审使用。

## 开发资料

- [Agent 工作流入口：口头需求 → Issue → 编码 → 本机验收](docs/17-agent-workflow.md)

- [仓库知识入口](docs/index.md)
- [基础 Harness 与验证入口](docs/13-harness.md)
- [数据库初始化说明](database/README.md)
- [OpenAPI 接口契约](contracts/openapi.yaml)
- [运行清单 Schema](contracts/schemas/runtime-manifest.schema.json)与[示例](contracts/examples/runtime-manifest.json)
- [仓库贡献指南](AGENTS.md)

产品设计版本为 V0.1，OpenAPI 文档版本为 `0.3.0`，使用标签区分 Demo 已实现和后续候选接口。接口路径中的 `/api/v1` 和清单中的 `schemaVersion: 1` 分别表示接口与清单协议版本。
