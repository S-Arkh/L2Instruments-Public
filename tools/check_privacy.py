"""Reject publication secrets and environment-specific metadata without printing values."""
import argparse
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {
    'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/]{32,}',
    'GitHub credential': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
    'AWS credential': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'service credential': r'\b(?:sk-[A-Za-z0-9_-]{32,}|xox[baprs]-[A-Za-z0-9-]{20,})\b',
}
METADATA = {
    'personal email': r'\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
    'user directory': r'(?<![\w/])(?:/(?:home|Users)/[\w.-]+|[A-Za-z]:[\\/]+Users[\\/]+[\w.-]+)',
    'mounted local directory': r'/mnt/[a-z]/',
    'development date': r'\b20\d{2}[-/]\d{2}[-/]\d{2}(?:T[\d:.+-]+Z?)?\b|\b20\d{6}\b',
    'conversation transcript': r'(?im)^\s*(?:<\|(?:im_start|im_end)\|>|<system-reminder>|(?:user|assistant|system)\s*:\s)',
}


def inspect(name, data, dependency=False):
    # Credentials are checked even in dependency files and binary ASCII strings.
    text = data.decode('utf-8', errors='replace')
    patterns = dict(SECRETS)
    license_file = any(word in name.lower() for word in ('license', 'authors', 'third_party', 'notices', 'copying'))
    if not dependency and not license_file and b'\0' not in data:
        patterns.update(METADATA)
    findings = []
    for label, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            line = text.count('\n', 0, match.start()) + 1
            if label == 'personal email' and Path(name).name == 'BUILDINFO.json':
                start = text.rfind('\n', 0, match.start()) + 1
                end = text.find('\n', match.end())
                source_line = text[start:end if end >= 0 else len(text)]
                # Qt high-DPI image filenames are manifest keys, not email addresses.
                asset = re.search(r'"packages/PySide6/[^"\n]+@[23]x\.png"\s*:', source_line)
                if asset and asset.start() <= match.start() - start and match.end() - start <= asset.end():
                    continue
            findings.append(f'{name}:{line}: {label}')
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--revision', help='Scan every file in a Git revision')
    mode.add_argument('--archive', type=Path, help='Scan a release ZIP, including bundled sources')
    args = parser.parse_args()
    findings = []
    count = 0
    if args.archive:
        with zipfile.ZipFile(args.archive) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                parts = Path(entry.filename).parts[1:]
                dependency = bool(parts and parts[0] in {'runtime', 'packages', 'licenses'})
                findings.extend(inspect(entry.filename, archive.read(entry), dependency))
                count += 1
    else:
        command = ['git', 'ls-tree', '-r', '--name-only', '-z', args.revision] if args.revision else [
            'git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z']
        names = subprocess.check_output(command, cwd=ROOT).decode().split('\0')
        for name in sorted(set(names) - {''}):
            if args.revision:
                data = subprocess.check_output(['git', 'show', f'{args.revision}:{name}'], cwd=ROOT)
            else:
                path = ROOT / name
                if not path.is_file():
                    continue
                data = path.read_bytes()
            findings.extend(inspect(name, data))
            count += 1
    if findings:
        raise SystemExit('\n'.join(findings))
    print(f'PASS: privacy patterns checked in {count} files')


if __name__ == '__main__':
    main()
