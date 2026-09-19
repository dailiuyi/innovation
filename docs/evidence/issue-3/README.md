# GH-3 场景操作记录中文动作

实现自查证据；独立代码审查、真实登录页面及 Windows 验收待完成。未合并、未部署，未操作日常 Demo、LAN、真实账号或存储。

## 映射依据

核对 `SceneService` 和 `DraftService` 全部审计写入，共 21 种当前动作。集中维护于 `frontend/src/utils/auditActions.js`，仅在动作列渲染时转换；历史记录不改数据库即可显示中文，未知代码原样回退。

| 动作代码 | 中文名称 |
|---|---|
| `CREATE` | 创建场景 |
| `UPDATE` | 编辑场景 |
| `DELETE` | 删除场景 |
| `SET_ENABLED` | 设置场景启用状态 |
| `DRAFT_CREATE` | 创建草稿 |
| `DRAFT_EDIT` | 编辑草稿说明 |
| `DRAFT_DELETE_REQUEST` | 请求删除草稿 |
| `DRAFT_DELETE` | 删除草稿 |
| `DRAFT_PUBLISH` | 发布草稿 |
| `FILE_REGISTER` | 登记文件 |
| `FILE_UPLOAD_START` | 开始上传文件 |
| `FILE_AVAILABLE` | 文件可用 |
| `FILE_FAILED` | 文件入库失败 |
| `FILE_RECONCILE` | 文件启动对账 |
| `FILE_DELETE_REQUEST` | 请求删除文件 |
| `FILE_DELETE_RETRY` | 重试删除文件 |
| `FILE_DELETE_FAILED` | 文件删除失败 |
| `FILE_DELETE` | 删除文件 |
| `COLLECTION_REPLACE_START` | 开始替换文件集合 |
| `COLLECTION_REPLACE_CANCEL` | 取消替换文件集合 |
| `COLLECTION_REPLACE_SWITCH` | 文件集合替换生效 |

- `SET_ENABLED` 同时涵盖启用和停用，具体前后状态仍在详情中。
- `DRAFT_EDIT` 仅修改说明；发布指针替换也使用 `DRAFT_PUBLISH`。
- 上传重试继续写 `FILE_UPLOAD_START`，没有单独的上传重试动作。
- `FILE_AVAILABLE` 表示正式文件校验通过；`FILE_FAILED` 涵盖传输、校验和存储失败，因此使用“文件入库失败”。没有独立的校验开始动作。
- `FILE_RECONCILE` 是启动核对，不意味着成功，结果与系统来源保留在原始详情中。
- 删除请求、删除失败、重试与完成分别保留对应文案；集合开始、取消和生效不混为同一阶段。
- 动作列宽 180px，Element Plus `show-overflow-tooltip` 保持单行，未知长代码溢出可悬停查看。刷新、分页、详情事件与原始数据不变，原浏览器选择器仍适用。

## 验证范围

环境：Linux、Python 3.11.2、Node 22.23.2、npm 10.9.8。无数据库变更，未运行 PostgreSQL，不能宣称 PostgreSQL 17 或业务端到端验收通过。

实现提交：`1bc0ac34f6bd3d3b432f585f78bdfecad3a2c7d5`。

源码基线：`50855415008e42dd12d01c050c55b377bcfa28ff` 加本 PR 展示改动；工作区检查时存在预期未提交修改。源码 SHA256：`e83c5ecd6fb794c2dc74c2b2acd212f21ec36c0b00b9e2600bb55883bbaeec99`。报告中的 `sourceUnchanged=true` 才作为通过证据。证据文档和截图在检查后补入，不改变被测前端源码。

命令：

```bash
.local/venv/bin/python scripts/harness.py doctor --profile quick
.local/venv/bin/python scripts/harness.py check --profile quick
npm_config_cache=/tmp/gh3-npm-cache npm --prefix frontend ci
.local/venv/bin/python scripts/harness.py check --profile frontend
```

