"""Prepare pinned Symphony v0.0.3 Chinese UI modules; never restart the service."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.local/symphony/source/elixir/lib/symphony_elixir_web'
OUTPUT = ROOT / '.local/symphony/data/ui-zh-CN'
FILES = {
    'live/dashboard_live.ex': '53e791aba1b1088b5786ca798f898429bbb72c56aacc6f8bd773b7fda5ee1860',
    'components/layouts.ex': '2c70c0dfffd30ce11bd0389a7c7ee40af0245a19b8cc361f17d1a12b22c57eb8',
}
TEXT = {
    'Symphony Observability': 'Symphony 运行监控',
    'Operations Dashboard': '运行监控面板',
    'Current state, retry pressure, token usage, and orchestration health for the active Symphony runtime.': '查看 Symphony 当前的任务状态、重试队列、Token 用量与调度运行情况。',
    'Snapshot unavailable': '暂时无法获取状态快照',
    'Active issue sessions in the current runtime.': '当前正在执行的任务会话。',
    'Issues waiting for the next retry window.': '等待下一次重试的任务。',
    'Issues paused for operator input or approval.': '等待人工输入或批准的任务。',
    'Total Codex runtime across completed and active sessions.': '已完成及运行中会话的 Codex 累计运行时长。',
    'Latest upstream rate-limit snapshot, when available.': '显示上游最近返回的用量限制信息（如有）。',
    'Active issues, last known agent activity, and token usage.': '查看执行中的任务、Agent 最新活动与 Token 用量。',
    'Issues paused because Codex requested operator input or approval.': '因 Codex 请求人工输入或批准而暂停的任务。',
    'No active sessions.': '暂无运行中的会话。',
    'No blocked sessions.': '暂无等待人工处理的会话。',
    'No issues are currently backing off.': '暂无等待重试的任务。',
    'Running sessions': '运行中的会话',
    'Blocked sessions': '等待人工处理的会话',
    'Retry queue': '重试队列',
    'Rate limits': '用量限制',
    'Total tokens': '累计 Token',
    'Runtime / turns': '运行时长 / 轮次',
    'Codex update': 'Codex 最新动态',
    'JSON details': 'JSON 详情',
    'Copy ID': '复制会话 ID',
    "'Copied'": "'已复制'",
    '>Running<': '>运行中<',
    '>Retrying<': '>等待重试<',
    '>Blocked<': '>等待人工处理<',
    '>Runtime<': '>累计运行时长<',
    '>Issue<': '>任务<',
    '>State<': '>状态<',
    '>Session<': '>会话<',
    '>Tokens<': '>Token 用量<',
    '>Blocked at<': '>暂停时间<',
    '>Last update<': '>最新动态<',
    '>Error<': '>错误信息<',
    '>Attempt<': '>重试次数<',
    '>Due at<': '>下次重试时间<',
    '>Total: ': '>合计：',
    'In <%= ': '输入 <%= ',
    ' / Out <%= ': ' / 输出 <%= ',
    '              Live\n': '              实时更新\n',
    '              Offline\n': '              连接已断开\n',
    '"n/a"': '"暂无数据"',
    '>n/a<': '>暂无数据<',
    '"#{mins}m #{secs}s"': '"#{mins} 分 #{secs} 秒"',
    '"Open #{@identifier} in the issue tracker"': '"在任务跟踪系统中打开 #{@identifier}"',
    '<html lang="en">': '<html lang="zh-CN">',
}
HELPERS = '''
  # Translate display values only. Keep API payloads, badge rules and raw logs intact.
  defp display_state(value) do
    Map.get(%{
      "open" => "待处理", "closed" => "已关闭", "running" => "运行中",
      "in progress" => "进行中", "active" => "进行中", "blocked" => "等待人工处理",
      "todo" => "待办", "queued" => "已排队", "pending" => "等待中",
      "retrying" => "等待重试", "done" => "已完成", "completed" => "已完成",
      "failed" => "失败", "error" => "错误", "cancelled" => "已取消"
    }, String.downcase(to_string(value)), value)
  end

  defp display_event(value) do
    Map.get(%{
      "notification" => "通知", "session_started" => "会话已启动",
      "turn_started" => "本轮已开始", "turn_completed" => "本轮已完成",
      "turn_failed" => "本轮失败", "turn_cancelled" => "本轮已取消",
      "token_usage" => "Token 用量更新", "session_failed" => "会话失败"
    }, to_string(value), value || "暂无数据")
  end

  defp display_error("Snapshot timed out"), do: "获取状态快照超时"
  defp display_error("Snapshot unavailable"), do: "暂时无法获取状态快照"
  defp display_error(value), do: value

'''


def prepare():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for relative, expected in FILES.items():
        path = SOURCE / relative
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError(f'Upstream source changed; review translations before applying: {relative}')
        source = raw.decode('utf-8').replace('\r\n', '\n')
        for before, after in TEXT.items():
            source = source.replace(before, after)
        if path.name == 'dashboard_live.ex':
            source = source.replace('<%= entry.state %>', '<%= display_state(entry.state) %>')
            source = source.replace('<%= entry.state || "Blocked" %>', '<%= display_state(entry.state || "Blocked") %>')
            source = source.replace('<%= entry.last_event || "暂无数据" %>', '<%= display_event(entry.last_event) %>')
            source = source.replace('<%= @payload.error.message %>', '<%= display_error(@payload.error.message) %>')
            source = source.replace('  defp load_payload do', HELPERS + '  defp load_payload do')
        target = OUTPUT / path.name
        target.write_text(source, encoding='utf-8', newline='\n')
        manifest[path.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


def compile_modules(container, verify=False):
    # Existing Burrito runtime; compile in a separate VM, never hot-load the scheduler.
    root = '/opt/symphony/.burrito/symphony_erts-16.4_0.0.3'
    code = """Application.ensure_all_started(:phoenix_live_view)
