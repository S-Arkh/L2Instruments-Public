"""Run make in a staged System, retaining the full log and printing diagnostics."""
import argparse
import os
from pathlib import Path
import subprocess
import hashlib
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('system', type=Path)
    parser.add_argument('--launcher', required=True, type=Path)
    parser.add_argument('--wine', type=Path)
    parser.add_argument('--rebuild-interface', action='store_true')
    args = parser.parse_args()
    system = args.system.resolve(strict=True)
    if args.rebuild_interface:
        if not (system.parent / 'source-preparation.json').is_file():
            raise ValueError('Rebuild is restricted to a prepared workspace')
        outputs = [p for p in system.iterdir() if p.name.casefold() == 'interface.u']
        if len(outputs) > 1:
            raise ValueError('Multiple Interface.u files with different case')
        for output in outputs:
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            backup = system.parent / 'Backups' / ('Interface.' + digest + '.u')
            backup.parent.mkdir(exist_ok=True)
            if not backup.exists():
                shutil.copy2(output, backup)
            elif hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
                raise ValueError('Backup checksum mismatch')
            output.unlink()
    system_arg = str(system)
    if args.wine and os.name != 'nt':
        system_arg = 'Z:' + system_arg.replace('/', '\\')
    # Native headers are generated build products in this staged SDK. Silent
    # answers UCC's header-update prompt so automation never waits for stdin.
    command = [str(args.launcher.resolve(strict=True)), '--system', system_arg, 'make', '-NoBind', '-Silent']
    if args.wine:
        command.insert(0, str(args.wine.resolve(strict=True)))
    log = system.parent / 'compile.log'
    with log.open('wb') as output:
        result = subprocess.run(command, cwd=system, stdout=output, stderr=subprocess.STDOUT, timeout=180)
    text = log.read_text(encoding='utf-8', errors='replace')
    for line in text.splitlines():
        if not line.startswith(('Parsing ', 'Compiling ', 'Importing Defaults')):
            print(line)
    print(f'UCC exit: {result.returncode}; full log: {log}')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
