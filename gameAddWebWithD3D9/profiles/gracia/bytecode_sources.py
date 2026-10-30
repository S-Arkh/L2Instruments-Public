"""Recover damaged function bodies from decoded bytecode using explicit basic blocks.

The program-counter local replaces unavailable decompiler labels. Each jump keeps
its exact serialized target; no heuristic reconstruction of complex control flow.
"""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from restore_sources import ROOT, Package, audit, native_mapping, repair_literals, restore, tokens
from property_types import Types


def tree(rows):
    roots, stack = [], []
    for row in rows:
        node = dict(row, children=[])
        while stack and stack[-1]['depth'] >= node['depth']:
            stack.pop()
        if stack:
            stack[-1]['children'].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'


CAST_TYPES = {
    0x3a:'int', 0x3b:'bool', 0x3c:'float', 0x3d:'byte', 0x3e:'bool', 0x3f:'float',
    0x40:'byte', 0x41:'int', 0x42:'float', 0x43:'byte', 0x44:'int', 0x45:'bool',
    0x46:'bool', 0x47:'bool', 0x48:'vector', 0x49:'byte', 0x4a:'int', 0x4b:'bool',
    0x4c:'float', 0x4d:'vector', 0x4e:'rotator', 0x4f:'bool', 0x50:'rotator',
    0x51:'bool', 0x52:'string', 0x53:'string', 0x54:'string', 0x55:'string',
    0x56:'string', 0x57:'string', 0x58:'string', 0x59:'string',
    0x5a:'INT64', 0x5b:'INT64', 0x5c:'INT64', 0x5d:'INT64', 0x5e:'INT64',
    0x5f:'byte', 0x60:'int', 0x61:'bool', 0x62:'float', 0x63:'string',
}


