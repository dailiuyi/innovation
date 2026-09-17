# 乌托邦世界后端平台 V0.1

V0.1 面向第一阶段的 AR 场景展示：团队制作场景内容，管理员上传、预览和发布，用户扫码后下载内容并播放。

当前已实现 PostgreSQL 管理后台、Docker Compose 部署和本地文件存储基础组件。包含若依 Spring Boot 3 后端、Vue3 前端、登录与同权账号、日志、场景管理及审计。真实成品尚未提供，资源上传、版本发布和客户端下载接口暂不接入。

当前设计以 [技术选型、数据库、后端平台与作业流](docs/11-current-platform-architecture.md)为准。部署和运维操作见 [Docker 部署与存储基础设施](docs/10-local-infrastructure.md)。原云存储、昼夜、AR 坐标和多文件设计保留为历史候选材料，不能直接作为当前实现要求。

当前 Docker 入口为 http://192.168.0.12:43174。新数据库首次使用 `bootstrap` 和私密配置中的引导密码登录，创建第一个日常管理员以后，引导账号自动停用。旧本机 Demo 的数据不会自动进入 Docker 数据库。

[上游来源与适配记录](docs/09-upstream-adaptation.md)说明固定版本与维护边界。下面的 V0.1 方案概览包含后续能力，不能作为当前已实现功能清单。

## 方案概览

| 内容 | 设计 |
|---|---|
| 后端架构 | 一个 Spring Boot 应用，按功能分包 |
| 数据存储 | PostgreSQL 保存业务数据，本地持久卷保存成品；通过存储接口隔离实现 |
| 内容制作 | 人工完成扫描、GS 重建、编辑和构建，平台接收成品 |
| 内容发布 | 目标为人工发布与回滚；内容变体及文件契约待真实成品确认 |
| 后台权限 | 每人独立账号，具有相同管理员权限，操作记录到人 |

已确定保留“场景—内容版本—成品文件”的分离。文件管理粒度待成品交付格式确认后决定；当前 SQL、接口与关系图中的多文件关联是候选方案，不代表必须逐个管理模型、音频等内部资源。

[打开交互式汇报页面](docs/presentation.html)：以示例场景演示后端架构、数据模型和发布流程，可本地打开。

## 阅读顺序

1. [当前架构基线](docs/11-current-platform-architecture.md)：技术选型、数据库、后端平台和作业流。
2. [Docker 部署与本地存储](docs/10-local-infrastructure.md)：启动、存储约定、验证和迁移操作。
3. [验证记录](docs/06-validation.md)：已经完成的检查及验证限制。
4. [Demo 启动与维护](docs/08-demo-runbook.md)：旧本机进程模式和维护说明。

`docs/01` 至 `docs/05`、`docs/07` 及交互式汇报页面记录旧云存储与昼夜候选方案，供历史评审使用。

## 开发资料

- [数据库初始化说明](database/README.md)
- [OpenAPI 接口契约](contracts/openapi.yaml)
- [运行清单 Schema](contracts/schemas/runtime-manifest.schema.json)与[示例](contracts/examples/runtime-manifest.json)
- [仓库贡献指南](AGENTS.md)

产品设计版本为 V0.1，OpenAPI 文档版本为 `0.2.0`，使用标签区分 Demo 已实现和后续候选接口。接口路径中的 `/api/v1` 和清单中的 `schemaVersion: 1` 分别表示接口与清单协议版本。
