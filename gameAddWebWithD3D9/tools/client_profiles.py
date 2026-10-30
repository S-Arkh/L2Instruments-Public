"""Verify browser ABI inputs and generate the profile-specific texture adapter."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'int64/tools'))
from verify_profile import PE


def profile(name):
    catalog = json.loads((ROOT / 'client_profiles.json').read_text())
    if catalog['schema'] != 1:
        raise ValueError('Unsupported browser profile catalog')
    return catalog['profiles'][name]


def locate(directory, name):
    matches = [p for p in directory.iterdir() if p.name.lower() == name.lower()]
    if len(matches) != 1:
        raise ValueError(f'Missing or ambiguous input: {name}')
    return matches[0]


def verify(name, directory):
    p = profile(name)
    inventory = json.loads((ROOT / 'reports/inventory.json').read_text())
    checked = {}
    for filename in ('Engine.dll', 'NWindow.dll', 'D3DDrv.dll'):
        path = locate(directory, filename)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = inventory[p['inventory_prefix'] + '/' + filename.lower()]['sha256']
        if actual != expected:
            raise ValueError(f'Unsupported {filename} for {name}')
        checked[filename] = actual
    for filename, key in [('Interface.u', 'interface_sha256'), ('Interface.xdat', 'xdat_sha256')]:
        if key in p:
            actual = hashlib.sha256(locate(directory, filename).read_bytes()).hexdigest()
            if actual != p[key]:
                raise ValueError(f'Unsupported UI input: {filename}')
            checked[filename] = actual
    engine = PE(locate(directory, 'Engine.dll'))
    for symbol, key in [('?Init@UTexture@@UAEXHH@Z', 'init_rva'), ('??_7UTexture@@6B@', 'vtable_rva')]:
        if engine.exports.get(symbol) != int(p['texture'][key], 16):
            raise ValueError(f'Export mismatch: {symbol}')
    if p.get('core_profile'):
        # Import by file: both the browser and Core tools live in a tools directory.
        import importlib.util
        spec = importlib.util.spec_from_file_location('browser_core_catalog', ROOT.parent / 'dll/tools/core_profiles.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        core = next(c for c in module.catalog()['profiles'] if c['name'] == p['core_profile'])
        actual = hashlib.sha256(locate(directory, 'Core.dll').read_bytes()).hexdigest()
        if actual != core['sha256']:
            raise ValueError('Expected the original Core matching the selected profile')
        checked['Core.dll'] = actual
    return dict(profile=name, browser_status=p['browser_status'], xdat_schema=p['xdat_schema'], checked=checked)


def adapter(name):
    p = profile(name)
    inventory = json.loads((ROOT / 'reports/inventory.json').read_text())
    digest = bytes.fromhex(inventory[p['inventory_prefix'] + '/engine.dll']['sha256'])
    text = (ROOT / 'prototype/native/texture_probe.cpp').read_text()
    text, count = re.subn(r'const unsigned char expected\[32\] = \{.*?\};',
        'const unsigned char expected[32] = {' + ','.join(hex(x) for x in digest) + '};', text, flags=re.S)
    if count != 1:
        raise ValueError('Texture hash template changed')
    replacements = {
        'base + 0x1c4510': 'base + ' + p['texture']['init_rva'],
        'base + 0x4e358c': 'base + ' + p['texture']['vtable_rva'],
        'base + 0x581904': 'base + ' + p['texture']['render_vtable_rva'],
        'field<void*>(texture, 0x108)': 'field<void*>(texture, ' + p['texture']['render'] + ')',
        'field<int>(texture, 0xfc)': 'field<int>(texture, ' + p['texture']['mip_count'] + ')',
        'field<void*>(texture, 0xf8)': 'field<void*>(texture, ' + p['texture']['mips'] + ')',
    }
    for old in replacements:
        if old not in text:
            raise ValueError(f'Texture template changed: {old}')
    # One pass prevents newly substituted Gracia offsets being replaced again.
    text = re.sub('|'.join(re.escape(k) for k in replacements), lambda m: replacements[m[0]], text)
    return text.replace('HF x86 only', name + ' x86 only').replace('HF TEXF_RGBA8', 'TEXF_RGBA8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile')
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = verify(args.profile, args.inputs)
    if args.adapter:
        args.adapter.write_text(adapter(args.profile))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