class Emitter:
    def __init__(self, package, mapping, function, types):
        self.package, self.mapping, self.function = package, mapping, function
        self.types = types

    def type_of(self, node):
        kind, c = node['kind'], node['children']
        if kind in ('local', 'instance', 'default', 'struct_member'):
            return self.types.property(node['value'])
        if kind in ('bool_variable', 'skip'):
            return self.type_of(c[0])
        if kind in ('context', 'class_context'):
            return self.type_of(c[1])
        if kind in ('final_call', 'virtual_call', 'global_call'):
            return self.types.parameters(node['value'], self.function['name'])[1]
        if kind in ('array_element', 'dynamic_array_element'):
            prop = self.type_of(c[1])
            if prop and prop['kind'] == 'ArrayProperty':
                return self.types.property(prop['ref'])
            return prop
        if kind in ('dynamic_cast', 'class_cast', 'object'):
            return dict(kind='ObjectProperty', ref=node['value'])
        return None

    def expression(self, node, expected=None, call_owner=None):
        kind, c = node['kind'], node['children']
        expr = self.expression
        leaf = lambda value: value.rsplit('.', 1)[-1]
        enum = self.types.enum(expected)
        if enum and kind in ('constant', 'int_zero', 'int_one'):
            value = node.get('value', 1 if kind == 'int_one' else 0)
            members = self.types.enums[enum.casefold()]
            if isinstance(value, int) and 0 <= value < len(members):
                return members[value]
            # Explicit enum casts preserve even values outside declared enumerators.
            return enum.split('.')[-1] + '(' + str(value) + ')'
        if kind in ('local', 'instance', 'native_parameter'):
            return leaf(node['value'])
        if kind == 'default':
            return 'default.' + leaf(node['value'])
        if kind in ('nothing', 'end_parameters'):
            return ''
        if kind in ('bool_variable', 'skip', 'discard_string'):
            return expr(c[0])
        if kind in ('int_zero', 'int_one', 'true', 'false', 'none', 'self'):
            return dict(int_zero='0', int_one='1', true='true', false='false', none='None', self='self')[kind]
        if kind == 'constant':
            return repr(node['value'])
        if kind == 'string':
            return quote(node['value'])
        if kind == 'name':
            return "'" + node['value'] + "'"
        if kind == 'object':
            value = node['value']
            if value == 'None':
                return 'None'
            # Object constants in UI bytecode are usually class references.
            try:
                _, entry = self.package.find(value)
                cls = 'Class' if entry.cls == 0 else leaf(self.package.ref(entry.cls))
            except ValueError:
                cls = 'Class'
            return cls + "'" + value + "'"
        if kind == 'native':
            args = [expr(n) for n in c if n['kind'] != 'end_parameters']
            native_kind, name = self.mapping[str(node['index'])]
            if native_kind == 'function':
                return name + '(' + ', '.join(args) + ')'
            if native_kind.startswith('operator'):
                if len(args) != 2:
                    raise ValueError('Invalid binary native arity')
                return '(' + args[0] + ' ' + name + ' ' + args[1] + ')'
            if len(args) != 1:
                raise ValueError('Invalid unary native arity')
            return '(' + (name + args[0] if native_kind == 'preoperator' else args[0] + name) + ')'
        if kind in ('virtual_call', 'final_call', 'global_call'):
            name = leaf(node['value'])
            if kind == 'global_call':
                name = 'global.' + name
            elif kind == 'final_call' and call_owner is None and node['value'].casefold() != self.function['name'].casefold() and name.casefold() == leaf(self.function['name']).casefold():
                name = 'super.' + name
            params, _ = self.types.parameters(node['value'], call_owner or self.function['name'])
            arguments = [n for n in c if n['kind'] != 'end_parameters']
            return name + '(' + ', '.join(expr(n, params[i] if i < len(params) else None) for i,n in enumerate(arguments)) + ')'
        if kind in ('context', 'class_context'):
            if c[1]['kind'] == 'constant' and isinstance(c[1]['value'], int):
                # UE still null-checks the context when its child is an inlined
                # class constant. Preserve that behavior without invalid obj.8.
                return "class'GraciaRecoveryAPI'.static.ContextInt(" + expr(c[0]) + ', ' + expr(c[1]) + ')'
            receiver = self.type_of(c[0])
            owner = receiver['ref'] + '.__context' if receiver and receiver.get('ref') else None
            return expr(c[0]) + ('.static.' if kind == 'class_context' else '.') + expr(c[1], call_owner=owner)
        if kind == 'cast':
            target = CAST_TYPES[int(node['cast'], 16)]
            if enum and target in ('byte', 'int'):
                return enum.split('.')[-1] + '(' + expr(c[0]) + ')'
            if target == 'int' and (c[0]['kind'] in ('int_zero','int_one') or c[0]['kind'] == 'constant' and isinstance(c[0]['value'], int)):
                return expr(c[0])
            if target == 'float' and c[0]['kind'] == 'constant' and isinstance(c[0]['value'], float):
                return expr(c[0])
            return target + '(' + expr(c[0]) + ')'
        if kind in ('dynamic_cast', 'class_cast'):
            return leaf(node['value']) + '(' + expr(c[0]) + ')'
        if kind in ('array_element', 'dynamic_array_element'):
            return expr(c[1]) + '[' + expr(c[0]) + ']'
        if kind == 'array_length':
            return expr(c[0]) + '.Length'
        if kind == 'struct_member':
            return expr(c[0]) + '.' + leaf(node['value'])
        if kind in ('struct_equal', 'struct_not_equal'):
            return '(' + expr(c[0]) + (' == ' if kind == 'struct_equal' else ' != ') + expr(c[1]) + ')'
        if kind in ('assign', 'assign_bool'):
            return expr(c[0]) + ' = ' + expr(c[1], self.type_of(c[0]))
        if kind in ('array_insert', 'array_remove'):
            return expr(c[0]) + ('.Insert(' if kind == 'array_insert' else '.Remove(') + ', '.join(expr(n) for n in c[1:]) + ')'
        if kind in ('vector', 'rotation'):
            return ('vect' if kind == 'vector' else 'rot') + '(' + ','.join(map(str, node['value'])) + ')'
        raise ValueError(f'Unsupported expression {kind} at {node["pc"]:#x}')

    def body(self, locals_text):
        roots = tree(self.function['instructions'])
        pcs = {n['pc']: i for i, n in enumerate(roots)}
        end = self.function['memory_size']
        labels = {roots[0]['pc'], end}
        for i, n in enumerate(roots):
            if n['kind'] == 'return' and i + 1 < len(roots):
                labels.add(roots[i+1]['pc'])
            if n['kind'] in ('jump', 'jump_if_not', 'case'):
                if n['target'] != 65535:
                    if n['target'] not in pcs and n['target'] != end:
                        raise ValueError('Jump into an expression')
                    labels.add(n['target'])
                if i + 1 < len(roots):
                    labels.add(roots[i+1]['pc'])
            if n['kind'] in ('switch', 'case'):
                labels.add(n['pc'])
        blocks, current = [], []
        for n in roots:
            if current and n['pc'] in labels:
                blocks.append(current)
                current = []
            current.append(n)
        if current:
            blocks.append(current)
        lines = ['{', locals_text, '    local int __RecoveredPC;', '    __RecoveredPC = 0;', '    while (true)', '    {', '        switch (__RecoveredPC)', '        {']
        for block in blocks:
            lines.append(f'        case {block[0]["pc"]}:')
            terminated = False
            for n in block:
                kind = n['kind']
                if terminated:
                    raise ValueError('Reachable expression after terminal in one block')
                if kind == 'jump':
                    lines.append(f'            __RecoveredPC = {n["target"]};')
                    terminated = True
                elif kind == 'jump_if_not':
                    next_pc = roots[pcs[n['pc']]+1]['pc']
                    lines.extend([f'            if ({self.expression(n["children"][0])})', f'                __RecoveredPC = {next_pc};', '            else', f'                __RecoveredPC = {n["target"]};'])
                    terminated = True
                elif kind == 'switch':
                    first = pcs[n['pc']] + 1
                    cases, j = [], first
                    while True:
                        case = roots[j]
                        if case['kind'] != 'case':
                            raise ValueError('Invalid switch case chain')
                        cases.append(case)
                        if case['target'] == 65535:
                            break
                        j = pcs[case['target']]
                        if j <= first and len(cases) > 1:
                            raise ValueError('Cyclic switch')
                    lines.append(f'            switch ({self.expression(n["children"][0])})')
                    lines.append('            {')
                    for case in cases:
                        label = 'default' if case['target'] == 65535 else 'case ' + self.expression(case['children'][0], self.type_of(n['children'][0]))
                        target = roots[pcs[case['pc']]+1]['pc']
                        lines.extend([f'            {label}:', f'                __RecoveredPC = {target};', '                break;'])
                    lines.append('            }')
                    terminated = True
                elif kind == 'return':
                    value = self.expression(n['children'][0], self.types.parameters(self.function['name'], self.function['name'])[1])
                    lines.append('            return ' + value + ';' if value else '            __RecoveredPC = -1;')
                    terminated = True
                elif kind in ('case', 'nothing', 'debug'):
                    pass
                else:
                    value = self.expression(n)
                    if kind == 'native' and value.startswith('('):
                        value = value[1:-1]
                    lines.append('            ' + value + ';')
            if not terminated:
                index = pcs[block[-1]['pc']] + 1
                target = roots[index]['pc'] if index < len(roots) else end
                lines.append(f'            __RecoveredPC = {target};')
            lines.append('            break;')
        # A valid serialized function returns before its script end. The default
        # only exits the dispatcher; the compiler supplies the implicit return.
        lines.extend(['        default:', '            __RecoveredPC = -1;', '            break;', '        }', '        if (__RecoveredPC == -1) break;', '    }', '}'])
        return '\n'.join(lines)


