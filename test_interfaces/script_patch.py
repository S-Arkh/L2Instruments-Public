"""Wrap an ordinary login click handler in an isolated generated-source copy."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def patch_click(source, profile, build_id, modern=False):
    if profile not in ('gracia', 'high_five', 'japan', 'korean'):
        raise ValueError('Unknown logical profile')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', build_id):
        raise ValueError('Build identity must be a short identifier or hash')
    for name in ('CompilerOriginalOnClickButton', 'CompilerShowTestMessage', 'bCompilerTestRunning', 'Btn_CompilerTest'):
        if name.lower() in source.lower():
            raise ValueError('Existing test integration or name collision: ' + name)
    matches = list(re.finditer(r'(?im)^function\s+OnClickButton\s*\(\s*string\s+(\w+)\s*\)', source))
    if len(matches) != 1:
        raise ValueError('Expected one ordinary generated OnClickButton(string) handler')
    match = matches[0]
    header = re.search(r'(?ims)^class\s+\w+\b[^;]*;', source)
    if not header or header.end() > match.start():
        raise ValueError('Expected generated class header before click handler')
    original = source[match.start():match.end()]
    source = source[:match.start()] + original.replace('OnClickButton', 'CompilerOriginalOnClickButton', 1) + source[match.end():]
    source = source[:header.end()] + '\n\nvar bool bCompilerTestRunning;' + source[header.end():]
    runner = 'CompilerSortTestRunner' if modern else 'CompilerTestRunner'
    if profile == 'korean':
        source += '''
function CompilerShowTestMessage(string Message)
{
    GetTextBoxHandle("LogIn.Txt_Msg").SetText(Message);
    GetWindowHandle("LogIn.Txt_Msg").ShowWindow();
}
'''
    else:
        source += '''
function CompilerShowTestMessage(string Message)
{
    ShowMessageInLogin(Message);
}
'''
    source += '''
function OnClickButton(string strID)
{
    local CompilerTestRunner TestRunner;
    local string TestSummary;
    if (strID != "Btn_CompilerTest")
    {
        CompilerOriginalOnClickButton(strID);
        return;
    }
    if (bCompilerTestRunning) return;
    bCompilerTestRunning = true;
    CompilerShowTestMessage("Compiler tests running. Results: System/test.txt");
    TestRunner = new class'%s';
    if (TestRunner == None)
    {
        bCompilerTestRunning = false;
        CompilerShowTestMessage("Cannot create compiler test runner");
        return;
    }
    TestSummary = TestRunner.Run("%s", "%s");
    bCompilerTestRunning = false;
    CompilerShowTestMessage(TestSummary);
}
''' % (runner, profile, build_id)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--profile', choices=('gracia', 'high_five', 'japan', 'korean'), required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--client-sort', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT/'test_interfaces/local'):
        parser.error('Output must be a new source file beneath test_interfaces/local')
    text = args.input.read_text(encoding='utf-8-sig')
    result = patch_click(text, args.profile, args.build_id, args.client_sort)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as stream:
        stream.write(result)
    print(json.dumps(dict(profile=args.profile, input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                          source_generated=True, compiled=False, runtime_tested=False), indent=2))


if __name__ == '__main__':
    main()
