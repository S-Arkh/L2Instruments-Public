"""Additional real HF/source fixtures and dependency/format failure checks."""
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from backend import Core, sha256

def main():
    core=Core();reports=[]
    for relative in ('gameAddWebWithD3D9/archive/addWeb/inputs/interface.u','gameAddWebWithD3D9/archive/addWeb/inputs/NWindow.u','int64/compiler/System/Interface.u'):
        path=ROOT.parent/relative
        dependencies=[str(ROOT.parent/'gameAddWebWithD3D9/archive/addWeb/workspace/System')] if relative.startswith('gameAddWebWithD3D9/') else []
        summary=core.request(operation='inspect',path=str(path),dependencies=dependencies,reload=True)
        row={'file':relative,'sha256':sha256(path),'version':summary['package']['version'],
             'licensee':summary['package']['licensee'],'dependencies':dependencies,'diagnostics':summary['diagnostics'],'modes':{}}
        for force in (False,True):
            counts={};examples=[]
            for cls in summary['package']['classes']:
                result=core.request(operation='decompile',path=str(path),dependencies=dependencies,class_id=cls['id'],force_bytecode=force)['result']
                counts[result['status']]=counts.get(result['status'],0)+1
                if result['issues'] and len(examples)<5:examples.append({'class':cls['path'],'issues':result['issues'][:3]})
            row['modes']['bytecode' if force else 'preferred_source']={'counts':counts,'examples':examples}
        reports.append(row)
    config_classes={}
    engine=ROOT.parent/'gameAddWebWithD3D9/profiles/gracia/inputs/Engine.u'
    for name,config in (('PlayerInput','User'),('GameInfo','System')):
        result=core.request(operation='decompile',path=str(engine),force_bytecode=True,**{'class':name})['result']
        declaration=next(line for line in result['code'].splitlines() if line.startswith('class '))
        assert ' config('+config+')' in declaration,declaration
        assert not any('Config class name:' in issue['message'] for issue in result['issues'])
        config_classes[name]=declaration
    with tempfile.TemporaryDirectory(prefix='uexplorer-formats-') as tmp:
        original=ROOT.parent/'gameAddWebWithD3D9/profiles/gracia/inputs/Interface.u'
        path=Path(tmp)/'Interface.u';path.write_bytes(original.read_bytes())
        response=core.request(operation='inspect',path=str(path),reload=True)
        assert any('Missing dependency' in s for s in response['diagnostics'])
        result=core.request(operation='decompile',path=str(path),**{'class':'LoginMenuWnd'})['result']
        assert result['status']=='partial'
        data=original.read_bytes();prefix='Lineage2Ver111'.encode('utf-16le')
        plain=bytes(b^0xac for b in data[len(prefix):])
        for envelope in ('plain','GamekitData111'):
            path.write_bytes(plain if envelope=='plain' else envelope.encode('utf-16le')+bytes(b^0xac for b in plain))
            response=core.request(operation='inspect',path=str(path),reload=True)
            assert len(response['package']['classes'])==239
        bad=bytearray(plain);bad[4:8]=bytes([255,0,0,0]);path.write_bytes(bad)
        try:core.request(operation='inspect',path=str(path),reload=True)
        except RuntimeError as error:assert 'Unsupported package version' in str(error)
        else:raise AssertionError('Unsupported format accepted')
    result={'core_sha256':sha256(core.library),'fixtures':reports,'config_declarations':config_classes,'missing_dependency':'passed',
            'plain_and_gamekit_envelopes':'passed','unsupported_version':'passed'}
    (ROOT/'tests/formats-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