File.mkdir_p!("/data/ui-zh-CN/ebin")
for file <- ["layouts.ex", "dashboard_live.ex"], {module, binary} <- Code.compile_file("/data/ui-zh-CN/" <> file) do
  File.write!("/data/ui-zh-CN/ebin/" <> Atom.to_string(module) <> ".beam", binary)
  IO.puts("Compiled " <> Atom.to_string(module))
end
"""
    if verify:
        code += """
base = %{counts: %{running: 0, retrying: 0, blocked: 0}, codex_totals: %{total_tokens: 0, input_tokens: 0, output_tokens: 0, seconds_running: 0}, rate_limits: nil, running: [], blocked: [], retrying: []}
render = fn payload -> SymphonyElixirWeb.DashboardLive.render(%{__changed__: nil, payload: payload, now: DateTime.utc_now()}) |> Phoenix.HTML.Safe.to_iodata() |> IO.iodata_to_binary() end
empty = render.(base)
for label <- ["运行监控面板", "暂无运行中的会话。", "暂无等待人工处理的会话。", "暂无等待重试的任务。"] do
  unless String.contains?(empty, label), do: raise("Missing empty label: " <> label)
end
entry = %{issue_identifier: "GH-TEST", issue_url: "https://example.com/issue", state: "open", session_id: "session-test", started_at: DateTime.utc_now(), turn_count: 2, last_message: "raw diagnostic preserved", last_event: "notification", last_event_at: nil, tokens: %{total_tokens: 3, input_tokens: 2, output_tokens: 1}, blocked_at: nil, error: "raw error preserved", attempt: 1, due_at: nil}
rows = render.(%{base | running: [entry], blocked: [entry], retrying: [entry]})
for label <- ["待处理", "通知", "复制会话 ID", "已复制", "重试次数", "暂停时间", "raw diagnostic preserved", "raw error preserved", "session-test"] do
  unless String.contains?(rows, label), do: raise("Missing row label: " <> label)
end
error = render.(%{error: %{code: "snapshot_timeout", message: "Snapshot timed out"}})
unless String.contains?(error, "获取状态快照超时"), do: raise("Missing translated error")
IO.puts("PASS: empty/running/blocked/retry/error templates; raw diagnostics preserved")
"""
    subprocess.run([
        'docker', 'exec', '-e', 'ROOTDIR=' + root,
        '-e', 'BINDIR=' + root + '/erts-16.4/bin', '-e', 'EMU=beam', '-e', 'PROGNAME=erl',
        container, root + '/erts-16.4/bin/erlexec',
        '-boot', root + '/releases/0.0.3/start_clean', '-boot_var', 'RELEASE_LIB', root + '/lib',
        '-noshell', '-pa', root + '/lib/*/ebin', '-s', 'elixir', 'start_cli', '-extra', '-e', code,
    ], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile', action='store_true', help='Compile in a separate VM; do not install or restart')
    parser.add_argument('--verify', action='store_true', help='Compile and render synthetic dashboard states')
    parser.add_argument('--container', default='innovation-symphony')
    args = parser.parse_args()
    prepare()
    if args.compile or args.verify:
        compile_modules(args.container, verify=args.verify)
