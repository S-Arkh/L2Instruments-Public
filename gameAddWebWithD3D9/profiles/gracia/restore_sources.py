"""Restore known SDK native names/operators in WOTgreal output; never guess control flow."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / 'tools/ue2'))
from uc_declarations import tokens
from audit_exported_sources import audit
from ue2package import Package


def repair_literals(text, functions):
    """WOTgreal prints string contents without escaping; use actual package values."""
    values = {row['value'] for f in functions.values() for row in f['instructions'] if row['kind'] == 'string'}
    candidates = sorted(('"' + value + '"' for value in values), key=len, reverse=True)
    edits, i = [], 0
    while i < len(text):
        if text.startswith('//', i):
            end = text.find('\n', i)
            i = len(text) if end < 0 else end + 1
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0:
                raise ValueError('Unterminated comment')
            i = end + 2
        elif text[i] == "'":
            end = text.find("'", i + 1)
            if end < 0:
                raise ValueError('Unterminated name literal')
            i = end + 1
        elif text[i] == '"':
            raw = next((value for value in candidates if text.startswith(value, i)), None)
            if raw is None:
                end = text.find('"', i + 1)
                if end < 0:
                    raise ValueError('Unterminated string not found in bytecode')
                raw = text[i:end+1]
                if '\\' in raw:
                    raise ValueError('Unverified escaped literal')
            content = raw[1:-1]
            escaped = content.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '\\r').replace('\n', '\\n')
            if escaped != content:
                edits.append((i, i+len(raw), '"'+escaped+'"'))
            i += len(raw)
        else:
            i += 1
    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    return text, len(edits)


def repair_loops(text, functions):
    """Restore only braced while loops with matching serialized backward branches."""
    ts = tokens(text)
    pairs, stack = {}, []
    for i, t in enumerate(ts):
        if t.text in ('(', '{', '['):
            stack.append(i)
        elif t.text in (')', '}', ']'):
            if not stack or ts[stack[-1]].text != {')':'(', '}':'{', ']':'['}[t.text]:
                raise ValueError('Unbalanced delimiters')
            pairs[stack.pop()] = i
    if stack:
        raise ValueError('Unclosed delimiters in decompiled source')
    edits, evidence, i = [], [], 0
    while i < len(ts):
        if ts[i].text.lower() not in ('function', 'event'):
            i += 1
            continue
        header = i
        while i < len(ts) and ts[i].text not in ('(', ';'):
            i += 1
        if i == len(ts) or ts[i].text == ';':
            continue
        name = ts[i-1].text
        i = pairs[i] + 1
        if ts[i].text != '{':
            continue
        end = pairs[i]
        f = functions.get(name.casefold())
        if f:
            rows = [row for row in f['instructions'] if row['depth'] == 0]
            branches = [row for row in rows if row['kind'] == 'jump_if_not']
            conditions = [k for k in range(i+1, end) if ts[k].text.lower() == 'if']
            # A differing count means WOTgreal already restructured flow: don't guess.
            if len(branches) == len(conditions):
                for condition, branch in zip(conditions, branches):
                    opening = condition + 1
                    if ts[opening].text != '(':
                        continue
                    body = pairs[opening] + 1
                    if ts[body].text != '{':
                        continue
                    close = pairs[body]
                    if close < 3 or ts[close-3].text.lower() != 'goto' or ts[close-1].text != ';':
                        continue
                    label = ts[close-2].text
                    if not re.fullmatch(r'JL[0-9A-F]+', label) or int(label[2:], 16) != branch['pc']:
                        continue
                    back = next((r for r in rows if r['kind'] == 'jump' and r['target'] == branch['pc'] and r['pc'] + 3 == branch['target']), None)
                    if back is None or (close+1 < end and ts[close+1].text.lower() == 'else'):
                        continue
                    edits.extend([(ts[condition].start, ts[condition].end, 'while'),
                                  (ts[close-3].start, ts[close-1].end, '')])
                    evidence.append(dict(function=name, condition_pc=branch['pc'], jump_pc=back['pc'], exit_pc=branch['target']))
        i = end + 1
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, evidence


def native_mapping(report):
    result = {}
    for index, info in report['natives'].items():
        declarations = set(info['declarations'])
        if not declarations:
            continue
        if len(declarations) != 1:
            raise ValueError(f'Ambiguous native {index}')
        declaration = declarations.pop()
        match = re.search(r'\b(operator\(\d+\)|preoperator|postoperator|function)\s+(.+?)\s*\(', declaration, re.I)
        if not match:
            raise ValueError(f'Cannot parse SDK declaration: {declaration}')
        kind = match[1].lower()
        name = match[2].split()[-1]
        result[index] = (kind, name)
    return result


def restore(text, mapping):
    ts = tokens(text)
    counts = Counter()

    def region(begin, end):
        edits = []
        i = begin
        while i < end:
            match = re.fullmatch(r'UnknownFunction(\d+)', ts[i].text)
            if not match or i + 1 >= end or ts[i + 1].text != '(':
                i += 1
                continue
            first, depth, j = i + 2, 1, i + 2
            args = []
            while j < end:
                word = ts[j].text
                if word == '(':
                    depth += 1
                elif word == ')':
                    depth -= 1
                    if depth == 0:
                        if j > first:
                            args.append(region(first, j))
                        break
                elif word == ',' and depth == 1:
                    args.append(region(first, j))
                    first = j + 1
                j += 1
            if depth:
                raise ValueError(f'Unbalanced native call at {ts[i].start}')
            index = match[1]
            if index not in mapping:
                replacement = ts[i].text + '(' + ', '.join(args) + ')'
            else:
                kind, name = mapping[index]
                if kind == 'function':
                    replacement = name + '(' + ', '.join(args) + ')'
                elif kind.startswith('operator'):
                    if len(args) != 2:
                        raise ValueError(f'Expected two arguments: {index}')
                    replacement = f'({args[0]} {name} {args[1]})'
                else:
                    if len(args) != 1:
                        raise ValueError(f'Expected one argument: {index}')
                    replacement = '(' + (name + args[0] if kind == 'preoperator' else args[0] + name) + ')'
                # UnrealScript statement parsing expects an lvalue before ++/+= etc.
                statement = (i == 0 or ts[i - 1].text in (';', '{', '}')) and j + 1 < len(ts) and ts[j + 1].text == ';'
                if statement and (kind in ('preoperator', 'postoperator') or name in ('+=', '-=', '*=', '/=')):
                    replacement = replacement[1:-1]
                counts[index] += 1
            edits.append((ts[i].start, ts[j].end, replacement))
            i = j + 1
        if begin == end:
            return ''
        start, stop = ts[begin].start, ts[end - 1].end
        value = text[start:stop]
        for a, b, replacement in reversed(edits):
            value = value[:a-start] + replacement + value[b-start:]
        return value

    if not ts:
        return text, counts
    return text[:ts[0].start] + region(0, len(ts)) + text[ts[-1].end:], counts


def control_flow(text):
    """Find missing JL labels per function (labels are local, not class-wide)."""
    ts = tokens(text)
    functions = []
    i = 0
    while i < len(ts):
        if ts[i].text.lower() not in ('function', 'event'):
            i += 1
            continue
        start = i
        while i < len(ts) and ts[i].text not in ('{', ';'):
            i += 1
        if i == len(ts) or ts[i].text == ';':
            i += 1
            continue
        header = text[ts[start].start:ts[i].start].strip()
        begin = i
        depth = 1
        i += 1
        while i < len(ts) and depth:
            depth += (ts[i].text == '{') - (ts[i].text == '}')
            i += 1
        body = ts[begin:i]
        labels = {body[k].text for k in range(len(body)-1) if body[k+1].text == ':' and re.fullmatch(r'JL[0-9A-F]+', body[k].text)}
        missing = [dict(label=body[k+1].text, line=text.count('\n', 0, body[k].start)+1)
                   for k in range(len(body)-1) if body[k].text.lower() == 'goto'
                   and re.fullmatch(r'JL[0-9A-F]+', body[k+1].text) and body[k+1].text not in labels]
        if missing:
            functions.append(dict(function=header, missing_targets=missing))
    return functions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('classes', type=Path)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.classes)
    if report['missing'] or report['extra']:
        raise ValueError('Exported class set does not match the profiled Interface')
    if args.destination.exists():
        raise ValueError('Choose a new destination to preserve previous work')
    mapping = native_mapping(report)
    package = Package(ROOT/'inputs/Interface.u')
    functions = {}
    for index, entry in enumerate(package.exports, 1):
        if package.ref(entry.cls) == 'Core.Function':
            path = package.ref(index)
            owner, name = path.rsplit('.', 1)
            functions.setdefault(owner.casefold(), {})[name.casefold()] = package.function(path)
    files, totals, flow, rejected, repairs = {}, Counter(), {}, {}, {}
    for path in sorted(args.classes.glob('*.uc')):
        text = path.read_bytes().decode('latin1')
        try:
            members = functions.get(path.stem.casefold(), {})
            text, literals = repair_literals(text, members)
            text, loops = repair_loops(text, members)
            files[path.name], counts = restore(text, mapping)
            problems = control_flow(text)
            repairs[path.name] = dict(literals=literals, loops=loops)
        except ValueError as error:
            # Preserve the source verbatim rather than guessing malformed literals.
            files[path.name] = path.read_bytes().decode('latin1')
            rejected[path.name] = str(error)
            continue
        totals.update(counts)
        if problems:
            flow[path.name] = problems
    args.destination.mkdir(parents=True)
    for name, text in files.items():
        (args.destination / name).write_bytes(text.encode('latin1'))
    result = dict(profile='gracia_epilogue_0941cac5', source_audit=report,
                  restored_calls=sum(totals.values()), restored_indices=dict(totals),
                  missing_control_flow_targets=flow, rejected=rejected, repairs=repairs, ready_to_compile=False)
    (args.destination.parent / (args.destination.name + '-restoration.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(restored_calls=result['restored_calls'], restored_indices=len(totals),
                         unresolved_indices=report['unresolved_indices'],
                         repaired_loops=sum(len(r['loops']) for r in repairs.values()),
                         repaired_literals=sum(r['literals'] for r in repairs.values()),
                         missing_goto_targets=sum(len(f['missing_targets']) for fs in flow.values() for f in fs),
                         affected_classes=len(flow), rejected=rejected, ready_to_compile=False), indent=2))


if __name__ == '__main__':
    main()
