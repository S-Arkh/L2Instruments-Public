"""Hash-pinned texture-only installation and recoverable rollback (standard library)."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import copy


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe(root, relative):
    p = PurePosixPath(relative)
    if '\\' in relative or p.is_absolute() or len(p.parts) != 2 or p.parts[0] != 'SysTextures' or p.suffix.lower() != '.utx':
        raise ValueError(f'Invalid texture path: {relative}')
    result = root.joinpath(*p.parts).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Path escapes root')
    return result


def atomic_copy(source, target):
    fd, temp = tempfile.mkstemp(prefix='.pinkdream-', dir=target.parent)
    os.close(fd)
    temp = Path(temp)
    try:
        shutil.copy2(source, temp)
        if sha(temp) != sha(source):
            raise ValueError('Copy verification failed')
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def journal_write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def install(client, bundle, backup=None, check=False, from_bundle=None):
    client, bundle = client.resolve(), bundle.resolve()
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    files = copy.deepcopy(manifest['files'])
    if from_bundle:
        previous = json.loads((from_bundle / 'manifest.json').read_text(encoding='utf-8'))
        if not manifest.get('library_sha256') or previous.get('library_sha256') != manifest['library_sha256']:
            raise ValueError('Theme switch requires the same standard source library')
        if previous['profile'] != manifest['profile'] or {f['path'] for f in previous['files']} != {f['path'] for f in files}:
            raise ValueError('Theme switch profile/package mismatch')
        previous_files = {f['path']: f for f in previous['files']}
        for f in files:
            old = previous_files[f['path']]
            if sha(safe(from_bundle, f['path'])) != old['sha256']:
                raise ValueError('Previous theme bundle hash mismatch')
            f['accepted_input_sha256'] = list(set(f.get('accepted_input_sha256', [f['original_sha256']]) + [old['sha256']]))
    if not files or len({f['path'].lower() for f in files}) != len(files):
        raise ValueError('Empty or duplicate package list')
    for f in files:
        if sha(safe(bundle, f['path'])) != f['sha256']:
            raise ValueError(f'Bundle hash mismatch: {f["path"]}')
        actual = sha(safe(client, f['path']))
        if actual not in f.get('accepted_input_sha256', [f['original_sha256']]):
            raise ValueError(f'Client differs from original: {f["path"]}')
        # Journal pins the exact pre-install version, not just the theme's reference package.
        f['original_sha256'] = actual
    if check:
        return {'status': 'check-passed', 'files': len(files)}
    if backup is None:
        raise ValueError('--backup is required for installation')
    backup = backup.resolve()
    backup.mkdir(parents=True, exist_ok=False)
    # All verified originals are saved before replacing the first client file.
    for f in files:
        dst = safe(backup, f['path'])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe(client, f['path']), dst)
        if sha(dst) != f['original_sha256']:
            raise ValueError('Backup verification failed; client untouched')
    journal = {'schema': 1, 'client': str(client), 'profile': manifest['profile'],
               'revision': manifest['revision'], 'status': 'installing', 'files': files}
    journal_write(backup / 'journal.json', journal)
    try:
        for f in files:
            dst = safe(client, f['path'])
            if sha(dst) != f['original_sha256']:
                raise ValueError('Client changed during installation')
            atomic_copy(safe(bundle, f['path']), dst)
        journal['status'] = 'installed'
        journal_write(backup / 'journal.json', journal)
    except Exception:
        # A durable journal exists even if installation stops halfway.
        rollback(backup)
        raise
    return journal


def rollback(backup):
    backup = backup.resolve()
    path = backup / 'journal.json'
    journal = json.loads(path.read_text(encoding='utf-8'))
    client = Path(journal['client'])
    for f in journal['files']:
        if sha(safe(backup, f['path'])) != f['original_sha256']:
            raise ValueError('Backup hash mismatch')
        if sha(safe(client, f['path'])) not in (f['sha256'], f['original_sha256']):
            raise ValueError(f'Client file changed after installation: {f["path"]}')
    for f in journal['files']:
        dst = safe(client, f['path'])
        current = sha(dst)
        if current not in (f['sha256'], f['original_sha256']):
            raise ValueError('Client changed during rollback')
        if current != f['original_sha256']:
            atomic_copy(safe(backup, f['path']), dst)
    journal['status'] = 'rolled-back'
    journal_write(path, journal)
    return journal


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    put = sub.add_parser('install')
    put.add_argument('--client', required=True, type=Path)
    put.add_argument('--bundle', required=True, type=Path)
    put.add_argument('--backup', type=Path)
    put.add_argument('--check', action='store_true')
    put.add_argument('--from-bundle', type=Path, help='Installed theme bundle from the same standard library')
    undo = sub.add_parser('rollback')
    undo.add_argument('--backup', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'install':
        result = install(args.client, args.bundle, args.backup, args.check, args.from_bundle)
    else:
        result = rollback(args.backup)
    print(result['status'])
