"""Build the XDAT and stage UC sources; never modifies the installed client."""
from pathlib import Path
import shutil
import sys
import json

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2] / 'interface_editor/app'))
from _interface_core import Document

def main():
    schema = (ROOT.parents[2] / 'interface_editor/schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(schema)
    doc.load(str(ROOT / 'inputs/Interface.xdat'), 'ct26.XDAT')
    def find(name, kind):
        return next(i for i in doc.search(name)['matches'] if doc.info(i)['name'] == name and doc.info(i)['type'] == kind)
    def children(node):
        return next(c['id'] for c in doc.children(node) if c['name'] == 'children')
    status = find('DetailStatusWnd', 'Window')
    template = find('btnCredit', 'Button')
    button = doc.duplicate(template, children(status))
    doc.set_many(button, dict(name='btnBrowser', parentName='DetailStatusWnd', buttonName=-1,
        buttonNameText='Browser', anchor_x=97.0, anchor_y=516.0, size_absolute_width=98, size_absolute_height=27))
    doc.set(status, 'size_absolute_height', 550)
    # GM layout inherits DetailStatusWnd; explicitly retain its previous height.
    browser = doc.duplicate(find('CalculatorWnd', 'Window'))
    for node in list(doc.children(children(browser))):
        doc.remove(node['id'])
    doc.set_many(browser, dict(name='BrowserWnd', script='BrowserWnd', state='GamingState',
        size_absolute_width=900, size_absolute_height=606, title=-1, alwaysOnTop=1,
        draggable=1, savePosition=1, anchor_x=0.0, anchor_y=0.0))
    states = next(c['id'] for c in doc.children(browser) if c['name'] == 'additionalState')
    state = doc.add(states, 'ct26.Window.State')
    doc.set(state, 'unk148', 'LoginState')
    content = children(browser)
    for name, text, x, width in [('btnBack', '<', 10, 36), ('btnForward', '>', 48, 36),
        ('btnReload', 'Reload', 86, 64), ('btnHome', 'Home', 152, 60), ('btnGo', 'Go', 834, 56)]:
        node = doc.duplicate(template, content)
        doc.set_many(node, dict(name=name, parentName='BrowserWnd', anchor_x=float(x), anchor_y=34.0,
            buttonName=-1, buttonNameText=text, size_absolute_width=width, size_absolute_height=27))
    edit = doc.duplicate(find('PetitionChatEditBox', 'EditBox'), content)
    doc.set_many(edit, dict(name='Address', parentName='BrowserWnd', anchor_x=220.0, anchor_y=39.0,
        anchored=1, relativePoint=1, anchorPoint=1, relativeTo='', type=0, maxLength=2048,
        size_absolute_width=604, size_absolute_height=20, useFont=0))
    output = ROOT / 'result/system/Interface.xdat'
    output.write_bytes(doc.serialize())
    check = Document(schema)
    check.load(str(output), 'ct26.XDAT')
    assert check.serialize() == output.read_bytes()
    classes = ROOT / 'workspace/Interface/Classes'
    # Recover the baseline each time, preserving custom client sources.
    sys.path.insert(0, str(ROOT.parents[1] / 'tools/ue2'))
    from extract_sources import extract
    from uc_declarations import normalize_file
    extract(ROOT / 'inputs/interface.u', classes)
    for p in classes.glob('*.uc'):
        normalize_file(p)
    statusfile = classes / 'DetailStatusWnd.uc'
    data = statusfile.read_bytes()
    assert b'function OnClickButton' not in data
    data += b'\nfunction OnClickButton(string strID)\n{\n    if (strID == "btnBrowser")\n        ShowWindowWithFocus("BrowserWnd");\n}\n'
    statusfile.write_bytes(data)
    loginfile = classes / 'LoginMenuWnd.uc'
    data = loginfile.read_bytes()
    assert b'case "btnTestExt"' not in data
    old = b'case "btnNewAccount"'
    assert data.count(old) == 1
    data = data.replace(old, b'case "btnTestExt":\n        ShowWindowWithFocus("BrowserWnd");\n        break;\n    ' + old)
    loginfile.write_bytes(data)
    for name in ('AddWebAPI.uc', 'BrowserWnd.uc'):
        shutil.copy2(ROOT / 'src/Classes' / name, classes / name)
    for p in (ROOT / 'workspace/System').iterdir():
        if p.name.lower() == 'interface.u': p.unlink()
    (ROOT / 'ui-validation.json').write_text(json.dumps({'xdat_roundtrip': True,
        'login_button': 'LoginMenuWnd.btnTestExt', 'status_button': 'DetailStatusWnd.btnBrowser',
        'browser_states': ['GamingState', 'LoginState'], 'browser_size': [900, 606]}, indent=2))
    print('XDAT roundtrip passed; browser and both button handlers staged')

if __name__ == '__main__':
    main()
