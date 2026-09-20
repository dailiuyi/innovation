# 需求专项优先与人工验收实例

## 顺序

1. 先运行最短需求业务路径。密码策略先验证短密码设置后登录；发布功能先验证发布指针变更。实现前追踪实际调用方。
2. Java 修改先执行 `python scripts/check_java.py --module ruoyi-framework`（按风险选择模块），再执行 quick；UI 行为追加 frontend。零测试、跳过或未运行不能当通过。
3. 按改动选择 HTTP/数据库回归。账号变更不默认跑文件入库全套；迁移、存储、发布等相关变更才追加 ingestion。超时先定位原因，不盲目重复长构建。
4. 独立审查通过后启动同一提交的隔离实例，交付网址、凭据文件位置、版本、验证范围和停止命令。

## 固定宿主机命令

统一用同一个 Windows 用户执行，必要时授权沙箱外运行；不在沙箱账号与宿主账号间反复建立 Git 快照。命令不依赖当前目录：

```powershell
python E:/code/java/innovation/scripts/review.py prepare --pr 8
# SHA 替换为 prepare 返回的完整提交号。
python E:/code/java/innovation/scripts/review.py check --pr 8 --sha SHA --suite accounts
python E:/code/java/innovation/scripts/review.py check --pr 8 --sha SHA --suite frontend
# 独立审查者确认无阻断问题后执行。
python E:/code/java/innovation/scripts/review.py serve --pr 8 --sha SHA --reviewed-sha SHA
python E:/code/java/innovation/scripts/review.py status --pr 8 --sha SHA
python E:/code/java/innovation/scripts/review.py stop --pr 8 --sha SHA
```

工作区在 `.local/reviews/pr-编号/完整SHA/source`。每个提交独立检出，不覆盖脏目录、不切换主工作区。Python/JDK/PostgreSQL/Maven 来自宿主机 `.local`；npm 在审查目录独立安装并共享下载缓存。缺失 Maven 缓存时明确失败，确认后用 `check ... --online` 显式补齐依赖。预览运行期间拒绝重建，先停止再验证。

首个内置业务专项为 `accounts`：新 PostgreSQL 17、Redis、随机回环端口、当前提交新构建 Jar；先测 6 位 bootstrap 登录，再覆盖创建、重置、个人改密的 5/6/64/65 边界、成功后的登录、两份旧 Token 失效及失败请求不改变会话。不覆盖 bootstrap 全部启动边界、资源入库或所有页面点击；其他业务需增加对应专项。

`serve` 当前要求 accounts、frontend 两份同版证据通过，核对源码清洁、Jar 哈希、已审查 SHA 和远端 PR head。`--reviewed-sha` 是独立审查者明确声明，不是工具自动批准。前端使用同一源码的 Vite，验证页面、API 代理和真实登录；浏览器操作验收仍须按需求执行。凭据仅保存在本地实例目录；创建首个日常账号后 bootstrap 自动停用。

`serve` 是长驻前台进程：人在终端保持它运行，Agent 使用持续终端会话，并从另一命令查询 `status`。`stop` 请求父进程关闭自己创建的 Java/Vite/Redis/PostgreSQL，保留证据及隔离数据。父进程被强杀可能留下锁或 PostgreSQL，须核对实例目录与进程身份后恢复，禁止按进程名批量终止服务。

## Symphony

`scripts/symphony.ps1 Build` 构建 `innovation-symphony:0.0.3-java-v2`，包含 JDK 21/Maven。修改配置不代表运行容器升级。只有 running/retrying=0 且 ready 队列为空时保留旧容器并切换，沿用 data 和既有认证流程。

Symphony 交付可审查代码、已运行的 Java 证据和宿主待验收项；宿主独立审查者负责真实 HTTP 和人工实例。实现者不得自我批准。未启动同版实例时写“人工实例待启动”，不写“全部完成”。独立实例不等于合并或日常 Demo/LAN 部署。
