"""Compare decoded function instructions by symbolic references and branch targets."""
import argparse
import json
from collections import Counter
from pathlib import Path
from ue2package import Package


def functions(package):
    return {package.ref(i).casefold(): package.ref(i) for i, entry in enumerate(package.exports, 1)
            if package.ref(entry.cls) == 'Core.Function'}


def canonical(function, fold_byte_literals=False):
    rows = function['instructions']
    # Map memory addresses to instruction indices so compact package references
    # and different byte offsets cannot hide mismatched control flow.
    normalized = []
    pc_index = {}
    targets = {r[k] for r in rows for k in ('target', 'skip_end') if k in r}
    i = 0
    while i < len(rows):
        row = rows[i]
        pc_index[row['pc']] = len(normalized)
        if fold_byte_literals and row['kind'] == 'cast' and row['cast'] in ('3a', '3d', '43') and i + 1 < len(rows):
            child = rows[i + 1]
            value = child.get('value') if child['kind'] == 'constant' else {'int_zero': 0, 'int_one': 1}.get(child['kind'])
            valid = ((row['cast'] == '3a' and child['opcode'] == '24') or
                     (row['cast'] == '3d' and child['opcode'] in ('1d', '2c', '25', '26')) or
                     (row['cast'] == '43' and child['opcode'] == '1e'))
            if (valid and child['depth'] == row['depth'] + 1 and child['pc'] not in targets
                    and isinstance(value, (int, float)) and 0 <= value <= 255 and int(value) == value):
                value = int(value)
                if row['cast'] == '3a' and value in (0, 1):
                    folded = dict(opcode='25' if value == 0 else '26', kind='int_zero' if value == 0 else 'int_one')
                else:
                    folded = dict(opcode='2c' if row['cast'] == '3a' else '24', kind='constant', value=value)
                normalized.append(dict(pc=row['pc'], depth=row['depth'], **folded))
                i += 2
                continue
        normalized.append(row)
        i += 1
    pc_index[function['memory_size']] = len(normalized)
    result = []
    references = {'local', 'instance', 'default', 'native_parameter', 'struct_member',
                  'object', 'name', 'virtual_call', 'global_call', 'final_call',
                  'dynamic_cast', 'class_cast', 'struct_equal', 'struct_not_equal',
                  'delegate_property', 'delegate_name'}
    for row in normalized:
        item = {k: v for k, v in row.items() if k not in ('pc', 'serial', 'line', 'skip_end')}
        if row['kind'] in references and isinstance(item.get('value'), str):
            item['value'] = item['value'].casefold()
        if 'target' in item and not (row['kind'] == 'case' and item['target'] == 65535):
            item['target'] = pc_index.get(item['target'], ('invalid', item['target']))
        if fold_byte_literals and 'skip_end' in row:
            item.pop('skip', None)
            item.pop('size', None)
            item['skip_target'] = pc_index.get(row['skip_end'], ('invalid', row['skip_end']))
        result.append(item)
    return result


