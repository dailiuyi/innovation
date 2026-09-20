# GH-9 场景列表入口拆分与列宽调整

实现基线 `5806c68680212dccc3874b94a0ddd49dde080a5a`，分支 `codex/issue-9`。改动：`frontend/src/views/demo/scenes.vue`、`frontend/src/views/demo/DraftPanel.vue`、`frontend/src/views/index.vue`、`scripts/verify_browser.py`、`scripts/verify_ingestion.py`、`scripts/verify_draft_panel.mjs`、新增 `scripts/verify_scene_list_ui.py`、`docs/12-resource-ingestion.md`、`docs/13-harness.md`、`docs/06-validation.md`、`docs/evidence/README.md` 与本目录。

## 改动行为

- 场景列表每行直接提供两个入口：“场景信息”打开名称、地址、坐标、坐标类型编辑弹窗，“版本与文件”直接打开该场景资源管理面板；打开资源面板不再经过编辑弹窗。
- 编辑弹窗底部只有“关闭、保存”（新建时标题仍是“新建场景”），不再包含“版本与文件”。
- 资源面板标题为“内容版本草稿 · 场景名”，正文首行显示“所属场景：名称（编号 …）”；名称取自 `GET /api/v1/scenes/{id}`，切换场景或迟到响应会失效并清空。
- 场景列表列宽：状态 80、修订号 80、操作 300 且 `fixed="right"`；名称、地址用 `min-width` 180/320 分配剩余空间并 `show-overflow-tooltip` 省略加悬停查看完整值。操作列按“场景信息、版本与文件、启用/停用、删除”四个按钮整体预留 300px，按钮保持原有链接按钮尺寸与 12px 间距。
- 发布、上传、下载、删除规则和版本列表、文件列表布局未改；发布成功后仍经 `sceneUpdated` 与关闭面板两条路径刷新列表。

## 容器内 Linux 自查

环境：Python 3.11.2、Node 22.23.2、npm 10.9.8（npm 缓存 `/data/cache/npm`），Chromium 153.0.8010.12（Playwright chromium-1243，headless）。

- `npm --prefix frontend ci --prefer-offline --no-audit --no-fund`：退出码 0，`frontend/package-lock.json` 未变化。
- `.local/venv/bin/python scripts/harness.py doctor --profile quick`、`check --profile quick`：passed，报告见 [验证记录](../../06-validation.md) 中本批次条目（含 HEAD、源码指纹与 `sourceUnchanged`）。
- `check --profile frontend`：contracts-and-links、draft-panel 通过；`frontend-build` 在 harness 固定的 300 秒步骤超时内未完成，profile 记为 blocked。同一命令直接执行 `npm --prefix frontend run build:prod` 退出码 0（墙钟 6 分 56 秒），`frontend/dist/static/js/scenes-*.js` 内含新列配置，`DraftPanel-*.js` 内含“所属场景：”。
- `scripts/verify_draft_panel.mjs`：通过，新增场景名加载与“切走后旧场景响应不得写回”的断言。
- `scripts/verify_scene_list_ui.py`：64 项全部通过（本目录 `validation-scene-list-ui.json`，逐项日志与截图见 `.local/scene-list-ui/`）。该脚本只启动 Vite 开发服务器与真实浏览器，用 Playwright 返回合成响应，不连接后端、数据库或存储。

浏览器检查覆盖：行内两个入口各自可用且互不依赖；1280/1440/1920 下四个按钮直接可见、文字未截断、单行排列、间距不重叠、操作列宽于按钮组且表格无需横向滚动；1024px 窄窗口出现横向滚动后操作列仍固定在右侧且按钮完整；状态、修订号列宽 ≤100px，地址列始终宽于名称列并随窗口变宽；超长名称与地址省略显示、悬停提示显示完整值、表格未被撑高；首页步骤说明指向“场景列表的‘版本与文件’”；场景信息弹窗只含关闭与保存、仍可看到名称与地址；行内“版本与文件”直接打开对应场景面板并显示场景名；“发布”后列表修订号刷新到新值；停用/启用填写原因后状态刷新；删除确认仍显示场景名且取消不删除；页面无 JS 错误、无未拦截请求。

