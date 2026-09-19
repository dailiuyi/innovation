# GH-1 首页指引验收

本次仅修改首页展示和导航。入口按现有权限工具与已加载动态路由判断，主按钮保留原名称。路径核对：`/admin/scenes`（场景管理 → 场景列表）、`/account/accounts`（账号管理 → 账号列表）、`/admin/audits`（场景操作记录）。步骤名称来自 `scenes.vue` 和 `DraftPanel.vue`，文件夹上传明确为替换全部文件。

## 环境与证据边界

Linux，Python 3.11.2、Node 22.23.2、npm 10.9.8。基线提交 `4b9861a96837f152f973df61aa6476c7df94b248`。未运行 PostgreSQL、后端、日常 Demo、LAN Compose；无数据库版本验证。实现自查不替代独立 review。

浏览器与截图阻塞：已在 `.local` 安装 Playwright 与 Chromium，但启动报错 `libglib-2.0.so.0: cannot open shared object file`，退出码 127。未成功渲染页面，未生成截图；浅色、深色、窄窗口、150% 缩放、实际点击和权限隐藏均不能宣称浏览器验证通过。源码自查确认采用 Element Plus 主题变量、自适应网格、可换行文本且无固定内容高度。真实登录、动态菜单和目标页面仍需下述 Windows 独立测试。

依赖安装首次 `npm --prefix frontend ci` 因默认 `/home/node/.npm` 缓存不可写而失败；改用 `npm_config_cache=$PWD/.local/npm-cache npm --prefix frontend ci` 成功，锁文件未变。quick 首次使用独立 Git 元数据环境变量导致 harness 临时仓库指纹测试失败，撤掉变量后重跑通过，未修改测试。后续检查均使用原检出 Git 基线和包含未提交文件的源码指纹。

## Windows 待验收步骤

在独立 Windows 验收检出准备 PostgreSQL 17、JDK 21、Maven 缓存、Redis、Node、Playwright 和 Edge，按开发工作流配置依赖。不要使用日常 Demo、真实账号或存储。

```powershell
npm --prefix frontend ci
python scripts/harness.py doctor --profile quick
python scripts/harness.py check --profile quick
python scripts/harness.py check --profile frontend
python scripts/harness.py doctor --profile ingestion
python scripts/harness.py check --profile ingestion
```

`ingestion` 使用自身隔离账号、数据库和存储，并自动清理进程；现有脚本不覆盖首页完整验收。首页需在另外准备的独立测试应用中，以合成管理员完成以下人工步骤（不要调用日常 Demo 启动命令）：

1. 从 `/login` 输入测试账号密码登录，进入 `/index`，确认标题、介绍、四步操作和四条发布提示常驻可见。
2. 点击“进入场景管理”，确认 `/admin/scenes`。返回首页，依次点击“场景管理”“账号管理”“场景操作记录”，确认分别到达上述三个路径及对应页面。
3. 在独立测试库准备无对应权限的测试用户，重新登录；确认首页不显示其无权限入口，无法通过入口获得额外权限。正常管理员应能看到全部入口。
4. 从场景列表选择合成场景，点击“编辑 → 版本与文件”，核对“新草稿说明”“创建草稿”“查看文件”“选择文件并上传”“选择文件夹并上传”“重新选择原文件”“发布/替换发布”。上传、发布及冻结规则由 ingestion 的真实流程结果佐证。
5. 在浅色与深色模式，分别检查宽窗口和窄窗口；通过浏览器菜单设为 150%，滚动查看全部内容，确认没有重叠、横向溢出或文字截断，键盘 Tab 可访问入口。保存全页截图，注明窗口、主题、缩放、源码提交和测试账号类型（不保存凭据）。
6. 核对 harness 报告范围、源码指纹及 skipped/blocked；补充真实截图与独立审查后，再判断所有 issue 验收项是否完成。

## 本次检查结果

被测源码对应提交 `70034711e9081a5ab501e671ea9f41339549a0f7` 的文件内容；本地 `.git` 只读，因此报告 HEAD 仍为基线提交，`dirty=true`。quick/frontend 的开始和结束指纹均为 `eab55b1270fbc7ca5df3451d1821541beaed93d5dcaa421eb4a83601de9d74b0`，检查期间源码未变。随后仅追加本节验证记录，未再修改首页。

| 命令 | 结果 | 本地报告 |
|---|---|---|
| `.local/venv/bin/python scripts/harness.py doctor --profile quick` | passed，环境探测 | `.local/harness/20260919T142210Z-vy_t8_ha/report.json` |
| `npm_config_cache=$PWD/.local/npm-cache npm --prefix frontend ci` | passed，锁文件未变 | `.local/npm-ci.log` |
| `.local/venv/bin/python scripts/harness.py check --profile quick` | passed，harness 回归与 371 项契约/链接检查 | `.local/harness/20260919T142849Z-gn1d_1ct/report.json` |
| `.local/venv/bin/python scripts/harness.py check --profile frontend` | blocked，前三步通过，Vite 构建在 transforming 阶段超过 300 秒 | `.local/harness/20260919T142850Z-_kwogzxr/report.json` |

frontend 无 skipped 步骤；构建被超时终止，日志未给出编译错误，具体慢点未定位，不能据此断言生产构建通过。另使用已安装的 Vue compiler-sfc 对首页执行 parse、compileScript、compileTemplate、compileStyle 均成功，仅说明单文件编译未报错，不替代完整构建或浏览器验收。ingestion、真实登录/入口点击、视觉检查与截图未执行成功，独立 review 未执行。初次失败的 quick 报告保留在 `.local/harness/20260919T142346Z-pzn5h_i8/report.json`，原因和纠正见上文。
