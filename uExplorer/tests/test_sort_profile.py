"""Validate explicit SDK Sort dialect through the production API, including cache isolation."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from backend import Core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    before = hashlib.sha256(args.package.read_bytes()).hexdigest()
    core = Core(args.library.resolve())
    request = dict(path=str(args.package.resolve()), function='SortProbe.SortAll')
    for profile in ('auto', 'sdk-client-sort', 'auto', 'sdk-client-sort'):
        summary = core.request(path=request['path'], bytecode_profile=profile)['package']
        assert (summary['version'], summary['licensee'], summary['bytecode_profile']) == (126, 0, profile)
        try:
            result = core.request(operation='function', bytecode_profile=profile, **request)['result']
        except RuntimeError as error:
            assert profile == 'auto' and 'Array sort requires' in str(error), str(error)
        else:
            assert profile == 'sdk-client-sort'
            assert result['nodes']
            recovered = core.request(operation='decompile', path=request['path'],
                                     **{'class': 'SortProbe'}, force_bytecode=True,
                                     bytecode_profile=profile)['result']
            assert recovered['status'] == 'recovered', recovered['issues']
    try:
        core.request(path=request['path'], bytecode_profile='unknown')
    except RuntimeError as error:
        assert 'Unknown bytecode profile' in str(error)
    else:
        raise AssertionError('Unknown profile accepted')
    assert hashlib.sha256(args.package.read_bytes()).hexdigest() == before
    print('PASS: production Sort profile, strict default, cache isolation and immutable package')


if __name__ == '__main__':
    main()