本次未提升截图：1280/1440/1920 与 1024 横滚后的截图（同输入与数据，仅视口不同）以及逐项日志留在本机 `.local/scene-list-ui/`，文件名 `scenes-1920.png`、`scenes-1440.png`、`scenes-1280.png`、`scenes-1024-scrolled.png`、`scenes-1440-interaction.png` 与 `verify_scene_list_ui.log`。需要随审查共享时由验收人从该目录脱敏后取用。

容器没有系统浏览器运行库，也没有 root：本轮在 `/tmp/browser-sysroot`、`/tmp/browser-libs`、`/tmp/browser-fonts` 中解包 Debian 运行库与 Noto CJK 字体，通过 `LD_LIBRARY_PATH`/`FONTCONFIG_FILE` 驱动 Playwright 自带的 Chromium，并用未提交的 `.local/run_scene_ui_check.py` 追加 `--no-sandbox`。这些内容都在 `.local/` 与 `/tmp`，不属于仓库改动，也不在宿主重现。

## 未覆盖与限制

- 合成响应不证明真实发布、上传、下载、ZIP、文件删除、删除恢复、审计与鉴权行为；这些仍需后端参与。
- 未执行 Windows ingestion、Edge 真实后端登录点击、真实数据库、Docker/LAN、部署与 Addressables 客户端加载。
- 本容器构建墙钟时间明显长于宿主（user 时间仅约 28 秒），因此 `check --profile frontend` 的固定超时与宿主结论可能不同。
- 独立代码审查、宿主三视口观感与本机人工点击仍待完成。

## Windows 隔离验收步骤

在本 PR 最终提交的独立 checkout 中准备 PostgreSQL 17、JDK 21、Maven 离线依赖、Redis、Edge、任务自己的 Python/前端依赖与 Playwright；不要操作日常 Demo、LAN Compose 或真实账号，也不要为通过检查而启用已退役的 bootstrap 账号。

```powershell
npm --prefix frontend ci --prefer-offline --no-audit --no-fund
.local/venv/Scripts/python.exe scripts/harness.py doctor --profile quick
.local/venv/Scripts/python.exe scripts/harness.py check --profile quick
.local/venv/Scripts/python.exe scripts/harness.py check --profile frontend
.local/venv/Scripts/python.exe scripts/harness.py doctor --profile ingestion
.local/venv/Scripts/python.exe scripts/harness.py check --profile ingestion
.local/venv/Scripts/python.exe scripts/verify_scene_list_ui.py --report-dir .local
```

`ingestion` 的浏览器流程已改为点行内“场景信息/版本与文件”，并断言 1280/1440/1920 的列宽、按钮单行与间距；该 profile 需要 Windows 依赖，本容器未执行。

人工核对：

1. 1280、1440、1920 视口下“场景信息／版本与文件／启用或停用／删除”全部直接可见，无重叠、截断或非预期换行。
2. “场景信息”弹窗只有“关闭、保存”，名称、地址、坐标可保存；弹窗内没有“版本与文件”。
3. 行内“版本与文件”直接打开对应场景的资源面板并显示正确场景名；发布后关闭面板，列表修订号与状态已刷新。
4. 超长名称与地址省略显示，悬停可查看完整内容，表格未被撑破。
5. 窄窗口出现横向滚动时操作列固定在右侧且按钮完整可点。
6. 停用/启用原因校验与删除确认保持原行为，上传、下载、发布、删除规则未变。

## 保留文件

下表 SHA256 在 2026-09-20 自查后计算，只标识本目录内容，不是业务源码指纹。

| 文件 | SHA256 |
|---|---|
| [validation-scene-list-ui.json](validation-scene-list-ui.json) | `b3f85a849992ff0b3c0c4d92a5ef3c449f9f472e24d03e8387ed5b8fcc56dad0` |

状态：容器内实现自查通过；独立代码审查、Windows ingestion 与宿主浏览器验收待完成。
