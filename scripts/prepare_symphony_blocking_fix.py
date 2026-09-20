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


def patch_source(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED:
        raise ValueError('Upstream fingerprint changed; review blocker patch before applying')
    source = raw.decode('utf-8')
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
    return source


def prepare():
    source = patch_source(SOURCE.read_bytes())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'orchestrator.ex').write_text(source, encoding='utf-8', newline='\n')
    (OUTPUT / 'verify.exs').write_bytes(Path(__file__).with_name('verify_symphony_blocking.exs').read_bytes())
    manifest = {'upstreamSha256': EXPECTED, 'patchedSha256': hashlib.sha256(source.encode()).hexdigest()}
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def verify(container):
    root = '/opt/symphony/.burrito/symphony_erts-16.4_0.0.3'
    code = '''
File.mkdir_p!("/data/blocking-fix/ebin")
for {module, binary} <- Code.compile_file("/data/blocking-fix/orchestrator.ex") do
  File.write!("/data/blocking-fix/ebin/" <> Atom.to_string(module) <> ".beam", binary)
end
Code.require_file("/data/blocking-fix/verify.exs")
'''
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
    args = parser.parse_args()
    print(json.dumps(prepare()))
    if args.verify:
        verify(args.container)
