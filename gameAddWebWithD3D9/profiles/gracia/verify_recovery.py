"""Compare original CFG blocks with recompiled dispatcher paths and expressions."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bytecode_sources import ROOT, Package, tree
from property_types import Types


def number(node):
    if node['kind'] == 'constant': return node['value']
    if node['kind'] == 'int_zero': return 0
    if node['kind'] == 'int_one': return 1
    raise ValueError('Expected a constant')


def canonical(node):
    k, c = node['kind'], node['children']
    if k in ('debug', 'nothing', 'end_parameters'): return None
    if k in ('skip', 'bool_variable', 'discard_string'): return canonical(c[0])
    if k in ('constant', 'int_zero', 'int_one'):
        n = number(node)
        return ['float' if isinstance(n, float) else 'int', n]
    children = [canonical(n) for n in c if n['kind'] != 'end_parameters']
    if k == 'native' and node.get('index') in (143, 169) and children[0][0] in ('int','float'):
        return [children[0][0], -children[0][1]]
    if k == 'cast' and node['cast'] == '3a' and children[0][0] == 'int': return children[0]
    if k == 'cast':
        cast = node['cast']
        if cast == '52' and children[0][0] == 'int' and 0 <= children[0][1] <= 255:
            cast = '53'  # byte/int constants stringify identically in this range
        return ['cast', cast, *children]
    if k == 'class_context' and c[1]['kind'] == 'final_call' and c[1]['value'] == 'GraciaRecoveryAPI.ContextInt':
        return children[1]
    if k == 'class_context' and c[0]['kind'] == 'object' and c[0]['value'].casefold() == 'graciarecoveryapi' and c[1]['kind'] == 'virtual_call' and c[1]['value'].casefold() == 'contextint':
        return ['context', *children[1][2:]]
    if k == 'final_call' and node['value'] == 'GraciaRecoveryAPI.ContextInt':
        return ['context', *children]
    result = [k]
    for key in ('index', 'value', 'cast'):
        if key in node:
            value = node[key]
            if key == 'value' and isinstance(value, str) and k != 'string':
                value = value.casefold()  # FName and UE identifiers are case-insensitive
            result.append(value)
    return result + children


def block_starts(roots, end):
    labels = {roots[0]['pc'], end}
    for i, n in enumerate(roots):
        if n['kind'] in ('jump', 'jump_if_not', 'case'):
            if n['target'] != 65535: labels.add(n['target'])
            if i+1 < len(roots): labels.add(roots[i+1]['pc'])
        if n['kind'] == 'return' and i+1 < len(roots): labels.add(roots[i+1]['pc'])
        if n['kind'] in ('switch', 'case'): labels.add(n['pc'])
    return labels


def switch_cases(roots, positions, index):
    result, seen = [], set()
    j = index+1
    while j not in seen:
        seen.add(j)
        case = roots[j]
        if case['kind'] != 'case': raise ValueError('Invalid case chain')
        result.append((None if case['target'] == 65535 else canonical(case['children'][0]), roots[j+1]['pc']))
        if case['target'] == 65535: return result
        j = positions[case['target']]
    raise ValueError('Cyclic case chain')


def is_pc(node):
    return node['kind'] == 'local' and node['value'].rsplit('.',1)[-1].lower() == '__recoveredpc'


def trace(roots, positions, start, boundaries=None, generated=False):
    def walk(pc, seen):
        if boundaries is not None and pc != start and pc in boundaries:
            return ['route', pc]
        if pc in seen: raise ValueError('Unexpected cycle inside a basic block')
        if pc not in positions: raise ValueError(f'Unmapped PC {pc}')
        seen = seen | {pc}
        i = positions[pc]; n = roots[i]; k = n['kind']; c = n['children']
        next_pc = roots[i+1]['pc'] if i+1 < len(roots) else None
        if generated and k == 'assign' and is_pc(c[0]):
            target = number(c[1]) if c[1]['kind'] != 'native' else None
            if target is None:
                # -1 is encoded with the integer unary-minus native.
                if c[1].get('index') != 143 or number(c[1]['children'][0]) != 1:
                    raise ValueError('Nonconstant recovered PC')
                target = -1
            return ['return', None] if target == -1 else ['route', target]
        if k == 'return': return ['return', canonical(c[0])]
        if k == 'jump':
            return walk(n['target'], seen) if generated else ['route', n['target']]
        if k == 'jump_if_not':
            yes = walk(next_pc, seen) if generated else ['route', next_pc]
            no = walk(n['target'], seen) if generated else ['route', n['target']]
            return ['branch', canonical(c[0]), yes, no]
        if k == 'switch':
            cases = switch_cases(roots, positions, i)
            return ['switch', canonical(c[0]), [[value, walk(target, seen) if generated else ['route', target]] for value,target in cases]]
        if k in ('case', 'nothing', 'debug'):
            return walk(next_pc, seen)
        return ['statement', canonical(n), walk(next_pc, seen)]
    return walk(start, set())


def verify(original, compiled):
    roots, built = tree(original['instructions']), tree(compiled['instructions'])
    positions = {n['pc']:i for i,n in enumerate(roots)}
    built_positions = {n['pc']:i for i,n in enumerate(built)}
    outer = [i for i,n in enumerate(built) if n['kind']=='switch' and is_pc(n['children'][0])]
    if not outer:
        # Empty script declarations retain their implicit Return Nothing.
        if [canonical(n) for n in roots] != [canonical(n) for n in built]:
            raise ValueError('Function without dispatcher differs')
        return 0
    if len(outer) != 1: raise ValueError('Multiple dispatchers')
    switch_index = outer[0]
    prefix = built[:switch_index]
    if original['name'] == 'LoginMenuWnd.OnClickButton':
        expected_condition = ['native', 122, ['local', 'loginmenuwnd.onclickbutton.strid'], ['string', 'btnBrowser']]
        expected_action = ['context', ['final_call', 'nwindow.uiscript.getwindowhandle', ['string', 'BrowserWnd']], ['final_call', 'nwindow.windowhandle.showwindow']]
        if len(prefix) != 5 or canonical(prefix[0]['children'][0]) != expected_condition or canonical(prefix[1]) != expected_action or prefix[2]['kind'] != 'return' or canonical(prefix[2]['children'][0]) is not None or prefix[0]['target'] != prefix[3]['pc']:
            raise ValueError('Unexpected login browser branch')
        prefix = prefix[3:]
    if len(prefix) != 2 or prefix[0]['kind'] != 'assign' or not is_pc(prefix[0]['children'][0]) or number(prefix[0]['children'][1]) != 0 or prefix[1]['kind'] != 'jump_if_not' or prefix[1]['children'][0]['kind'] != 'true':
        raise ValueError('Invalid dispatcher initialization')
    # Check the common return/backedge and every generated PC assignment's tail.
    finish = built[-4:]
    if len(finish) != 4 or finish[0]['kind'] != 'jump_if_not' or finish[1]['kind'] != 'jump' or finish[2]['kind'] != 'jump' or finish[3]['kind'] != 'return':
        raise ValueError('Invalid dispatcher epilogue')
    expected_exit = ['native',154,['local',original['name'].casefold()+'.__recoveredpc'],['int',-1]]
    if canonical(finish[0]['children'][0]) != expected_exit or finish[0]['target'] != finish[2]['pc'] or finish[1]['target'] != finish[3]['pc'] or finish[2]['target'] != prefix[1]['pc'] or prefix[1]['target'] != finish[3]['pc']:
        raise ValueError('Invalid dispatcher return/backedge')
    def only_jumps_to_epilogue(pc):
        seen = set()
        while pc != finish[0]['pc']:
            if pc in seen: raise ValueError('Cyclic dispatcher tail')
            seen.add(pc)
            n = built[built_positions[pc]]
            if n['kind'] != 'jump': raise ValueError('Code after route assignment')
            pc = n['target']
    for i,n in enumerate(built):
        if n['kind'] == 'assign' and is_pc(n['children'][0]) and n is not prefix[0]:
            only_jumps_to_epilogue(built[i+1]['pc'])
    cases = switch_cases(built, built_positions, outer[0])
    dispatch = {value[1]:pc for value,pc in cases if value is not None}
    boundaries = block_starts(roots, original['memory_size'])
    expected = boundaries - {original['memory_size']}
    if set(dispatch) != expected:
        raise ValueError(f'Block set mismatch {set(dispatch)^expected}')
    for pc in sorted(expected):
        a = trace(roots, positions, pc, boundaries=boundaries)
        b = trace(built, built_positions, dispatch[pc], generated=True)
        if a != b:
            return dict(pc=pc, original=a, compiled=b)
    return len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiled', type=Path, default=ROOT/'workspace/System/Interface.u')
    parser.add_argument('--report', type=Path, default=ROOT/'recovery-validation.json')
    args = parser.parse_args()
    source, target = Package(ROOT/'inputs/Interface.u'), Package(args.compiled)
    errors, functions, blocks = {}, 0, 0
    for i,e in enumerate(source.exports, 1):
        if source.ref(e.cls) != 'Core.Function': continue
        name = source.ref(i)
        try:
            original, compiled = source.function(name), target.function(name)
            # Definition/native/event/static/final flags affect dispatch semantics.
            if original['native'] != compiled['native'] or original['flags'] != compiled['flags']:
                raise ValueError(f'Function ABI flags differ: {original["flags"]:#x}/{compiled["flags"]:#x}')
            if original['native']:
                functions += 1
                continue
            result = verify(original, compiled)
            if isinstance(result, dict): errors[name] = result
            else: functions += 1; blocks += result
        except (ValueError, KeyError, IndexError, RecursionError) as error:
            errors[name] = str(error)
    original_types = Types(ROOT/'inputs', ('Interface',))
    compiled_types = Types(args.compiled.parent, ('Interface',))
    metadata_errors = {}
    for name, prop in original_types.properties.items():
        other = compiled_types.properties.get(name)
        for key in ('kind','ref','flags','dim'):
            a, b = prop[key], other.get(key) if other else None
            if isinstance(a,str): a = a.casefold()
            if isinstance(b,str): b = b.casefold()
            if a != b: metadata_errors[name+'.'+key] = [a,b]
    for category in ('parents', 'enums'):
        old, new = getattr(original_types,category), getattr(compiled_types,category)
        for name,value in old.items():
            if json.dumps(value).casefold() != json.dumps(new.get(name)).casefold():
                metadata_errors[category+':'+name] = [value,new.get(name)]
    helper = tree(target.function('GraciaRecoveryAPI.ContextInt')['instructions'])
    if len(helper) != 4 or canonical(helper[0]['children'][0]) != ['native',114,['local','graciarecoveryapi.contextint.owner'],['none']] or helper[0]['target'] != helper[2]['pc'] or canonical(helper[1]) != ['return',['int',0]] or canonical(helper[2]) != ['return',['local','graciarecoveryapi.contextint.value']]:
        errors['GraciaRecoveryAPI.ContextInt'] = 'Unexpected null-context helper implementation'
    result = dict(original_sha256=source.sha256, compiled_sha256=target.sha256,
                  verified_functions=functions, verified_blocks=blocks, errors=errors,
                  metadata_errors=metadata_errors, passed=not errors and not metadata_errors,
                  scope='function flags, CFG routing/expressions, dispatcher init/exit, login branch, helper, property metadata, enums and inheritance')
    args.report.write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(verified_functions=functions, verified_blocks=blocks, errors=len(errors), first_errors=list(errors)[:15], metadata_errors=metadata_errors), indent=2))
    if errors or metadata_errors: raise SystemExit(1)


if __name__ == '__main__': main()
