"""Compare eager and lazy schema loading in isolated processes; emit anonymous metrics."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))


def worker(mode, sample, schema):
    from _interface_core import Document
    from schema_catalog import catalog_text
    def timed(fn):
        start = time.perf_counter()
        value = fn()
        return value, (time.perf_counter() - start) * 1000
    def peak_memory():
        if sys.platform == 'linux':
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in ('peak', 'working', 'peak_pool', 'pool',
                                                       'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL('kernel32')
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL('psapi')
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                raise ctypes.WinError()
            return counters.peak // 1024
        raise RuntimeError('Memory measurement supports Linux and Windows')
    memory_before = peak_memory()
    if mode == 'eager':
        text, startup = timed(catalog_text)
        versions = json.loads(text)['versions']
        get_text = lambda key: text
    else:
        from schema_catalog import SchemaRepository
        repository, startup = timed(SchemaRepository)
        versions = repository.versions
        get_text = repository.text
    memory_startup = peak_memory()
    _, first_profile = timed(lambda: get_text(schema))
    _, cached_profile = timed(lambda: get_text(schema))
    doc, construct = timed(lambda: Document(get_text(schema)))
    memory_document = peak_memory()
    data = Path(sample).read_bytes()
    _, opening = timed(lambda: doc.load_bytes(data, schema))
    def reopen():
        other = Document(get_text(schema))
        other.load_bytes(data, schema)
    _, repeated_open = timed(reopen)
    rows = []
    def analyze():
        document = Document(text) if mode == 'eager' else None
        for candidate in dict.fromkeys(key for _, key in versions):
            if mode == 'lazy':
                document = Document(get_text(candidate))
            result = document.probe(data, candidate)
            rows.append((candidate, result['compatible'], result['tail_bytes']))
    _, detection = timed(analyze)
    result = dict(startup_ms=startup, first_profile_ms=first_profile,
                  cached_profile_ms=cached_profile, document_ms=construct,
                  open_ms=opening, repeated_open_ms=repeated_open, detection_ms=detection,
                  baseline_peak_kib=memory_before, startup_peak_kib=memory_startup,
                  document_peak_kib=memory_document,
                  schema_peak_delta_kib=memory_document - memory_before,
                  peak_rss_kib=peak_memory(), candidates=rows)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['eager', 'lazy'], required=True)
    parser.add_argument('--sample', type=Path, required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--repeat', type=int, default=5)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.mode, args.sample, args.schema)))
        return
    if args.repeat < 1:
        parser.error('--repeat must be positive')
    runs = [json.loads(subprocess.check_output([
        sys.executable, __file__, '--worker', '--mode', args.mode,
        '--sample', str(args.sample), '--schema', args.schema], text=True))
        for _ in range(args.repeat)]
    result = {'mode': args.mode, 'schema': args.schema, 'platform': sys.platform,
              'cache_note': 'Fresh process per run; OS filesystem cache is not flushed.', 'runs': runs,
              'summary': {key: {'median': statistics.median(r[key] for r in runs),
                                'min': min(r[key] for r in runs),
                                'max': max(r[key] for r in runs)}
                          for key in runs[0] if key != 'candidates'}}
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
