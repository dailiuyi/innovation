# GH-4 默认展示发布版本文件

实现基线：`50855415008e42dd12d01c050c55b377bcfa28ff`。分支：`codex/issue-4`。

页面首次进入优先恢复当前场景 URL 的手动选择，否则选中列表响应中的发布版本（不依赖分页中的草稿行）。普通刷新不自动切回发布版本；发布成功重新选择当前发布指针。场景切换使旧初始化、选择和文件请求失效，并清空文件与清单。已发布文件冻结及说明编辑规则保持原样。

## Linux 实现自查

命令：`.local/venv/bin/python scripts/harness.py doctor --profile quick`、`.local/venv/bin/python scripts/harness.py check --profile quick`、`npm --prefix frontend ci --cache /tmp/gh4-npm-cache`、`.local/venv/bin/python scripts/harness.py check --profile frontend`。

组件回归使用实际组件脚本和模拟接口，覆盖乱序、默认选择（发布版本不在当前分页）、无发布、URL 恢复、手动选择后刷新、首次/替换发布与切换场景清空。它不证明浏览器渲染、登录或真实服务行为。完整结果、源码指纹和报告路径由 PR/Issue 进展记录交接；报告保留在 `.local/harness/`。

初次 doctor 与实现修改重叠，`sourceUnchanged=false`，结果 blocked，不能作为通过证据。首次默认缓存 `npm ci` 因 `/home/node/.npm` 不可写失败；改用可写临时缓存重试，不修改锁文件。

## Windows 待验收

在独立验收 checkout 检出 PR 最终提交，按开发工作流准备 PostgreSQL 17、JDK 21、Maven 离线依赖、Redis、Edge、Python 验证依赖及 Playwright。不要启动/停止日常 Demo，不连接真实账号和存储。

```powershell
npm --prefix frontend ci
python scripts/harness.py doctor --profile ingestion
python scripts/harness.py check --profile ingestion
```

检查新报告 `sourceUnchanged=true`、全部步骤及 skipped/blocked 项。新增浏览器断言从真实登录流程验证：无 draftId 进入已发布场景直接显示文件、说明按钮可用、替换发布显示新版本、手动切回草稿可管理且刷新保留选择。

还需在隔离测试环境人工核对：

1. 无发布场景显示尚未发布和创建入口。
2. 已发布场景从「编辑 → 版本与文件」进入即显示对应编号、发布状态及文件；无上传/删除文件入口，说明可保存。
3. 查看其他草稿，验证上传/删除及刷新不会跳回发布版本。
4. 当前查看旧版本时首次发布/替换发布其他草稿，核对文件切到新发布版本。
5. 网络减速后在两个场景之间切换（包括 A → B → A），旧文件立即消失，迟到响应不覆盖新场景。

状态：业务端到端验收待完成；独立代码审查待完成。Linux 无 Windows ingestion 运行依赖，未执行数据库验收、部署或客户端加载验证。
