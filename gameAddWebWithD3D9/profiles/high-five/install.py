"""Install the profiled HF browser texture kit, or restore an installation backup."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def locate(directory, name):
    matches = [p for p in directory.iterdir() if p.name.casefold() == name.casefold()]
    if len(matches) > 1:
        raise ValueError(f'Ambiguous filename: {name}')
    return matches[0] if matches else directory / name

def install(system, package, profile, backup_root, check=False):
    system = system.resolve(strict=True)
    for name, expected in profile['required_client_files'].items():
        path = locate(system, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'Unsupported {name}: use the matching client/Core profile')
    for name, allowed in profile['supported_ui_inputs'].items():
        path = locate(system, name)
        if not path.is_file() or digest(path) not in allowed:
            raise ValueError(f'Custom/unknown {name}: rebuild the UI integration from this client first')
    for name, info in profile['files'].items():
        if Path(name).name != name or digest(package / name) != info['sha256']:
            raise ValueError(f'Package verification failed: {name}')
    selected = []
    for name in profile['files']:
        target = locate(system, name)
        if name == 'options.config' and target.exists():
            continue  # preserve extension configuration on upgrades
        selected.append((name, target))
    if check:
        return dict(profile=profile['profile'], files=[n for n, _ in selected], check_only=True)
    backup = backup_root / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, exist_ok=False)
    record = dict(system=str(system), profile=profile['profile'], entries=[])
    for name, target in selected:
        existed = target.exists()
        if existed:
            shutil.copy2(target, backup / name)
        record['entries'].append(dict(name=name, target_name=target.name, existed=existed,
            before=digest(target) if existed else None, after=profile['files'][name]['sha256']))
    record_file = backup / 'installation.json'
    record_file.write_text(json.dumps(record, indent=2), encoding='utf-8')
    written = []
    try:
        for name, target in selected:
            written.append((name, target))
            shutil.copy2(package / name, target)
            if digest(target) != profile['files'][name]['sha256']:
                raise OSError(f'Installed hash mismatch: {name}')
    except Exception:
        for name, target in reversed(written):
            source = backup / name
            if source.exists():
                shutil.copy2(source, target)
            elif target.exists():
                target.unlink()
        raise
    return dict(profile=profile['profile'], installed=len(selected), backup=str(backup))

def restore(backup):
    record = json.loads((backup / 'installation.json').read_text(encoding='utf-8'))
    system = Path(record['system'])
    # Verify all entries before restoring any, including backup integrity.
    for item in record['entries']:
        if Path(item['name']).name != item['name'] or Path(item['target_name']).name != item['target_name']:
            raise ValueError('Invalid backup filename')
        target = system / item['target_name']
        if not target.is_file() or digest(target) != item['after']:
            raise ValueError(f"Changed since install: {target}; restore manually from backup")
        if item['existed'] and digest(backup / item['name']) != item['before']:
            raise ValueError('Backup hash mismatch')
    for item in record['entries']:
        target = system / item['target_name']
        if item['existed']:
            shutil.copy2(backup / item['name'], target)
        else:
            target.unlink()
    return dict(restored=str(system))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--system', type=Path)
    group.add_argument('--restore', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate client/package without installing')
    args = parser.parse_args()
    if args.restore:
        if args.check: parser.error('--check is only for --system')
        result = restore(args.restore)
    else:
        profile = json.loads((ROOT / 'result/manifest.json').read_text())
        result = install(args.system, ROOT / 'result/system', profile, ROOT / 'backups', args.check)
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
