"""Stage the texture probe from addWeb; never writes into a client directory."""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'archive/addWeb'

def main(native_only=False):
    stage = ROOT / 'stage'
    stage.mkdir(exist_ok=True)
    shutil.copytree(BASE / 'native', stage / 'native', dirs_exist_ok=True)
    for path in (ROOT / 'native').glob('*'):
        shutil.copy2(path, stage / 'native' / path.name)
    api = stage / 'native/base/extension_api.h'
    text = api.read_text()
    old = 'Float, Int64, String };'
    assert text.count(old) == 1
    api.write_text(text.replace(old, 'Float, Int64, String, Object };'))
    bindings = stage / 'native/base/extensionL2.cpp'
    text = bindings.read_text()
    text = text.replace('#include "../browser.h"', '#include "../browser.h"\n#include "../texture_probe.h"')
    marker = 'L2_NATIVE(4015, WebStatus,       &addweb::Status),'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '\n        L2_NATIVE(4016, TextureProbeFrame, &textureprobe::Frame),\n        L2_NATIVE(4017, TextureProbeStatus, &textureprobe::Status),')
    bindings.write_text(text)
    probe = (BASE / 'tests/extension_probe.cpp').read_text()
    marker = '    // VM tests are finished; no UObject/UFunction cache remains in this host.'
    assert probe.count(marker) == 1
    probe = probe.replace(marker, '''    if (count() != 18 || bindings[16].index != 4016 ||
        bindings[16].arguments[0] != l2ext::Type::Object ||
        bindings[16].arguments[1] != l2ext::Type::Int ||
        bindings[16].result != l2ext::Type::Bool) return 30;
    scalar.clear(); callOpcode(scalar, 4016);
    scalar.push_back(0x2a); // EX_NoObject
    integer(scalar, 7); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, 0, "TextureProbeFrame None object via Core VM")) return 31;
    scalar.clear(); callOpcode(scalar, 4017); scalar.push_back(0x16);
    if (!evaluateScalar(step, scalar, static_cast<std::uint32_t>(-4), "TextureProbeStatus null rejection")) return 32;
''' + marker)
    (stage / 'probe.cpp').write_text(probe)

    if native_only:
        return

    workspace = ROOT / 'workspace'
    shutil.copytree(BASE / 'workspace', workspace, dirs_exist_ok=True)
    for path in (ROOT / 'Classes').glob('*.uc'):
        shutil.copy2(path, workspace / 'Interface/Classes' / path.name)
    for path in (workspace / 'System').iterdir():
        if path.name.lower() == 'interface.u':
            path.unlink()  # disposable compiler output copied from addWeb

    sys.path.insert(0, str(ROOT.parents[1] / 'interface_editor/app'))
    from _interface_core import Document
    schema = (ROOT.parents[1] / 'interface_editor/schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(schema)
    doc.load(str(BASE / 'result/system/Interface.xdat'), 'ct26.XDAT')
    def find(name, kind):
        return next(i for i in doc.search(name)['matches']
                    if doc.info(i)['name'] == name and doc.info(i)['type'] == kind)
    browser = find('BrowserWnd', 'Window')
    children = next(c['id'] for c in doc.children(browser) if c['name'] == 'children')
    for child in list(doc.children(children)):
        doc.remove(child['id'])
    doc.set_many(browser, dict(alwaysOnTop=0, alwaysOnBack=0,
        size_absolute_width=540, size_absolute_height=566))
    surface = doc.duplicate(find('texPledgeCrest', 'Texture'), children)
    doc.set_many(surface, dict(name='ProbeSurface', parentName='BrowserWnd',
        alwaysOnTop=0, alwaysOnBack=0, anchored=1, relativePoint=1, anchorPoint=1,
        relativeTo='', anchor_x=14.0, anchor_y=34.0, size_absolute_width=512,
        size_absolute_height=512, type=0, layer=1, u=0.0, v=0.0,
        uSize=256.0, vSize=256.0, alpha=255, isAnimTex=0, colorModify=0xffffffff))
    output = ROOT / 'result/system'
    output.mkdir(parents=True, exist_ok=True)
    data = doc.serialize()
    (output / 'Interface.xdat').write_bytes(data)
    check = Document(schema)
    check.load(str(output / 'Interface.xdat'), 'ct26.XDAT')
    assert check.serialize() == data
    (ROOT / 'preparation.json').write_text(json.dumps(dict(xdat_roundtrip=True,
        window='BrowserWnd', texture='BrowserWnd.ProbeSurface', always_on_top=False,
        native_indices=[4016, 4017], client_installed=False), indent=2))
    print('Texture probe UI/native sources staged; XDAT roundtrip passed')

if __name__ == '__main__':
    main()
