"""Generate test inputs from schema defaults and original, minimal test data.

No client document or extracted game tree is used as an input.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document, encode_dat


def generate():
    folder = ROOT / 'tests/fixtures'
    folder.mkdir(exist_ok=True)
    schema = (ROOT / 'schemas/schemas.json').read_text(encoding='utf-8')
    records = json.loads(schema)['records']
    manifest = []
    for name in records:
        if not name.endswith('.XDAT'):
            continue
        doc = Document(schema)
        doc.create(name)
        if name == 'ct26.XDAT':
            windows = next(n['id'] for n in doc.children(doc.summary()['root']) if n['name'] == 'windows')
            window = doc.add_configured(windows, 'ct26.Window', dict(name='LoginMenuWnd', size=1,
                size_absolute_values=1, size_absolute_width=300, size_absolute_height=240))
            controls = next(n['id'] for n in doc.children(window) if n['name'] == 'children')
            for index, button in enumerate(('btnCredit', 'btnOption')):
                doc.add_configured(controls, 'ct26.Button', dict(name=button, parentName='LoginMenuWnd',
                    size=1, size_absolute_values=1, size_absolute_width=98, size_absolute_height=30,
                    usePosition=1, relativePoint=0, anchorPoint=0, anchor_x=10, anchor_y=20+index*40,
                    normalTex='Synthetic.Missing.Button', buttonName=805))
            doc.add_configured(controls, 'ct26.TextBox', dict(name='TestTextBox', parentName='LoginMenuWnd'))
        data = doc.serialize()
        filename = 'Interface_high_five.xdat' if name == 'ct26.XDAT' else name + '.xdat'
        (folder / filename).write_bytes(data)
        manifest.append(dict(file=filename, schema=name, sha256=hashlib.sha256(data).hexdigest(), synthetic=True))
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    strings = folder / 'sysstring'
    strings.mkdir(exist_ok=True)
    for filename, rows in [('original.dat', [(805, 'Credit')]),
                           ('fileedit.dat', [(805, 'Credit'), (6000, 'Test Button')])]:
        payload = struct.pack('<I', len(rows))
        for ident, text in rows:
            raw = text.encode('ascii') + b'\0'
            payload += struct.pack('<I', ident) + bytes([len(raw)]) + raw
        payload += b'\x0cSafePackage\0'
        (strings / filename).write_bytes(encode_dat(payload, filename, 413, 'l2encdec', True))


if __name__ == '__main__':
    generate()
