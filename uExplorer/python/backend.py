"""ctypes transport and filesystem export. Package interpretation lives in C++."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def core_path():
    override = os.environ.get('UEXPLORER_CORE')
    candidates = [Path(override)] if override else []
    name = 'uexplorer_core.dll' if sys.platform == 'win32' else 'libuexplorer_core.so'
    candidates += [ROOT/'bin'/name, ROOT/'build/Release'/name, ROOT/'build'/name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError('C++ core not found. Run build.ps1 / CMake first.')


class Core:
    def __init__(self, library=None):
        self.library = Path(library) if library else core_path()
        self.dll = ctypes.CDLL(str(self.library))
        self.dll.ue_abi_version.restype = ctypes.c_int
        if self.dll.ue_abi_version() != 1:
            raise RuntimeError('Unsupported uExplorer core ABI')
        self.dll.ue_request.argtypes = [ctypes.c_char_p]
        self.dll.ue_request.restype = ctypes.c_void_p
        self.dll.ue_free.argtypes = [ctypes.c_void_p]
        self.dll.ue_free.restype = None

    def request(self, **payload):
        address = self.dll.ue_request(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        if not address:
            raise RuntimeError('C++ core allocation failure')
        try:
            result = json.loads(ctypes.string_at(address).decode('utf-8'))
        finally:
            self.dll.ue_free(address)
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'Unknown core failure'))
        return result


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def component(name):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
        raise ValueError(f'Unsafe/nonidentifier output component: {name!r}')
    if name.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(f'Reserved output component: {name}')
    return name


def targets(package, classes, destination):
    base = Path(destination).resolve()/component(Path(package).stem)/'Classes'
    paths = []
    for item in classes:
        parts = [component(part) for part in item['path'].split('.')]
        path = base.joinpath(*parts).with_suffix('.uc')
        if not path.resolve().is_relative_to(Path(destination).resolve()):
            raise ValueError('Export target escapes selected directory')
        paths.append(path)
    if len({str(p).casefold() for p in paths}) != len(paths):
        raise ValueError('Case-insensitive output filename collision')
    return paths


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.uexplorer-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def view_text(result, ansi_encoding='cp1251'):
    if result.get('raw_hex') is not None:
        raw = bytes.fromhex(result['raw_hex'])
        return raw.decode('utf-16' if result['encoding'] == 'utf-16' else ansi_encoding, errors='replace')
    return result['code']


def export_classes(core, package, classes, destination, dependencies=(), force=False,
                   overwrite=False, cancelled=lambda: False, progress=lambda *args: None):
    package = Path(package).resolve()
    paths = targets(package, classes, destination)
    if not overwrite:
        existing = [str(p) for p in paths if p.exists()]
        if existing:
            raise FileExistsError('Output exists: '+existing[0])
    report = {'package': str(package), 'sha256': sha256(package), 'classes': [], 'cancelled': False,
              'force_bytecode': force, 'dependencies': list(dependencies), 'core_sha256': sha256(core.library)}
    for index, (item, path) in enumerate(zip(classes, paths)):
        if cancelled():
            report['cancelled'] = True
            break
        progress(index, len(classes), item['path'])
        try:
            response = core.request(operation='decompile', path=str(package), class_id=item['id'],
                                    dependencies=list(dependencies), force_bytecode=force)
            result = response['result']
            report['diagnostics'] = response.get('diagnostics', [])
            data = bytes.fromhex(result['raw_hex']) if 'raw_hex' in result else result['code'].encode('utf-8')
            if not overwrite and path.exists():
                raise FileExistsError(f'Output appeared during export: {path}')
            atomic_write(path, data)
            row = {key: value for key, value in result.items() if key not in ('code', 'raw_hex')}
            row.update(file=str(path), output_sha256=hashlib.sha256(data).hexdigest())
            report['classes'].append(row)
        except Exception as error:
            report['classes'].append({'class': item['path'], 'status': 'failed', 'error': str(error)})
    progress(len(report['classes']), len(classes), 'Finished')
    report['counts'] = {status: sum(r['status'] == status for r in report['classes'])
                        for status in ('source', 'recovered', 'partial', 'failed')}
    # Reports are per operation and never silently replace an earlier export report.
    base = Path(destination).resolve()/component(package.stem)
    base.mkdir(parents=True, exist_ok=True)
    import datetime
    report_path = base/('export-report-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')
    atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    report['report_file'] = str(report_path)
    return report
