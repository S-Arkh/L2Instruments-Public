"""Run isolated client matrix workers; aggregate progress from stdout events."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from package_matrix import ROOT, atomic_write, component, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--profile', action='append', required=True)
    for name in ('compiler', 'launcher', 'library', 'out', 'report', 'export-cache'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('client-sort-profile', 'scoped-enum-profile', 'client-enum-profile', 'asset-root'):
        parser.add_argument('--'+name, action='append', default=[])
    args = parser.parse_args()
    if args.jobs < 1: parser.error('--jobs must be positive')
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'local') or out == ROOT/'local':
        parser.error('Output must be a new directory beneath uExplorer/local')
    labels = [component(item.split('=', 1)[0]) for item in args.profile]
    if len(set(labels)) != len(labels): parser.error('Duplicate client labels')
    out.mkdir(parents=True, exist_ok=args.resume)
    lock = threading.Lock(); rows = {}; statuses = dict.fromkeys(labels, 'QUEUED')
    if args.resume:
        for label in labels:
            if not (out/label/'results.json').is_file(): continue
            result = json.loads((out/label/'results.json').read_text(encoding='utf-8'))
            for row in result['packages']: rows[(row['profile'], row['file'])] = row
            if result['complete']: statuses[label] = 'DONE'

    def save():
        ordered = list(rows.values())
        complete = all(value == 'DONE' for value in statuses.values())
        data = json.dumps(dict(complete=complete, workers=statuses, packages=ordered), ensure_ascii=False, indent=2).encode('utf-8')
        try:
            atomic_write(out/'results.json', data)
            write_report(ordered, args.report, out/'results.json', complete)
            return True
        except OSError as error:
            # Reporting must not interrupt stdout consumption and abort a worker.
            # Retain a unique checkpoint even if the current report is held open.
            recovery = out/('results-recovery-'+uuid.uuid4().hex+'.json')
            recovery.write_bytes(data)
            print('REPORT WRITE ERROR:', str(error), 'checkpoint:', str(recovery), flush=True)
            return False

    def worker(profile):
        label = profile.split('=', 1)[0]
        if statuses[label] == 'DONE': return
        command = [sys.executable, '-B', str(ROOT/'tests/package_matrix.py'), '--profile', profile,
                   '--out', str(out/label), '--report', str(out/(label+'.txt')), '--json-progress']
        if args.resume:
            if (out/label/'inputs.json').is_file(): command.append('--resume')
            elif (out/label).exists():
                (out/label).rename(out/(label+'.bootstrap-'+uuid.uuid4().hex))
        for name in ('compiler', 'launcher', 'library', 'export-cache'):
            command += ['--'+name, str(getattr(args, name.replace('-', '_')).resolve())]
        for name in ('client-sort-profile', 'scoped-enum-profile', 'client-enum-profile', 'asset-root'):
            for value in getattr(args, name.replace('-', '_')):
                if name == 'asset-root' and value.split('=', 1)[0] != label: continue
                command += ['--'+name, value]
        with lock:
            statuses[label] = 'RUNNING'; save()
        try:
            with (out/(label+'.log')).open('a' if args.resume else 'w', encoding='utf-8') as log:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding='utf-8', errors='replace',
                                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                for line in process.stdout:
                    log.write(line); log.flush()
                    if line.startswith('MATRIX_ROW '):
                        row = json.loads(line[len('MATRIX_ROW '):])
                        with lock:
                            rows[(row['profile'], row['file'])] = row; save()
                    else:
                        print(line.rstrip(), flush=True)
                code = process.wait()
            result = json.loads((out/label/'results.json').read_text(encoding='utf-8'))
            with lock:
                for row in result['packages']: rows[(row['profile'], row['file'])] = row
                statuses[label] = 'DONE' if code == 0 and result['complete'] else 'ERROR'; save()
        except Exception as error:
            with lock:
                statuses[label] = 'ERROR'; save()
            print(label, 'WORKER ERROR', str(error), flush=True)

    with ThreadPoolExecutor(max_workers=min(args.jobs, len(labels))) as pool:
        list(pool.map(worker, args.profile))
    with lock:
        if not save(): raise RuntimeError('Checks finished but final report could not be updated; see recovery checkpoint')
    if any(value != 'DONE' for value in statuses.values()):
        raise RuntimeError('A matrix worker did not finish; inspect per-client logs')
    print('COMPLETE:', len(rows), 'packages; see aggregate report', flush=True)


if __name__ == '__main__':
    main()
