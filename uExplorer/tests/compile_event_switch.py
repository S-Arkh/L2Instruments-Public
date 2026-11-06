"""Check event-label recovery and named/numeric generated-source equivalence.

The original switch is reconstructed as PC dispatch. Compare two spellings of
that same generated program, not the original AST against a rewritten switch.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from backend import Core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compiler', 'launcher', 'library', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'local') or out == ROOT/'local':
        parser.error('Output must be a new directory under uExplorer/local')
    out.mkdir(parents=True, exist_ok=False)
    core = Core(args.library.resolve())

    def compile_sources(sources, label):
        subprocess.run([sys.executable, '-B', str(ROOT/'tests/compile_generation.py'),
                        '--compiler', str(args.compiler.resolve()), '--launcher', str(args.launcher.resolve()),
                        '--sources', str(sources), '--out', str(out/label)], check=True)
        return out/label/'System/Generation.u'

    def snapshot(package):
        classes = core.request(operation='inspect', path=str(package))['package']['classes']
        sources, functions = {}, {}
        for cls in classes:
            result = core.request(operation='decompile', path=str(package), class_id=cls['id'], force_bytecode=True)['result']
            if result['status'] != 'recovered':
                raise AssertionError(result['issues'])
            sources[cls['name']] = result['code']
            for function in result['functions']:
                functions[function['name']] = core.request(operation='function', path=str(package), function=function['name'])['result']
        return sources, functions

    original = compile_sources(ROOT/'tests/event_switch', 'original')
    sources, _ = snapshot(original)
    probe = sources['EventSwitchProbe']
    assert probe.count('case EV_Ready:') == 1
    assert probe.count('case 2010:') == 2  # Computed selector and unrelated function.
    assert 'case 2030:' in probe and 'case 9999:' in probe
    assert 'case EV_Alias' not in probe
    assert 'case EV_Ready:' not in sources['EventSwitchShadowed']
    assert 'case 2010:' in sources['EventSwitchShadowed']
    assert '(EventID == EV_Ready)' in probe
    assert '(EV_Ready != EventID)' in probe
    assert '(EventID == 2030)' in probe and '(EventID == 9999)' in probe
    assert '((EventID + 1) == 2010)' in probe
    assert '(Value == 2010)' in probe
    assert '(EV_Ready == 2010)' in sources['EventSwitchShadowed']

    results = []
    for spelling in ('named', 'numeric'):
        directory = out/(spelling+'-source')
        directory.mkdir()
        for name, code in sources.items():
            if spelling == 'numeric':
                code = code.replace('case EV_Ready:', 'case 2010:')
                code = code.replace('(EventID == EV_Ready)', '(EventID == 2010)')
                code = code.replace('(EV_Ready != EventID)', '(2010 != EventID)')
            (directory/(name+'.uc')).write_text(code, encoding='utf-8')
        package = compile_sources(directory, spelling)
        results.append(snapshot(package)[1])

    def canonical(value):
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items() if k != 'reference'}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value

    assert canonical(results[0]) == canonical(results[1]), 'Named and numeric label ASTs differ'
    (out/'result.json').write_text(json.dumps(dict(source_checks=True, named_numeric_ast_equal=True,
                                                 original_ast_equivalence_claimed=False, runtime_tested=False), indent=2))
    print('PASS: event-label scope checks and named/numeric generated-program AST equality')


if __name__ == '__main__':
    main()
