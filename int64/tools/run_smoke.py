"""Compile positive/negative regression cases in separate copies of UCC."""
import argparse
import os
from pathlib import Path
import subprocess
from prepare_smoke import prepare
from check_smoke import check


NEGATIVE = {
    'overflow_positive': ('function int64 Test() { return 9223372036854775808; }', 'outside signed INT64 range'),
    'overflow_negative': ('function int64 Test() { return -9223372036854775809; }', 'outside signed INT64 range'),
    'implicit_narrowing': ('function int Test(int64 Value) { return Value; }', 'Type mismatch'),
    'out_widening': ('function Sink(out int64 Value) {} function Test() { local int Value; Sink(Value); }', 'Type mismatch'),
    'unrelated_struct': ('struct Other { var int Left, Right; }; function Test() { local Other Value; Value = 1; }', 'Type mismatch'),
    'bad_default': ('var int64 Value;\ndefaultproperties\n{\n Value=9223372036854775808\n}', 'Invalid numeric INT64 default value'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--launcher', required=True, type=Path)
    parser.add_argument('--wine', type=Path)
    parser.add_argument('--case', action='append', choices=('positive', *NEGATIVE))
    args = parser.parse_args()
    root = args.destination.resolve()
    if root.exists():
        raise ValueError('Use a fresh destination for a reproducible test')
    root.mkdir(parents=True)
    launcher = args.launcher.resolve()
    for case in (args.case or ('positive', *NEGATIVE)):
        system = prepare(root / case)
        if case != 'positive':
            source, diagnostic = NEGATIVE[case]
            (system.parent / 'Int64Smoke/Classes/Int64Probe.uc').write_text(
                'class Int64Probe extends Object;\n' + source + '\n', encoding='ascii')
        system_arg = str(system)
        if args.wine and os.name != 'nt':
            system_arg = 'Z:' + system_arg.replace('/', '\\')
        command = [str(launcher), '--system', system_arg, 'make', '-NoBind']
        if args.wine:
            command.insert(0, str(args.wine))
        log = system.parent / 'compile.log'
        # A Wine background service can inherit stdout and keep a PIPE open
        # after UCC has exited. A log file avoids waiting for that unrelated EOF.
        with log.open('wb') as output:
            process = subprocess.run(command, cwd=system, stdout=output,
                                     stderr=subprocess.STDOUT, timeout=120)
        transcript = log.read_text(encoding='utf-8', errors='replace')
        if case == 'positive':
            if process.returncode or 'Success - 0 error(s), 0 warning(s)' not in transcript:
                raise RuntimeError(f'{case} failed ({process.returncode}):\n{transcript}')
            check(system / 'Int64Smoke.u')
        elif not process.returncode or diagnostic.casefold() not in transcript.casefold() or 'Compile aborted due to errors.' not in transcript or (system / 'Int64Smoke.u').exists():
            raise RuntimeError(f'{case}: expected a clean compile rejection, got {process.returncode}:\n{transcript}')
        print(f'PASS compile case: {case} (UCC exit {process.returncode})')


if __name__ == '__main__':
    main()
