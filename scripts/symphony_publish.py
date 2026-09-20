"""Publish explicit workspace files through GitHub Git Data, without model transcription.

The generator has no credentials. The adapter supplies the existing github_api
transport; the host CLI uses gh's existing authentication. No automatic retries.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = '/repos/dailiuyi/innovation'
TOOL_NAME = 'github_publish_files'
TOOL_SPEC = {
    'name': TOOL_NAME,
    'description': 'Publish explicit relative file paths from this workspace to a codex/ branch. '
                   'Reads bytes itself, verifies blob hashes, preserves other files, never force pushes. '
                   'Use instead of copying file content into github_api. On failure stop and report; '
                   'do not retry unchanged arguments or switch to manual blobs.',
    'inputSchema': {'type': 'object', 'additionalProperties': False,
                    'required': ['branch', 'expected_head', 'paths', 'message'],
                    'properties': {
                        'branch': {'type': 'string'},
                        'expected_head': {'type': 'string', 'description': 'Verified remote head SHA; for a new branch the base commit SHA.'},
                        'paths': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 100},
                        'message': {'type': 'string'}}}}


class PublishError(ValueError):
    pass


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=15)
    if result.returncode:
        raise PublishError('git_preflight_failed')
    return result.stdout


def snapshot(root, paths):
    root = Path(root).resolve(strict=True)
    if Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != root:
        raise PublishError('workspace_is_not_git_root')
    if not isinstance(paths, list) or not 1 <= len(paths) <= 100:
        raise PublishError('invalid_paths')
    files = []
    seen = set()
    for name in paths:
        if (not isinstance(name, str) or not name or name.startswith('/') or
                any(c in name for c in '\\:\r\n\0') or
                any(part in ('', '.', '..') for part in name.split('/'))):
            raise PublishError('invalid_relative_path')
        parts = name.split('/')
        if (any(p.lower() in ('.git', '.local', '.codex', '.agents', 'node_modules', 'dist') for p in parts)
                or any(p.lower().startswith('.env') and p.lower() != '.env.example' for p in parts)):
            raise PublishError('runtime_or_secret_path')
        if name.casefold() in seen:
            raise PublishError('duplicate_path')
        seen.add(name.casefold())
        path = root
        for part in parts:
            path = path / part
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise PublishError('symlink_path')
        if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
            raise PublishError('path_outside_workspace_or_not_file')
        ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index', '-q', '--', name],
                                 stdin=subprocess.DEVNULL, capture_output=True, timeout=15).returncode
        if ignored != 1:
            raise PublishError('ignored_path_or_git_error')
        if path.stat().st_size > 1024 * 1024:
            raise PublishError('file_exceeds_1MiB')
        data = path.read_bytes()
        if len(data) > 1024 * 1024:
            raise PublishError('file_exceeds_1MiB')
        stage = git(root, 'ls-files', '--stage', '-z', '--', name)
        entries = [entry for entry in stage.split(b'\0') if entry]
        if len(entries) > 1 or (entries and entries[0].split(b'\t')[0].split()[2] != b'0'):
            raise PublishError('unmerged_path')
        mode = entries[0].split()[0].decode() if entries else '100644'
        if mode not in ('100644', '100755'):
            raise PublishError('unsupported_file_mode')
        files.append({'path': name, 'mode': mode, 'type': 'blob', 'sha': blob_sha(data), 'data': data})
    if sum(len(f['data']) for f in files) > 8 * 1024 * 1024:
        raise PublishError('batch_exceeds_8MiB')
    return files


def api_response(reply, allowed=(200, 201)):
    if not isinstance(reply, dict) or reply.get('status') not in allowed:
        status = reply.get('status') if isinstance(reply, dict) else None
        raise PublishError('github_request_failed_status_' + str(status))
    return reply.get('body')


def publish(root, args):
    """Yield github_api requests; receive {status, body}; return compact receipt."""
    if not isinstance(args, dict) or set(args) != {'branch', 'expected_head', 'paths', 'message'}:
        raise PublishError('invalid_arguments')
    branch, head, message = args['branch'], args['expected_head'], args['message']
    if (not isinstance(branch, str) or not re.fullmatch(r'codex/[A-Za-z0-9_-][A-Za-z0-9._/-]{0,150}', branch)
            or '..' in branch or '@{' in branch or '//' in branch
            or any(p.endswith(('.', '.lock')) or p.startswith('.') for p in branch.split('/')) or branch.endswith('/')):
        raise PublishError('invalid_codex_branch')
    if not isinstance(head, str) or not re.fullmatch('[0-9a-f]{40}', head):
        raise PublishError('invalid_expected_head')
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise PublishError('invalid_commit_message')
    files = snapshot(root, args['paths'])  # Complete all local checks before any network write.

    def request(method, path, body=None):
        result = {'method': method, 'path': REPO + path}
        if body is not None:
            result['body'] = body
        return result

    ref_path = '/git/ref/heads/' + branch
    ref = yield request('GET', ref_path)
    exists = ref.get('status') != 404
    if exists and api_response(ref)['object']['sha'] != head:
        raise PublishError('remote_head_changed_refresh_before_publish')
    base = api_response((yield request('GET', '/git/commits/' + head)))
    base_tree = base['tree']['sha']
    entries = []
    for file in files:
        blob = api_response((yield request('POST', '/git/blobs', {
            'encoding': 'base64', 'content': base64.b64encode(file['data']).decode('ascii')})))
        if blob['sha'] != file['sha']:
            raise PublishError('uploaded_blob_hash_mismatch')
        entries.append({k: file[k] for k in ('path', 'mode', 'type', 'sha')})
    tree = api_response((yield request('POST', '/git/trees', {'base_tree': base_tree, 'tree': entries})))
    if tree['sha'] == base_tree and exists:
        return {'status': 'unchanged', 'branch': branch, 'commit': head, 'files': entries}
    commit = api_response((yield request('POST', '/git/commits', {
        'message': message, 'tree': tree['sha'], 'parents': [head]})))
    if commit['tree']['sha'] != tree['sha'] or [p['sha'] for p in commit['parents']] != [head]:
        raise PublishError('commit_tree_or_parent_mismatch')
    # Check input stability before the only visible publication mutation.
    current = snapshot(root, args['paths'])
    if [(f['sha'], f['mode']) for f in current] != [(f['sha'], f['mode']) for f in files]:
        raise PublishError('workspace_changed_before_publish')
    ref = yield request('GET', ref_path)
    if exists:
        if api_response(ref)['object']['sha'] != head:
            raise PublishError('remote_head_changed_before_publish')
        api_response((yield request('PATCH', '/git/refs/heads/' + branch,
                                    {'sha': commit['sha'], 'force': False})))
    else:
        if ref.get('status') != 404:
            raise PublishError('branch_created_concurrently')
        api_response((yield request('POST', '/git/refs', {'ref': 'refs/heads/' + branch, 'sha': commit['sha']})))
    final = api_response((yield request('GET', ref_path)))
    if final['object']['sha'] != commit['sha']:
        raise PublishError('publication_head_unconfirmed_inspect_remote')
    return {'status': 'published', 'branch': branch, 'commit': commit['sha'], 'files': entries}


def gh_request(request):
    """Host-only transport. Never print gh stderr or read/export its token."""
    cmd = ['gh', 'api', '--method', request['method'], request['path']]
    body = request.get('body')
    if body is not None:
        cmd += ['--input', '-']
    result = subprocess.run(cmd, input=json.dumps(body).encode() if body is not None else None,
                            capture_output=True, timeout=60)
    try:
        value = json.loads(result.stdout)
    except ValueError:
        raise PublishError('gh_response_unavailable') from None
    if result.returncode:
        # gh REST error responses expose status without leaking authentication.
        return {'status': int(value.get('status', 0)), 'body': value}
    return {'status': 200, 'body': value}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    operation = publish(args.root, json.loads(args.request.read_text(encoding='utf-8-sig')))
    try:
        request = next(operation)
        while True:
            request = operation.send(gh_request(request))
    except StopIteration as done:
        args.receipt.write_text(json.dumps(done.value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(done.value, ensure_ascii=False))
        return 0
    except (PublishError, OSError, subprocess.TimeoutExpired, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, PublishError) else type(exc).__name__,
                          'next': 'Inspect remote branch before retry; no automatic retry.'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
