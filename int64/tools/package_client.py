"""Wrap a compiled script package using the supplied client's Ver111 envelope.

No package-version patching or payload transformation except reversible XOR.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from ue2package import Package


def wrap(data, envelope):
    if not data.startswith(b'\xc1\x83\x2a\x9e'):
        raise ValueError('Expected an unwrapped Unreal package')
    if envelope not in ('Lineage2Ver111', 'GamekitData111', 'plain'):
        raise ValueError('Unsupported package envelope')
    if envelope == 'plain':
        return data
    return envelope.encode('utf-16le') + bytes(b ^ 0xac for b in data)


def package_client(source, output, reference, replace_output=False):
    source, output, reference = Path(source), Path(output), Path(reference)
    if output.resolve() in (source.resolve(), reference.resolve()) or (output.exists() and not replace_output):
        raise ValueError('Choose a new output file, separate from the source/reference')
    compiled, client = Package(source), Package(reference)
    payload = wrap(compiled.data, client.envelope)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        backup = output.parent / 'Backups' / (output.stem + '.' + digest + output.suffix)
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            shutil.copy2(output, backup)
        elif hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
            raise ValueError('Backup checksum mismatch')
    output.write_bytes(payload)
    reread = Package(output)
    if reread.data != compiled.data:
        raise ValueError('Envelope round-trip failed')
    report = dict(source_sha256=compiled.sha256, packaged_sha256=hashlib.sha256(payload).hexdigest(),
                  envelope=client.envelope, compiled_version=compiled.version,
                  compiled_licensee=compiled.licensee, reference_version=client.version,
                  reference_licensee=client.licensee, payload_unchanged=True)
    output.with_suffix('.package.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--like', required=True, type=Path)
    parser.add_argument('--replace', action='store_true', help='Back up and replace an existing generated output')
    args = parser.parse_args()
    print(json.dumps(package_client(args.source, args.output, args.like, args.replace), indent=2))
