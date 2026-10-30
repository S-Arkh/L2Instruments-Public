"""Compare WOTgreal Classes with the input package and inventory native placeholders."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'tools/ue2'))
from ue2package import Package
from extract_sources import script_text


def audit(classes):
    package = Package(ROOT / 'inputs/Interface.u')
    expected = {e.name.casefold() for e in package.exports if e.cls == 0}
    files = sorted(classes.glob('*.uc'))
    actual = {p.stem.casefold() for p in files}
    declarations = {}
    for name in ('Core', 'Engine', 'NWindow'):
        sdk = Package(ROOT / 'inputs' / (name + '.u'))
        for entry in sdk.exports:
            if entry.name != 'ScriptText':
                continue
            text = script_text(sdk, entry)[1]
            for match in re.finditer(r'\bnative\s*\(\s*(\d+)\s*\)([^;]*);', text, re.I):
                declarations.setdefault(int(match[1]), []).append(
                    name + ': ' + ' '.join(match[0].split()))
    counts = Counter()
    occurrences = {}
    for path in files:
        source = path.read_bytes().decode('latin1')
        # Custom natives are declared in Interface itself. Confirm each declaration
        # against the serialized UFunction, rather than inferring its name from use.
        for match in re.finditer(r'\bnative\s*\(\s*(\d+)\s*\)([^;]*);', source, re.I):
            function = re.search(r'\bfunction\s+(?:\w+\s+)?(\w+)\s*\(', match[2], re.I)
            if not function:
                raise ValueError(f'Unsupported Interface native declaration: {path.name}')
            name = path.stem + '.' + function[1]
            metadata = package.function(name)
            if metadata['native'] != int(match[1]) or not metadata['flags'] & 0x400:
                raise ValueError(f'Native declaration does not match bytecode: {name}')
            declarations.setdefault(int(match[1]), []).append('Interface: ' + ' '.join(match[0].split()))
        for line, text in enumerate(source.splitlines(), 1):
            for index in re.findall(r'UnknownFunction(\d+)', text):
                index = int(index)
                counts[index] += 1
                occurrences.setdefault(index, []).append(dict(file=path.name, line=line))
    return dict(
        source_directory=str(classes), package_sha256=package.sha256,
        package_classes=len(expected), exported_files=len(files),
        missing=sorted(expected - actual), extra=sorted(actual - expected),
        source_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        placeholder_calls=sum(counts.values()),
        natives={str(i): dict(count=counts[i], declarations=declarations.get(i, []),
                             occurrences=occurrences[i]) for i in sorted(counts)},
        unresolved_indices=sorted(set(counts) - declarations.keys()),
        ready_to_compile=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('classes', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.classes.is_dir():
        parser.error('Classes directory does not exist')
    result = audit(args.classes)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('natives', 'source_hashes')}, indent=2))
