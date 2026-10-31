"""Bounded, evidence-driven layout hypotheses; never claims semantic recovery."""
import copy
import json
import time

from _interface_core import Document
from schema_tools import validate_package


def scan_anchors(package, data, offset, radius=65536, limit=64):
    """Nearby serialized type tags; anchors are candidates, never object boundaries."""
    types = {name.split('.', 1)[1] for name in package['records'] if name.count('.') == 1}
    start, end = max(0, offset - 256), min(len(data), offset + radius)
    hits = []
    for name in types:
        encoded = name.encode('ascii')
        if len(encoded) >= 63:
            continue
        tag = bytes([len(encoded) + 1]) + encoded + b'\0'
        position = data.find(tag, start, end)
        while position >= 0 and len(hits) < limit * max(1, len(types)):
            hits.append({'offset': position, 'size': len(tag), 'kind': 'anchor',
                         'path': '<?>', 'field': name, 'value': name})
            position = data.find(tag, position + len(tag), end)
    return sorted(hits, key=lambda h: h['offset'])[:limit]


def locate_field(records, record, field):
    """Return the declaring record and operation path (including conditional arms)."""
    def walk(ops, path):
        for index, op in enumerate(ops):
            here = path + [index]
            if op.get('op') == 'field' and op['name'] == field:
                return here
            if op.get('op') == 'if':
                for arm in ('yes', 'no'):
                    found = walk(op[arm], here + [arm])
                    if found is not None:
                        return found
        return None
    while record:
        found = walk(records[record]['ops'], [])
        if found is not None:
            return record, found
        record = records[record]['base']
    raise ValueError('Field declaration not found')


def apply_change(package, change):
    result = copy.deepcopy(package)
    ops = result['records'][change['record']]['ops']
    for key in change['path'][:-1]:
        ops = ops[key]
    index = change['path'][-1]
    if change['action'] == 'insert':
        for offset, kind in enumerate(change['kinds']):
            name = change['name'] + (f'_{offset}' if offset else '')
            ops.insert(index + offset, {'op': 'field', 'name': name, 'kind': kind,
                                       'default': '' if kind == 'string' else 0})
    elif change['action'] == 'remove':
        del ops[index:index + change.get('count', 1)]
    else:
        ops[index]['kind'] = change['kind']
        ops[index]['default'] = '' if change['kind'] == 'string' else 0
        ops[index].pop('enum', None)
        ops[index].pop('type', None)
    result['draft'] = True
    result['status'] = 'draft'
    result.pop('validation', None)
    return result


def inspect_samples(package, samples, limit=2000):
    validate_package(package)
    schema = package['versions'][0][1]
    document = Document(json.dumps(package))
    return [document.diagnose(data, schema, limit) for data in samples]


def suggest(package, samples, cancelled=lambda: False, seconds=20, max_trials=240):
    """Try small changes near a failure, require non-regression on every sample.

    Offsets are evidence of progress only, not probabilities of correctness.
    The caller explicitly accepts each change; no arbitrary byte skipping.
    """
    started = time.monotonic()
    if not samples:
        raise ValueError('At least one sample is required')
    baseline = []
    for data in samples:
        if cancelled() or time.monotonic() - started >= seconds:
            return {'baseline': baseline, 'hypotheses': [], 'trials': 0,
                    'stopped': 'cancelled' if cancelled() else 'budget'}
        baseline.extend(inspect_samples(package, [data], 128))
    failure = next((r.get('failure') for r in baseline if r.get('failure')), None)
    if not failure:
        return {'baseline': baseline, 'hypotheses': [], 'trials': 0, 'stopped': 'no_field_failure'}
    sites = [(failure['type'], failure['field'])]
    # A wrong layout can consume many plausible scalars before the string fails.
    # Scalar anomalies are hints only: unusual values remain legal in the reader.
    for result in baseline:
        anomalies = [result['first_anomaly']] if result.get('first_anomaly') else []
        if anomalies:
            first = anomalies[0]
            sites.insert(0, (first['type'], first['field']))
    for result in baseline:
        for event in reversed(result['trace']):
            site = (event['type'], event.get('field'))
            if site[1] and event['kind'] not in ('list', 'object') and site not in sites:
                sites.append(site)
            if len(sites) >= 48:
                break
    changes, seen = [], set()
    for record, field in sites:
        owner, path = locate_field(package['records'], record, field)
        key = (owner, tuple(path))
        if key in seen:
            continue
        seen.add(key)
        common = {'record': owner, 'path': path, 'field': field}
        # Use neutral names: the binary evidence cannot recover semantic names.
        suffix = 1
        existing = json.dumps(package['records'][owner])
        while f'unknown_{suffix:03}' in existing:
            suffix += 1
        for kinds in ([['int'] * n for n in range(1, 9)] + [['string'], ['compact']]):
            changes.append(dict(common, action='insert', kinds=kinds, name=f'unknown_{suffix:03}'))
        siblings = package['records'][owner]['ops']
        for part in path[:-1]:
            siblings = siblings[part]
        op = siblings[path[-1]]
        if op['kind'] not in ('list', 'object'):
            for count in range(1, 9):
                group = siblings[path[-1]:path[-1] + count]
                if len(group) != count or any(o.get('op') != 'field' or o.get('kind') in ('list', 'object') for o in group):
                    break
                changes.append(dict(common, action='remove', count=count))
            for kind in ('int', 'string', 'compact'):
                if op['kind'] != kind:
                    changes.append(dict(common, action='replace', kind=kind))
    hypotheses, trials, stopped = [], 0, 'complete'
    for change in changes:
        if cancelled() or time.monotonic() - started >= seconds or trials >= max_trials:
            stopped = 'cancelled' if cancelled() else 'budget'
            break
        candidate = apply_change(package, change)
        trials += 1
        try:
            results = []
            for data in samples:
                if cancelled() or time.monotonic() - started >= seconds:
                    break
                results.extend(inspect_samples(candidate, [data], 32))
            if len(results) != len(samples):
                stopped = 'cancelled' if cancelled() else 'budget'
                break
        except (ValueError, RuntimeError):
            continue
        def progress(r):
            offset = r['failure']['offset'] if r.get('failure') else r['cursor']
            plausible = min(offset, r['first_anomaly']['offset']) if r.get('first_anomaly') else offset
            return (int(r['compatible'] and r['tail_bytes'] == 0), plausible, offset)
        before, after = [progress(r) for r in baseline], [progress(r) for r in results]
        if all(a >= b for a, b in zip(after, before)) and any(a > b for a, b in zip(after, before)):
            hypotheses.append({'change': change, 'progress': after,
                               'complete': all(a[0] for a in after), 'results': results})
    hypotheses.sort(key=lambda h: (h['complete'], min(h['progress'])), reverse=True)
    return {'baseline': baseline, 'hypotheses': hypotheses[:12], 'trials': trials, 'stopped': stopped}