def compare(original_path, rebuilt_path):
    original, rebuilt = Package(original_path), Package(rebuilt_path)
    old, new = functions(original), functions(rebuilt)
    report = dict(original=original.summary(), rebuilt=rebuilt.summary(),
                  missing_functions=sorted(old.keys() - new.keys()),
                  extra_functions=sorted(new.keys() - old.keys()),
                  identical_functions=0, byte_literal_equivalent_functions=[], changed_functions={},
                  function_metadata_differences={}, decode_errors={})
    def import_keys(package):
        return {(package.ref(-i).casefold(), e.class_package.casefold(), e.cls.casefold())
                for i, e in enumerate(package.imports, 1)}
    def export_keys(package):
        return Counter((package.ref(i).casefold(), package.ref(e.cls).casefold())
                       for i, e in enumerate(package.exports, 1))
    ia, ib = import_keys(original), import_keys(rebuilt)
    ea, eb = export_keys(original), export_keys(rebuilt)
    report['missing_imports'], report['extra_imports'] = sorted(ia - ib), sorted(ib - ia)
    report['missing_exports'], report['extra_exports'] = sorted((ea - eb).elements()), sorted((eb - ea).elements())
    classes_a = {original.ref(i).casefold(): (original.ref(i), e) for i, e in enumerate(original.exports, 1) if e.cls == 0}
    classes_b = {rebuilt.ref(i).casefold(): (rebuilt.ref(i), e) for i, e in enumerate(rebuilt.exports, 1) if e.cls == 0}
    report['class_counts'] = [len(classes_a), len(classes_b)]
    report['class_metadata_differences'] = {}
    for key in sorted(classes_a.keys() & classes_b.keys()):
        na, entry_a = classes_a[key]
        nb, entry_b = classes_b[key]
        signature_a = [original.class_flags(na), original.ref(entry_a.super).casefold()]
        signature_b = [rebuilt.class_flags(nb), rebuilt.ref(entry_b.super).casefold()]
        if signature_a != signature_b:
            report['class_metadata_differences'][na] = [signature_a, signature_b]
    for key in sorted(old.keys() & new.keys()):
        try:
            a, b = original.function(old[key]), rebuilt.function(new[key])
            metadata_a = [a[k] for k in ('flags', 'native', 'precedence', 'replication')]
            metadata_b = [b[k] for k in ('flags', 'native', 'precedence', 'replication')]
            if metadata_a != metadata_b:
                report['function_metadata_differences'][old[key]] = [metadata_a, metadata_b]
            left, right = canonical(a), canonical(b)
            if left == right:
                report['identical_functions'] += 1
            elif canonical(a, True) == canonical(b, True):
                report['byte_literal_equivalent_functions'].append(old[key])
            else:
                first = next((i for i, (x, y) in enumerate(zip(left, right)) if x != y), min(len(left), len(right)))
                report['changed_functions'][old[key]] = dict(
                    first_difference=first, original_instruction_count=len(left), rebuilt_instruction_count=len(right),
                    original=left[max(0, first - 1):first + 3], rebuilt=right[max(0, first - 1):first + 3])
        except ValueError as error:
            report['decode_errors'][old[key]] = str(error)
    sa = {original.ref(i).casefold(): original.ref(i) for i, e in enumerate(original.exports, 1)
          if original.ref(e.cls) == 'Core.State'}
    sb = {rebuilt.ref(i).casefold(): rebuilt.ref(i) for i, e in enumerate(rebuilt.exports, 1)
          if rebuilt.ref(e.cls) == 'Core.State'}
    report['state_counts'] = [len(sa), len(sb)]
    report['state_differences'] = {}
    for key in sorted(sa.keys() & sb.keys()):
        try:
            a, b = original.state(sa[key]), rebuilt.state(sb[key])
            signature_a = [a['probe'], a['ignore'], a['flags'], a['fields'][0].casefold()]
            signature_b = [b['probe'], b['ignore'], b['flags'], b['fields'][0].casefold()]
            if canonical(a, True) != canonical(b, True) or signature_a != signature_b:
                report['state_differences'][sa[key]] = 'State instructions or flags/probes/super differ'
        except ValueError as error:
            report['decode_errors'][sa[key]] = str(error)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original', type=Path)
    parser.add_argument('rebuilt', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--require-equivalent', action='store_true')
    args = parser.parse_args()
    result = compare(args.original, args.rebuilt)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding='utf-8')
    summary = {k: v for k, v in result.items() if k not in ('changed_functions', 'decode_errors', 'byte_literal_equivalent_functions')}
    summary['byte_literal_equivalent_functions'] = len(result['byte_literal_equivalent_functions'])
    print(json.dumps(summary, indent=2))
    print('Changed:', len(result['changed_functions']), 'Decode errors:', len(result['decode_errors']))
    if args.require_equivalent and any(result[k] for k in (
            'changed_functions', 'decode_errors', 'missing_functions', 'extra_functions',
            'missing_imports', 'extra_imports', 'missing_exports', 'extra_exports', 'class_metadata_differences',
            'function_metadata_differences', 'state_differences')):
        raise SystemExit(1)
