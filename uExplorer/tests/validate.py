"""Real package regression against the existing Python parser, plus export safety."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
INPUTS=Path(os.environ.get('UEXPLORER_GRACIA_SYSTEM', str(ROOT.parent/'local/gracia/System')))
sys.path[:0]=[str(ROOT/'python'),str(ROOT.parent/'gameAddWebWithD3D9/tools/ue2')]
from backend import Core, export_classes, targets, sha256
from ue2package import Package
from extract_sources import script_text


def main():
    core=Core()
    package=INPUTS/'Interface.u'
    reference=Package(package)
    summary=core.request(operation='inspect',path=str(package),reload=True)
    assert len(summary['package']['classes'])==239
    assert not summary['diagnostics'],summary['diagnostics'][:10]
    functions=0
    def flatten(nodes):
        for node in nodes:
            yield (node['pc'],node['opcode'])
            yield from flatten(node['children'])
    for index,entry in enumerate(reference.exports,1):
        if reference.ref(entry.cls)!='Core.Function':continue
        name=reference.ref(index);expected=reference.function(name)
        actual=core.request(operation='function',path=str(package),function=name)['result']
        assert actual['size']==expected['memory_size'],name
        assert actual['flags']==expected['flags'] and actual['native']==expected['native'],name
        assert list(flatten(actual['nodes']))==[(n['pc'],int(n['opcode'],16)) for n in expected['instructions']],name
        functions+=1
    statuses={};issues=[]
    for item in summary['package']['classes']:
        result=core.request(operation='decompile',path=str(package),class_id=item['id'])['result']
        statuses[result['status']]=statuses.get(result['status'],0)+1
        issues.extend(result.get('issues',[]))
        assert 'class '+item['name'] in result['code']
    source_package=INPUTS/'NWindow.u'
    source_reference=Package(source_package)
    count=0
    for index,entry in enumerate(source_reference.exports,1):
        if entry.cls!=0:continue
        try:
            _,text_entry=source_reference.find(entry.name+'.ScriptText')
            expected,_,_=script_text(source_reference,text_entry)
        except ValueError:continue
        result=core.request(operation='decompile',path=str(source_package),class_id=index)['result']
        if result['method']=='ScriptText':
            assert bytes.fromhex(result['raw_hex'])==expected,entry.name
            count+=1
    with tempfile.TemporaryDirectory(prefix='uexplorer-test-') as tmp:
        selected=summary['package']['classes'][:2]
        report=export_classes(core,package,selected,tmp)
        assert len(report['classes'])==2 and not report['counts']['failed']
        assert len(list(Path(tmp).rglob('*.uc')))==2
        try:export_classes(core,package,selected,tmp)
        except FileExistsError:pass
        else:raise AssertionError('Existing source overwritten without permission')
        cancelled=export_classes(core,package,selected,tmp,overwrite=True,cancelled=lambda:True)
        assert cancelled['cancelled'] and not cancelled['classes']
        try:targets(package,[{'path':'../escape'}],tmp)
        except ValueError:pass
        else:raise AssertionError('Unsafe output path accepted')
        bad=Path(tmp)/'bad.u';bad.write_bytes(package.read_bytes()[:128])
        try:core.request(operation='inspect',path=str(bad),reload=True)
        except RuntimeError:pass
        else:raise AssertionError('Truncated package accepted')
    result={'core_sha256':sha256(core.library),'package_sha256':sha256(package),
            'functions_compared':functions,'scripttext_exact':count,'classes':statuses,'issues':issues}
    (ROOT/'tests/validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='issues'},indent=2))
    print('Issues:',len(issues));print(json.dumps(issues[:15],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
