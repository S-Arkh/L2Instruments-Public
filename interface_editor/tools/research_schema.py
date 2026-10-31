"""Reproducible local schema research. Reports contain no paths or payload values."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from schema_tools import export_package, report, validate_package, validation_info
from schema_research import inspect_samples, suggest, apply_change


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', action='append', required=True, type=Path)
    parser.add_argument('--package', type=Path, help='Standalone schema JSON (otherwise use bundled catalog)')
    parser.add_argument('--schema', default='etoa5.XDAT')
    parser.add_argument('--suggest', action='store_true')
    parser.add_argument('--seconds', type=int, default=20)
    parser.add_argument('--apply', type=int, help='Explicitly accept this zero-based hypothesis index')
    parser.add_argument('--output', type=Path, help='Write a standalone schema to a new file')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error('--seconds must be 1..120')
    if args.apply is not None and (not args.suggest or args.output is None):
        parser.error('--apply requires --suggest and --output')
    if args.package:
        if args.package.stat().st_size > 16 * 1024 * 1024:
            parser.error('Schema package too large')
        package = validate_package(json.loads(args.package.read_text(encoding='utf-8')))
    else:
        package = export_package((ROOT / 'schemas/schemas.json').read_text(encoding='utf-8'), args.schema)
    samples = []
    for path in args.sample:
        with path.open('rb') as source:
            data = source.read(256 * 1024 * 1024 + 1)
        if len(data) > 256 * 1024 * 1024 or sum(map(len, samples)) + len(data) > 512 * 1024 * 1024:
            parser.error('Sample set too large')
        samples.append(data)
    if args.suggest:
        result = suggest(package, samples, seconds=args.seconds, max_trials=640)
        results = result['baseline']
        summary = {key: result[key] for key in ('trials', 'stopped')}
        summary['hypotheses'] = [{key: h[key] for key in ('change', 'progress', 'complete')}
                                 for h in result['hypotheses']]
        if args.apply is not None:
            if not 0 <= args.apply < len(result['hypotheses']):
                parser.error('Hypothesis index out of range')
            package = apply_change(package, result['hypotheses'][args.apply]['change'])
            results = inspect_samples(package, samples)
    else:
        results = inspect_samples(package, samples)
        summary = {}
    package.update(validation_info(samples, results))
    summary['status'] = package['status']
    summary['samples'] = [report('', data, package['versions'][0][1], [r]) for data, r in zip(samples, results)]
    if args.output:
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(package, output, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
