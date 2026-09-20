"""Prepare a fingerprint-pinned Symphony v0.0.3 blocker fix (no live mutation)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.local/symphony/source/elixir/lib/symphony_elixir/orchestrator.ex'
OUTPUT = ROOT / '.local/symphony/data/blocking-fix'
EXPECTED = 'a3cc9c67338e097eee9167e3ec88839a49850f8cf09f4c0529f05ca4e0b5d985'
APP_SERVER_EXPECTED = 'e51dd1af6f58883ebcea208f2786debb208363f6303d8b9bb00da2125a528cef'


def patch_source(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Upstream fingerprint changed; review blocker patch before applying')
    source = raw.decode('utf-8').replace('\r\n', '\n')
    replacements = [
        ('    Map.get(running_entry, :last_codex_event) in [:turn_input_required, :approval_required] or',
         '    Map.get(running_entry, :operator_input_event) in [:turn_input_required, :approval_required] or\n'
         '      Map.get(running_entry, :last_codex_event) in [:turn_input_required, :approval_required] or'),
        ('    codex_event_blocker_error(Map.get(running_entry, :last_codex_event)) ||',
         '    codex_event_blocker_error(Map.get(running_entry, :operator_input_event)) ||\n'
         '      codex_event_blocker_error(Map.get(running_entry, :last_codex_event)) ||'),
        ('        last_codex_event: event,',
         '        last_codex_event: event,\n'
         '        operator_input_event: Map.get(running_entry, :operator_input_event) || operator_input_event(update),'),
        ('  defp input_required_blocker?(running_entry) when is_map(running_entry) do',
         '  # Keep a blocker for this worker lifetime, even after error/usage notifications.\n'
         '  defp operator_input_event(%{event: event}) when event in [:turn_input_required, :approval_required], do: event\n'
         '  defp operator_input_event(%{event: :turn_ended_with_error, reason: {event, _}})\n'
         '       when event in [:turn_input_required, :approval_required], do: event\n'
         '  defp operator_input_event(_), do: nil\n\n'
         '  defp input_required_blocker?(running_entry) when is_map(running_entry) do'),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError('Unexpected upstream patch anchor')
        source = source.replace(before, after)
    guard = '''
  # Trusted state is outside agent writable workspaces; survives scheduler restart.
  defp locally_stopped?(%Issue{identifier: identifier}) when is_binary(identifier) do
    root = System.get_env("SYMPHONY_CONTROL_ROOT")
    if is_binary(root) and Regex.match?(~r/^GH-[1-9][0-9]*$/, identifier) do
      case File.read(Path.join([root, identifier, "state.json"])) do
        {:ok, body} ->
          case Jason.decode(body) do
            {:ok, %{"status" => status}} -> status in ["review", "blocked"]
            _ -> true
          end
        {:error, :enoent} -> false
        _ -> true
      end
    else
      false
    end
  end
  defp locally_stopped?(_), do: false

'''
    source = source.replace('  defp should_dispatch_issue?(\n', guard + '  defp should_dispatch_issue?(\n', 1)
    source = source.replace('    candidate_issue?(issue, active_states, terminal_states) and\n',
                            '    !locally_stopped?(issue) and candidate_issue?(issue, active_states, terminal_states) and\n', 1)
    anchor = '  defp handle_retry_issue_lookup(%Issue{} = issue, state, issue_id, attempt, metadata) do'
    start = source.index(anchor)
    index = source.index('    cond do\n', start) + len('    cond do\n')
    source = source[:index] + ('      locally_stopped?(issue) ->\n'
                              '        {:noreply, release_issue_claim(state, issue_id)}\n\n') + source[index:]
    return source


def prepare(source_path=SOURCE, output=OUTPUT):
    source = patch_source(source_path.read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    (output / 'orchestrator.ex').write_text(source, encoding='utf-8', newline='\n')
    (output / 'verify.exs').write_bytes(Path(__file__).with_name('verify_symphony_blocking.exs').read_bytes())
    app_raw = (source_path.parent / 'codex/app_server.ex').read_bytes()
    if hashlib.sha256(app_raw).hexdigest() != APP_SERVER_EXPECTED:
        raise ValueError('App Server upstream changed; review unlimited controlled wait patch')
    app_source = app_raw.decode('utf-8').replace('\r\n', '\n')
    anchor = '      Config.settings!().codex.turn_timeout_ms,'
    if app_source.count(anchor) != 1:
        raise ValueError('App Server timeout anchor changed')
    app_source = app_source.replace(anchor, '      controlled_turn_timeout(),')
    anchor = '  defp await_turn_completion(port, on_message, tool_executor, auto_approve_requests) do'
    app_source = app_source.replace(anchor, '''  # No wall-clock ceiling for controlled tasks; individual commands retain their limits.
  @doc false
  def controlled_turn_timeout do
    if System.get_env("SYMPHONY_CONTROL_ROOT"), do: :infinity, else: Config.settings!().codex.turn_timeout_ms
  end

''' + anchor)
    (output / 'app_server.ex').write_text(app_source, encoding='utf-8', newline='\n')
    manifest = {'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'upstreamSha256': EXPECTED, 'patchedSha256': hashlib.sha256(source.encode()).hexdigest(),
                'appServerUpstreamSha256': APP_SERVER_EXPECTED,
                'appServerPatchedSha256': hashlib.sha256(app_source.encode()).hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def verify(container, container_output='/data/blocking-fix'):
    root = '/opt/symphony/.burrito/symphony_erts-16.4_0.0.3'
    code = '''
directory = DIRECTORY
File.mkdir_p!(directory <> "/ebin")
for name <- ["orchestrator.ex", "app_server.ex"] do
  for {module, binary} <- Code.compile_file(directory <> "/" <> name) do
    File.write!(directory <> "/ebin/" <> Atom.to_string(module) <> ".beam", binary)
  end
end
Code.require_file(directory <> "/verify.exs")
'''.replace('DIRECTORY', json.dumps(container_output))
    subprocess.run([
        'docker', 'exec', '-e', 'ROOTDIR=' + root, '-e', 'BINDIR=' + root + '/erts-16.4/bin',
        '-e', 'EMU=beam', '-e', 'PROGNAME=erl', container, root + '/erts-16.4/bin/erlexec',
        '-boot', root + '/releases/0.0.3/start_clean', '-boot_var', 'RELEASE_LIB', root + '/lib',
        '-noshell', '-pa', root + '/lib/*/ebin', '-s', 'elixir', 'start_cli', '-extra', '-e', code,
    ], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--container', default='innovation-symphony')
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--container-output', default='/data/blocking-fix')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output)))
    if args.verify:
        verify(args.container, args.container_output)
        manifest_path = args.output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        modules = ['Elixir.SymphonyElixir.Orchestrator.beam', 'Elixir.SymphonyElixir.Codex.AppServer.beam']
        manifest['verifiedModules'] = {name: hashlib.sha256((args.output / 'ebin' / name).read_bytes()).hexdigest()
                                       for name in modules}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
