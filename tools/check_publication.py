"""Validate publishable files; optionally export a clean source tree without .git."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BINARY_EXCEPTIONS = {'interface_editor/third_party/windows/zlib1.dll'}
EXCLUDED = {'__pycache__', '.pytest_cache', '.venv', 'build', 'builds', 'dist',
            'bin', 'out', 'work', 'workspace', 'runtime', 'compiler', 'sdk',
            'toolchain', 'inputs', 'local', 'backups', 'recovered', 'stage',
            'result', '_audit'}
SUFFIXES = {'.exe', '.dll', '.pyd', '.so', '.a', '.lib', '.o', '.obj', '.pdb',
            '.log', '.bak', '.u', '.xdat', '.dat', '.utx', '.zip', '.7z', '.nupkg', '.pyc'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, help='New directory outside this repository')
    parser.add_argument('--report', type=Path, help='Write hash report outside this repository')
    args = parser.parse_args()
    for path in (args.export, args.report):
        if path and path.resolve().is_relative_to(ROOT):
            parser.error('Export/report must be outside the repository')
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    selected = sorted(set(paths.decode('utf-8').split('\0')) - {''})
    manifest = {}
    for name in selected:
        relative = Path(name)
        path = ROOT/relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing file or symlink: ' + name)
        if any(p in EXCLUDED or p.startswith(('build-', 'workspace-', 'prepared-', 'result-')) for p in relative.parts[:-1]):
            raise ValueError('Generated/input directory selected: ' + name)
        if relative.suffix.lower() in SUFFIXES and name not in BINARY_EXCEPTIONS:
            raise ValueError('Unexpected binary/artifact: ' + name)
        if path.stat().st_size >= 50 * 1024 * 1024:
            raise ValueError('Large publication file: ' + name)
        if relative.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=name)
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if args.export:
        args.export.mkdir(parents=True, exist_ok=False)
        for name in selected:
            output = args.export/name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/name, output)
    if args.report:
        args.report.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'PASS: {len(selected)} publication files; syntax/artifact/size checks')


if __name__ == '__main__':
    main()
