"""Validate ExtensionL2.u and extract a reference-free call for the real client VM."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2] / 'int64'
sys.path.insert(0, str(ROOT / 'tools'))
from ue2package import Package, Reader


def check_bindings(p, manifest):
    metadata = json.loads(Path(manifest).read_text(encoding='utf-8'))
    cls = metadata['class']
    _, class_entry = p.find(cls)
    if class_entry.flags & 0x04000000:
        raise ValueError('Generated API must be a script class')
    for binding in metadata['bindings']:
        name = cls + '.' + binding['name']
        fn_index, _ = p.find(name)
        fn = p.function(name)
        if fn['native'] != binding['index'] or fn['flags'] & 0x2401 != 0x2401:
            raise ValueError(f'{name}: expected numbered native static final')
        expected = [('Arg' + str(i), t, False) for i, t in enumerate(binding['arguments'])]
        if binding['return'] != 'void':
            expected.append(('ReturnValue', binding['return'], True))
        children = [e for e in p.exports if e.outer == fn_index and p.ref(e.cls).endswith('Property')]
        if len(children) != len(expected):
            raise ValueError(f'{name}: wrong number of parameters/return properties')
        for arg, kind, is_return in expected:
            _, entry = p.find(name + '.' + arg)
            cls_name = {'byte': 'ByteProperty', 'int': 'IntProperty', 'bool': 'BoolProperty',
                         'float': 'FloatProperty', 'int64': 'StructProperty', 'string': 'StrProperty'}[kind]
            if p.ref(entry.cls) != 'Core.' + cls_name:
                raise ValueError(f'{name}.{arg}: wrong property type')
            r = Reader(p.data[entry.offset:entry.offset + entry.size])
            if p.name(r.index()) != 'None':
                raise ValueError('Unexpected property tags')
            r.index()
            r.index()
            if r.unpack('<i') != 1:
                raise ValueError('Expected scalar parameter')
            flags = r.unpack('<I')
            if not flags & 0x80 or bool(flags & 0x400) != is_return:
                raise ValueError('Wrong parameter flags')
            if not is_return and flags & (0x10 | 0x100 | 0x200 | 0x800):
                raise ValueError('Unexpected optional/out/skip/coerce parameter')
            p.name(r.index())
            if kind == 'int64' and p.ref(r.index()) != 'Core.Object.INT64':
                raise ValueError('Wrong INT64 representation')
        print(f'OK binding {binding["index"]}: {name}')


def check(path, bytecode_output=None, bindings_json=None):
    p = Package(path)
    if bindings_json:
        check_bindings(p, bindings_json)
        if not bytecode_output:
            return
    _, cls = p.find('ExtensionL2Tests')
    if cls.flags & 0x04000000:
        raise ValueError('Test class must remain a script class; only the function is native')
    declaration = p.function('ExtensionL2API.SaturatingAdd64')
    if declaration['native'] != 4000 or declaration['flags'] & 0x401 != 0x401:
        raise ValueError('Expected native(4000) final function')
    call = p.function('ExtensionL2Tests.ExampleCall')
    rows = call['instructions']
    natives = [r for r in rows if r['kind'] == 'native']
    if len(natives) != 1 or natives[0]['index'] != 4000:
        raise ValueError('ExampleCall does not invoke native 4000')
    if [r['cast'] for r in rows if r['kind'] == 'cast'] != ['5b', '5b']:
        raise ValueError('Expected int-to-INT64 argument conversions')
    start = natives[0]['serial']
    end = next(r['serial'] + 1 for r in rows if r['kind'] == 'end_parameters')
    # This exact function uses no serialized object/name references. Therefore
    # its serialized native-call bytes are also valid in-memory VM bytes.
    if any(r['kind'] not in ('return', 'native', 'cast', 'constant', 'int_one', 'nothing', 'end_parameters') for r in rows):
        raise ValueError('ExampleCall now contains a reference or unsupported expression')
    _, export = p.find('ExtensionL2Tests.ExampleCall')
    code = p.data[export.offset + start:export.offset + end]
    if code[:2] != b'\x6f\xa0':
        raise ValueError('Expected extended-native encoding 6F A0')
    if bytecode_output:
        output = Path(bytecode_output)
        if output.exists():
            raise ValueError('Choose a new bytecode fixture path')
        output.write_bytes(code)
    print(json.dumps(dict(native_index=4000, script_class=True, native_call_hex=code.hex(),
                          expected_result=2147483648, package_sha256=p.sha256), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--bytecode-output', type=Path)
    parser.add_argument('--bindings-json', type=Path)
    args = parser.parse_args()
    check(args.package, args.bytecode_output, args.bindings_json)
