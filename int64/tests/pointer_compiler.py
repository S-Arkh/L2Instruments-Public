"""Negative compiler contracts for typed pointer fields and expressions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if not out.is_relative_to(root/'uExplorer/local'):
        parser.error('Output must be a new directory under uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    cases = {
        'array_zero': ('var native pointer Handle[0];', 'Pointer array dimension'),
        'array_one': ('var native pointer Handle[1];', 'Pointer array dimension'),
        'array_large': ('var native pointer Handle[2049];', 'Pointer array dimension'),
        'array_empty': ('var native pointer Handle[];', 'Pointer array dimension'),
        'array_float': ('var native pointer Handle[2.5];', 'Pointer array dimension'),
        'array_bracket': ('var native pointer Handle[2;', "Missing ']'"),
        'local': ('function Test() { local native pointer Handle; }', 'Pointer declarations require native/transient fields or plain function pointer types'),
        'parameter': ('function Test(native pointer Handle);', 'Pointer declarations require native/transient fields or plain function pointer types'),
        'local-array': ('function Test() { local pointer Handles[2]; }', 'Pointer function arrays are unsupported'),
        'plain-field': ('var pointer Handle;', 'Pointer declarations require native/transient fields or plain function pointer types'),
        'out-literal': ('function Set(out pointer Value) { Value=0; } function Test() { Set(0); }', "Call to 'Set': type mismatch"),
        'argument-int': ('function Set(pointer Value); function Test(int Value) { Set(Value); }', 'type mismatch'),
        'return-nonzero': ('function pointer Test() { return 1; }', 'Type mismatch'),
        'pointer-add': ('var native pointer Handle; function Test() { Handle=Handle+1; }', "Left type is incompatible with '+'"),
        'pointer-compare': ('var native pointer Handle; function bool Test() { return Handle==Handle; }', "Types are incompatible with '=='"),
        'pointer-equal-int': ('var native pointer Handle; function bool Test(int Value) { return PointerEqual(Handle, Value); }', 'Type mismatch'),
        'pointer-equal-nonzero': ('var native pointer Handle; function bool Test() { return PointerEqual(Handle, 1); }', 'Type mismatch'),
        'pointer-equal-object': ('var native pointer Handle; function bool Test() { return PointerEqual(Handle, Self); }', 'Type mismatch'),
        'read': ('var native pointer Handle; function Test() { Log(Handle); }', "Call to 'Log': type mismatch"),
        'write-variable-int': ('var native pointer Handle; function Test(int Value) { Handle = Value; }', "Type mismatch in '='"),
        'write-nonzero': ('var native pointer Handle; function Test() { Handle = 1; }', "Type mismatch in '='"),
        'write-object': ('var native pointer Handle; function Test() { Handle = Self; }', "Type mismatch in '='"),
        'write-none': ('var native pointer Handle; function Test() { Handle = None; }', "Type mismatch in '='"),
        'read-int': ('var native pointer Handle; function int Test() { return Handle; }', 'Type mismatch'),
        'array-mismatch': ('var native pointer Handles[2], Handle; function Test() { Handle = Handles; }', 'Array mismatch'),
        'replication': ('var transient pointer Handle;\nreplication\n{\n reliable if (true) Handle;\n}', 'Pointer replication is unsupported'),
        'replication-array': ('var transient pointer Handles[2]; replication { reliable if (true) Handles; }', 'Pointer replication is unsupported'),
        'replication-struct': ('struct Data { var transient pointer Handle; }; var Data Value; replication { reliable if (true) Value; }', 'Pointer replication is unsupported'),
        'replication-nested': ('struct Inner { var native pointer Handle; }; struct Data { var Inner Value; }; var Data Value; replication { reliable if (true) Value; }', 'Pointer replication is unsupported'),
        'replication-inherited-struct': ('struct BaseData { var native pointer Handle; }; struct Data extends BaseData { var int Count; }; var Data Value; replication { reliable if (true) Value; }', 'Pointer replication is unsupported'),
        'replication-dynamic': ('struct Data { var transient pointer Handle; }; var array<Data> Values; replication { reliable if (true) Values; }', 'Pointer replication is unsupported'),
        'replication-rpc': ('replication { reliable if (true) Send; } function Send(pointer Value) {}', 'Pointer replication is unsupported'),
        'replication-rpc-out': ('replication { reliable if (true) Send; } function Send(out pointer Value) {}', 'Pointer replication is unsupported'),
        'replication-rpc-struct': ('struct Data { var transient pointer Handle; }; replication { reliable if (true) Send; } function Send(Data Value) {}', 'Pointer replication is unsupported'),
        'duplicate': ('var native pointer Handle; var native pointer Handle;', 'Duplicate or inherited pointer field name'),
        'default': ('var native pointer Handle;\ndefaultproperties\n{\n Handle=1\n}', 'Pointer defaults require literal 0'),
        'struct-default': ('struct Data { var native pointer Handle; }; var Data Value;\ndefaultproperties\n{\n Value=(Handle=1)\n}', 'Pointer defaults require literal 0'),
        'transient-default': ('var transient pointer Handle;\ndefaultproperties\n{\n Handle=-1\n}', 'Pointer defaults require literal 0'),
        'transient-struct-default': ('struct Data { var transient pointer Handle; }; var Data Value;\ndefaultproperties\n{\n Value=(Handle=0abc)\n}', 'Pointer defaults require literal 0'),
    }
    for name, value in {'hex': '0x0', 'float': '0.0', 'suffix': '0abc',
                        'expression': '0 + 1', 'none': 'None', 'empty': ''}.items():
        cases['default-'+name] = ('var native pointer Handle;\ndefaultproperties\n{\n Handle='+value+'\n}',
                                 'Pointer defaults require literal 0')
    failures = []
    results = {}
    for index, (name, (code, diagnostic)) in enumerate(cases.items()):
        # The legacy SDK's driver discovery fails with sufficiently long System
        # paths. Keep physical names short; retain semantic names in the report.
        workspace = 'case-'+str(index)
        source = out/(workspace+'-source')
        source.mkdir()
        (source/'InvalidPointer.uc').write_text('class InvalidPointer extends Object;\n'+code+'\n', encoding='ascii')
        result = subprocess.run([sys.executable, '-B', str(root/'uExplorer/tests/compile_generation.py'),
                                 '--compiler', str(args.compiler.resolve()), '--launcher', str(args.launcher.resolve()),
                                 '--sources', str(source), '--out', str(out/workspace), '--expect-error', diagnostic])
        results[name] = dict(workspace=workspace, diagnostic=diagnostic, passed=result.returncode == 0)
        if result.returncode:
            failures.append(name)
    (out/'result.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    if failures:
        raise AssertionError(failures)
    print(f'PASS: {len(cases)} rejected pointer operations/declarations')


if __name__ == '__main__':
    main()
