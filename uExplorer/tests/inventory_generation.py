"""Build an anonymized, occurrence-level backlog from a completed generation audit."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def category(message):
    if 'Unsupported property type' in message:
        return 'property-types'
    if 'tagged default type' in message:
        return 'defaults'
    if 'replicat' in message.lower():
        return 'replication'
    if 'iterator' in message:
        return 'iterators'
    if 'State ' in message:
        return 'states'
    return 'unclassified'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = args.audit.read_bytes()
    audit = json.loads(raw)
    labels = {name: f'P{i + 1}' for i, name in enumerate(sorted(
        {p['profile'] for p in audit['packages']}))}
    groups = {}
    packages = []
    for package in audit['packages']:
        profile = labels[package['profile']]
        row = dict(profile=profile, file=package['file'])
        if package.get('absent'):
            row['absent'] = True
            packages.append(row)
            continue
        row.update(sha256=package['sha256'], version=package['version'],
                   licensee=package['licensee'], modes={})
        for mode, data in package['modes'].items():
            row['modes'][mode] = data['counts']
            observed = Counter()
            for cls in data['classes']:
                for issue in cls['issues']:
                    message = re.sub(r' at PC \d+', '', issue['message'])
                    observed[message] += 1
                    group = groups.setdefault(message, dict(category=category(message),
                                                            occurrences=[]))
                    group['occurrences'].append(dict(profile=profile,
                        package=package['file'], mode=mode, owner=cls['name'],
                        scope=issue['scope']))
            if dict(observed) != data['issues']:
                raise ValueError(f'Issue totals disagree for {profile}/{package["file"]}/{mode}')
        packages.append(row)
    result = dict(audit_sha256=hashlib.sha256(raw).hexdigest(),
                  core_sha256=audit['core_sha256'], packages=packages,
                  groups=[dict(message=message, **value) for message, value in sorted(groups.items())])
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    for group in result['groups']:
        bytecode = [o for o in group['occurrences'] if o['mode'] == 'bytecode']
        owners = {(o['profile'], o['package'], o['owner']) for o in bytecode}
        print(f'{group["category"]}: {len(bytecode)} occurrences, {len(owners)} classes: {group["message"]}')


if __name__ == '__main__':
    main()