- doctor quick：通过，`.local/harness/20260919T154118Z-nbjvoibg/report.json`。
- check quick：通过，`.local/harness/20260919T154336Z-uo98f0_g/report.json`；harness 回归、契约及文档链接通过。
- check frontend：通过，`.local/harness/20260919T155703Z-7d26_aag/report.json`（临时源码快照运行后复制保留）；harness、契约/链接、草稿面板回归和 Vue 生产构建全部 passed，无 skipped。源码指纹与上述 quick 完全一致，检查期间无变化。
- npm ci：通过；锁文件未修改。首次默认缓存 `/home/node/.npm` 不可写失败，改用临时缓存解决。依赖审计报告既有 12 项问题，本任务未升级依赖。
- 最初 doctor 报告 `20260919T153859Z-zc_besc1` 因执行期间源码改变而 blocked，已在稳定源码上重跑，不计为通过。
- Node 临时自查：从后端审计调用提取的 21 种动作均有中文；未知动作、`constructor`、`toString`、`__proto__` 均回退原文。

挂载盘首次 frontend 构建在 300 秒时限内未完成，报告 `20260919T154534Z-6qcuvxq_` 为 blocked（其余步骤 passed，源码未变）。仅将同锁文件依赖移至 `/tmp` 后的尝试 `20260919T155151Z-uprhwptb` 仍慢；在临时源码快照已通过后主动中止，退出 130，无完整报告，不计通过。

为排除挂载盘 I/O，在 `/tmp/gh3-validation` 从相同 Git 基线解包源码并逐字节覆盖本次三份改动，用同一 Python venv 和锁文件依赖运行原样的 `.local/venv/bin/python scripts/harness.py check --profile frontend`，未调整时限、测试或业务代码。首次临时快照通过报告 `20260919T155523Z-3pm_gb8z` 包含依赖符号链接，指纹不同；将该依赖路径在临时 Git exclude 中排除后重跑，最终 `20260919T155703Z-7d26_aag` 指纹与 quick 相同。原工作区依赖目录已恢复。临时源码快照不连接后端、账号、数据库或存储。

## Windows 待验收

在单独 Windows 验收 checkout 检出 PR head，按开发工作流准备 PostgreSQL 17、JDK 21、Redis、Maven 缓存、Edge 和 Python 依赖；不要操作日常 Demo。

```powershell
npm --prefix frontend ci
python scripts/harness.py doctor --profile quick
python scripts/harness.py check --profile quick
python scripts/harness.py check --profile frontend
python scripts/harness.py doctor --profile ingestion
python scripts/harness.py check --profile ingestion
```

检查 ingestion 报告中的源码指纹、实际 PostgreSQL 版本、skipped/blocked 项。该脚本退出会清理隔离进程；另外在专用、保持运行的验收实例中使用合成管理员正常登录，访问 `/admin/audits`：核对已有记录的中文动作，点击刷新和查看并比较原始详情；在 1440、768、390px 窗口及 150% 缩放下检查横向滚动、单行名称和长代码悬停提示，保存实际页面截图。不得通过造会话或重新启用退休账号绕过登录。

未知代码可在隔离组件合成响应中验证，不向真实审计库写入假记录。真实历史数据兼容性、登录鉴权、后端刷新和详情链路当前仍待验收。实现自查不能替代 `docs/14-code-review.md` 定义的独立审查。

## 隔离组件截图

使用真实 `audits.vue`、原请求模块、Element Plus 和 Pagination 挂载到临时 Vite 页面；Playwright 拦截审计 GET 请求返回 21 种动作及一条未知长代码的合成记录。未伪造登录会话，也未访问业务后端。为同时核对所有名称，合成响应一次返回全部 22 行，不作为分页后端契约验证。

Chromium 153.0.8010.12 / Playwright 1.63.0：1440、768、390px 宽度下，21 个中文动作均单行且无截断；未知代码保留原文、溢出 tooltip 完整；刷新新增一次 GET；查看/关闭详情正常且保留 `DRAFT_PUBLISH` 原始 JSON；无 pageerror。已人工查看截图。窄窗口其他列沿用原表格横向滚动。本轮未覆盖登录外壳及 150% 缩放。

首次浏览器启动缺系统库，已在 `/tmp` 解包依赖和中文字体解决；Vite 初次加载曾出现连接拒绝和超时，待实际页面可访问后重跑通过，未改变产品代码。临时 Vite 已停止。原始结果留在 `.local/issue-3-browser/result.json`，临时检查脚本为 `.local/issue-3-browser/check.py`。

- [1440px 组件截图](audits-1440.png)
- [768px 组件截图](audits-768.png)
- [390px 组件截图](audits-390.png)
- [未知长代码提示](unknown-tooltip.png)
