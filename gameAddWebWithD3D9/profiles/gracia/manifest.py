"""Validate the Gracia UI/package and publish the install manifest."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]/'tools/ue2'))
from ue2package import Package

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_xdat():
    sys.path.insert(0, str(ROOT.parents[2]/'interface_editor/app'))
    from _interface_core import Document
    schema = (ROOT.parents[2]/'interface_editor/schemas/schemas.json').read_text()
    docs = []
    for path in (ROOT/'inputs/Interface.xdat', ROOT/'result/system/Interface.xdat'):
        doc = Document(schema); doc.load(str(path), 'ct24.XDAT')
        if doc.serialize() != path.read_bytes(): raise ValueError('XDAT round-trip differs')
        docs.append(doc)
    def snapshot(doc, node):
        return dict(name=doc.info(node)['name'], type=doc.info(node)['type'],
                    properties={p['name']:p['value'] for p in doc.properties(node)} if not doc.info(node).get('list') and doc.info(node)['type']!='$list' else {},
                    children=[snapshot(doc,c['id']) for c in doc.children(node)])
    a, b = [snapshot(d,d.summary()['root']) for d in docs]
    # Remove only the intended additions/size adjustment, then compare every node.
    found = dict(browser=0, button=0, login=0)
    def strip(node):
        if node['type']=='Window' and node['name']=='BrowserWnd':
            found['browser'] += 1
            p = node['properties']
            for key,value in dict(unk2=1,unk102='BrowserWnd',unk103='GamingState',unk105=1,unk134='Interface.BrowserIcon',unk136=1).items():
                if p[key] != value: raise ValueError('Invalid browser Window property: '+key)
            state = next(c for c in node['children'] if c['name']=='unk147')
            if len(state['children'])!=1 or 'LoginState' not in state['children'][0]['properties'].values():
                raise ValueError('Browser LoginState missing')
            controls = next(c for c in node['children'] if c['name']=='children')['children']
            if {c['name'] for c in controls} != {'btnBack','btnForward','btnReload','btnHome','btnGo','Address','ProbeSurface','BrowserInput','BrowserKeyboard'}:
                raise ValueError('Browser controls differ')
            return None
        if node['type']=='Window' and node['name']=='LoginMenuWnd':
            found['login'] += 1
            if node['properties']['size_absolute_height']!=175: raise ValueError('Login size mismatch')
            node['properties']['size_absolute_height']=149
            controls=next(c for c in node['children'] if c['name']=='children')
            for c in controls['children']:
                if c['name']=='btnBrowser':
                    found['button']+=1
                    if c['properties']['buttonNameText']!='Browser' or c['properties']['anchor_y']!=138.0:
                        raise ValueError('Login browser button mismatch')
            controls['children']=[c for c in controls['children'] if c['name']!='btnBrowser']
        node['children']=[value for c in node['children'] if (value:=strip(c)) is not None]
        return node
    if strip(b)!=a or found!=dict(browser=1,button=1,login=1):
        raise ValueError('Unintended change to existing Gracia XDAT')
    return dict(schema='ct24.XDAT', original_ui_preserved=True, browser_added=True)


def main():
    output=ROOT/'result'; system=output/'system'
    recovery=json.loads((ROOT/'recovery-validation.json').read_text())
    native=json.loads((ROOT/'native-validation.json').read_text(encoding='utf-8-sig'))
    if not recovery['passed'] or recovery['compiled_sha256']!=sha(ROOT/'workspace/System/Interface.u'):
        raise ValueError('Missing/stale recovery verification')
    if native['extension_sha256']!=sha(system/'ExtensionL2.dll') or native['patched_core_sha256']!=sha(system/'Core.dll'):
        raise ValueError('Packaged DLL/Core differs from native tests')
    if native['browser_host_sha256']!=sha(system/'GraciaBrowserHost.exe'):
        raise ValueError('Packaged browser helper differs from native tests')
    if {t['name'] for t in native['tests']} != {'options','vm-manual','vm-patched','texture-layout','frames','ipc-frames','exit'} or any(t['exit_code']!=0 or not t['finished'] for t in native['tests']):
        raise ValueError('Native tests incomplete')
    compiled, packaged=Package(ROOT/'workspace/System/Interface.u'), Package(system/'Interface.u')
    if compiled.data!=packaged.data: raise ValueError('Packaged payload differs')
    ui=verify_xdat()
    names=['Core.dll','ExtensionL2.dll','GraciaBrowserHost.exe','Interface.u','Interface.xdat','WebView2Loader.dll','options.config']
    supported={n:sorted({sha(ROOT/'inputs'/n),sha(system/n)}) for n in ('Core.dll','Interface.u','Interface.xdat')}
    previous=output/'manifest.json'
    if previous.exists():
        history=json.loads(previous.read_text()).get('supported_ui_inputs',{})
        for name in supported: supported[name]=sorted(set(supported[name])|set(history.get(name,[])))
    game_report = ROOT/'game-validation.json'
    game = json.loads(game_report.read_text()) if game_report.exists() else None
    game_verified = bool(game and game.get('passed') and
        set(game.get('files', {})) == set(names)-{'options.config'} and
        all(sha(system/name) == digest for name,digest in game['files'].items()))
    result=dict(profile='gracia_epilogue_0941cac5-wgc-recovered',
        required_client_files={n:sha(ROOT/'inputs'/n) for n in ('Engine.dll','NWindow.dll','D3DDrv.dll')},
        supported_ui_inputs=supported,
        files={n:dict(size=(system/n).stat().st_size,sha256=sha(system/n)) for n in names},
        verification=dict(recovery=recovery,native=native,xdat=ui),
        client_installed=False,browser_in_game_verified=game_verified,
        game_validation=game if game_verified else None)
    previous.write_text(json.dumps(result,indent=2))
    print('PASS Gracia seven-file bundle: hashes, recovery, native/IPC tests and XDAT preservation')


if __name__=='__main__': main()
