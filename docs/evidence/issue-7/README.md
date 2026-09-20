# GH-7 密码长度返工验收

## 改动和验收范围

旧提交 `7e15656383b5ea17216e8a8b0acb79cce39fbaa7` 允许设置 6 字符密码，但登录仍要求 12 字符。返工将实际登录使用的 `UserConstants.PASSWORD_MIN_LENGTH` 改为 6，并让 `DemoAccountService` 引用同组最小/最大常量，最大值保持 64。

Bootstrap、创建账号、重置和个人改密均调用公共校验；登录执行 `SysLoginService.loginPreCheck`。未更改 BCrypt、角色、数据库迁移、密码变更触发器、Token 的 `credential_epoch` 比较或个人改密后的会话删除。注册路由仍未开放。现行页面、生成源、OpenAPI（含 OwnPassword）及文档保持 6–64。

验收矩阵：5/65 字符在设置入口被拒绝并提示“密码长度必须为 6–64 个字符”；6/64 在四个设置入口成功且随后可登录；重置和个人改密使所有旧 Token 失效。新增登录服务测试另覆盖 11 字符，防止只接受边界 6 而遗漏区间。当前登录拒绝仍保留原有统一认证错误。

## 本次 Linux 自查

环境：Python 3.11.2、Node 22.23.2、npm 10.9.8；没有 JDK/Maven，没有数据库验收版本。

本地 Git HEAD 为 `b2b020030d05322f32de0710689707f05bf67dfb`，工作区包含旧 PR 修改及返工；`.git` 只读，无法本地切换分支。通过 Git Data API 在已核对的远端 `codex/issue-7` 原提交之上追加提交，不强推；最终提交号见 PR #8。

- `.local/venv/bin/python scripts/generate_contracts.py`：成功重新生成。
- `.local/venv/bin/python scripts/harness.py doctor --profile quick`：passed；`.local/harness/20260920T020556Z-x2a82oz8/report.json`。
- `.local/venv/bin/python scripts/harness.py check --profile quick`：passed；`.local/harness/20260920T020725Z-qs10a2y_/report.json`。
- 以上报告的源码 SHA256 为 `1adc600a812b770f4f6274b153f2cc5b0128d5ef93c93b4f35bf4e58b5920888`，检查过程中未变化；该快照包含代码和测试，不含本验收说明。
- `npm --prefix frontend ci --prefer-offline --no-audit --no-fund --cache /data/cache/npm` 和 `.local/venv/bin/python scripts/harness.py check --profile frontend`：本次最终结果和报告路径记录在 PR #8 / Issue #7 唯一进展评论。
- `DemoAccountServiceTest`、`SysLoginServiceTest`：本容器未执行；后者使用真实登录前置校验、UserDetailsService、密码校验和 BCrypt，数据库查询、Redis、异步调度及 Token 签发为替身。不能作为 HTTP/数据库或 Token 失效验收。
- Windows ingestion、真实登录点击与独立审查：待完成。旧提交在宿主机的验证结果不证明返工版本通过。

## Windows 隔离验收步骤

在本 PR 最终提交的独立 checkout 中准备 JDK 21、Maven、PostgreSQL 17、Redis、Edge、任务自己的 Python/前端依赖和 Maven 缓存；不要操作日常 Demo、LAN Compose 或真实账号。先记录实际提交和工具版本。

```powershell
mvn -f backend/pom.xml -pl ruoyi-framework -am test
.local/venv/Scripts/python.exe scripts/harness.py doctor --profile quick
.local/venv/Scripts/python.exe scripts/harness.py check --profile quick
npm --prefix frontend ci --prefer-offline --no-audit --no-fund
.local/venv/Scripts/python.exe scripts/harness.py check --profile frontend
.local/venv/Scripts/python.exe scripts/harness.py doctor --profile ingestion
.local/venv/Scripts/python.exe scripts/harness.py check --profile ingestion
```

确认 Surefire 实际执行两个密码测试类且无跳过。普通 ingestion 使用较长随机密码，**并不覆盖以下专项账号矩阵**；须另建临时 PostgreSQL 17 数据库、Redis 实例、存储目录和随机回环端口，使用本提交新构建的 Jar 完成：

1. 分别以 5、6、64、65 字符合成 `AR_BOOTSTRAP_PASSWORD` 启动空数据库。5/65 启动校验失败且提示长度；6/64 启动健康并可 `POST /login`。每例使用新库，已有账号会跳过 bootstrap 校验。
2. 用有效 bootstrap 会话 `POST /system/user` 创建日常管理员 A，成功后重新登录 A（bootstrap 会停用）；由 A 创建 B。分别测试 5/6/64/65，失败请求不可创建账号，成功密码须可登录。
3. 保留 B 的两份登录 Token。A 调用 `PUT /system/user/resetPwd`，先确认 5/65 失败且 B 原密码和 Token 仍有效，再分别确认 6/64 成功、新密码能登录、两份旧 Token 请求 `GET /getInfo` 均被拒绝。
4. B 调用 `PUT /system/user/profile/updatePwd`，对四种长度重复上述检查；新旧密码须不同。成功后用新密码重新登录，确认全部旧 Token 失效。失败的改密不得改变原密码或会话。
5. 浏览器完整登录，检查新增账号、重置弹窗和个人设置的“6–64 个字符”提示、重置输入边界和改密后重新登录行为。框架接口须同时检查 HTTP 与响应体 `code`，HTTP 200 本身不表示业务成功。

记录各项结果、实际 PostgreSQL/JDK 版本、新 Jar 来源及源码指纹；报告仅保留脱敏摘要，不记录密码或 Token。本说明不是独立审查或合并/部署许可。