HEADER = re.compile(r'^(?:(?:simulated|static|final|singular|exec)\s+)*(?:function|event)\s+(?:\w+\s+)?(\w+)\s*\([^;{]*\)\s*\{', re.M)
BOUNDARY = re.compile(r'^(?:(?:simulated|static|final|singular|exec|auto)\s+)*(?:function|event|state|defaultproperties|native\b)', re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('classes', type=Path)
    parser.add_argument('--recovered', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--all', action='store_true', help='Regenerate every non-native body from bytecode')
    args = parser.parse_args()
    if args.destination.exists():
        raise ValueError('Choose a new destination')
    report = audit(args.classes)
    mapping = native_mapping(report)
    package = Package(ROOT/'inputs/Interface.u')
    types = Types(ROOT/'inputs')
    results, errors, files = {}, {}, {}
    previous = json.loads((args.recovered.parent/(args.recovered.name+'-restoration.json')).read_text())
    for path in sorted(args.classes.glob('*.uc')):
        original = path.read_bytes().decode('latin1')
        text = (args.recovered/path.name).read_bytes().decode('latin1')
        headers = list(HEADER.finditer(text))
        edits, recovered = [], []
        # States contain indented functions and must retain their state wrapper.
        for state in re.finditer(r'^(?:auto\s+)?state\s+(\w+)(?:\s+extends\s+\w+)?\s*\{', text, re.M):
            state_tokens = tokens(text[state.end()-1:])
            depth, state_stop = 0, None
            for token in state_tokens:
                depth += (token.text == '{') - (token.text == '}')
                if depth == 0:
                    state_stop = state.end()-1+token.end
                    break
            if state_stop is None:
                raise ValueError('Unclosed state')
            region = text[state.end():state_stop-1]
            state_header = re.compile(r'^[ \t]*' + HEADER.pattern[1:], re.M)
            for match in state_header.finditer(region):
                start = state.end()+match.end()-1
                depth, stop = 0, None
                for token in tokens(text[start:state_stop]):
                    depth += (token.text == '{') - (token.text == '}')
                    if depth == 0:
                        stop = start+token.end
                        break
                if stop is None:
                    raise ValueError('Unclosed state function')
                name = path.stem+'.'+state[1]+'.'+match[1]
                try:
                    metadata = package.function(name)
                    locals_text = '\n'.join(re.findall(r'^\s*local\s+[^;]+;', text[start:stop], re.M))
                    body = Emitter(package, mapping, metadata, types).body(locals_text)
                    edits.append((start, stop, body))
                    recovered.append(name)
                except (ValueError, KeyError, IndexError) as error:
                    errors[name] = str(error)
        for k, match in enumerate(headers):
            following = BOUNDARY.search(text, match.end())
            stop = following.start() if following else len(text)
            tail = text[match.end():stop]
            # defaultproperties are outside the final function, preserve them.
            default = re.search(r'^defaultproperties\b', tail, re.M)
            if default:
                stop = match.end()+default.start()
                tail = text[match.end():stop]
            if not args.all and path.name not in previous['rejected'] and not re.search(r'\bgoto\s+JL[0-9A-F]+', tail):
                continue
            name = path.stem + '.' + match[1]
            try:
                metadata = package.function(name)
                locals_text = '\n'.join(re.findall(r'^\s*local\s+[^;]+;', tail, re.M))
                body = Emitter(package, mapping, metadata, types).body(locals_text)
                edits.append((match.end()-1, stop, body+'\n\n'))
                recovered.append(name)
            except (ValueError, KeyError, IndexError) as error:
                errors[name] = str(error)
        for start, stop, body in sorted(edits, reverse=True):
            text = text[:start]+body+text[stop:]
        # In rejected classes the declarations still have original spelling;
        # native declarations themselves are already valid UnrealScript.
        files[path.name] = text
        if recovered:
            results[path.name] = recovered
    args.destination.mkdir(parents=True)
    for name, text in files.items():
        (args.destination/name).write_bytes(text.encode('latin1'))
    result = dict(recovered=results, errors=errors, ready_to_compile=not errors,
                  method='explicit basic-block dispatcher preserving serialized targets')
    (args.destination.parent/(args.destination.name+'-bytecode.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(functions=sum(map(len, results.values())), errors=errors), indent=2))


if __name__ == '__main__':
    main()
