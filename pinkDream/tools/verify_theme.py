"""Validate v2 theme artifacts, alpha, package boundaries and real install/rollback."""
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from inventory import ROOT, inspect
from asset_store import read, load_image, digest
from install import install, rollback, sha
from texture import decode, FORMATS


def verify(bundle, assets, temp_root):
    m = json.loads((bundle / 'manifest.json').read_text())
    lib = json.loads((assets / 'library.json').read_text())
    if json.loads((assets / 'manifest.json').read_text()) != m:
        raise ValueError('Bundle/assets manifests differ')
    for relative, expected in m['loose_files'].items():
        path = (assets / relative).resolve()
        if not path.is_relative_to(assets.resolve()) or sha(path) != expected:
            raise ValueError('Loose asset modified; copy edits to an override folder')
    sources = {t['resource']: t for t in lib['textures']}
    mip_count = 0
    with tempfile.TemporaryDirectory(dir=temp_root, prefix='pinkdream-theme-') as temp:
        client = Path(temp) / 'client'
        backup = Path(temp) / 'backup'
        for f in m['files']:
            package = next(p for p in lib['packages'] if p['path'] == f['path'])
            original = read(package['container'])
            src = client / f['path']
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(original)
            before = inspect(src, True)
            if sha(bundle / f['path']) != f['sha256']:
                raise ValueError('Package hash mismatch')
            after = inspect(bundle / f['path'], True)
            if before['exports'] != after['exports']:
                raise ValueError('Export table changed')
            spans = []
            for t in m['textures']:
                if t['package'] != f['path']:
                    continue
                standard = load_image(t['standard_png'])
                editable = load_image(t['editable_png'])
                if standard.size != editable.size or standard.getchannel('A').tobytes() != editable.getchannel('A').tobytes():
                    raise ValueError('Editable geometry changed')
                fmt = next(k for k, v in FORMATS.items() if v == t['format'])
                for level, mip in enumerate(t['mips']):
                    payload = read(mip['payload'])
                    start, end = mip['offset'], mip['offset'] + len(payload)
                    if after['_data'][start:end] != payload:
                        raise ValueError('Packaged payload differs')
                    spans.append((start, end))
                    original_mip = sources[t['resource']]['mips'][level]
                    original_alpha = decode(read(original_mip['reference_payload']), mip['size'], fmt).getchannel('A')
                    image = decode(payload, mip['size'], fmt)
                    if image.getchannel('A').tobytes() != original_alpha.tobytes():
                        raise ValueError('Original alpha changed')
                    if load_image(mip['png']).tobytes() != image.tobytes():
                        raise ValueError('Saved mip differs')
                    if level == 0:
                        for ref in (t['packed_png'], t['packed_tga']):
                            if load_image(ref).tobytes() != image.tobytes():
                                raise ValueError('Saved top image differs')
                    mip_count += 1
            end = 0
            for start, stop in sorted(spans):
                if start < end or before['_data'][end:start] != after['_data'][end:start]:
                    raise ValueError('Unexpected changes outside image payloads')
                end = stop
            if before['_data'][end:] != after['_data'][end:]:
                raise ValueError('Unexpected trailing changes')
        install(client, bundle, backup, check=True)
        if backup.exists():
            raise ValueError('Check wrote files')
        install(client, bundle, backup)
        for f in m['files']:
            if sha(client / f['path']) != f['sha256']:
                raise ValueError('Install mismatch')
        rollback(backup)
        for f in m['files']:
            if sha(client / f['path']) != f['original_sha256']:
                raise ValueError('Rollback mismatch')
    return {'schema': 2, 'theme': m['theme'], 'revision': m['revision'],
            'textures': len(m['textures']), 'mips': mip_count, 'alpha_preserved': True,
            'outside_payloads_unchanged': True, 'stored_images_match_packages': True,
            'real_install_rollback_from_reference': 'passed',
            'install_from_pristine_client': 'hash-supported; original package copy unavailable for full installation test',
            'game_tested': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--assets', type=Path, required=True)
    p.add_argument('--temp-root', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    if a.report.exists():
        raise FileExistsError(a.report)
    result = verify(a.bundle, a.assets, a.temp_root)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    with a.report.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps(result, indent=2))
