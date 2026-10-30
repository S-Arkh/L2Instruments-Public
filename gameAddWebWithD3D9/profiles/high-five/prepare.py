"""Build an independent browser-texture stage from the tested texture probe."""
from pathlib import Path
import importlib.util
import shutil
import sys
import argparse

ROOT = Path(__file__).resolve().parent
PROBE = ROOT.parents[1] / 'prototype'
BASE = ROOT.parents[1] / 'archive/addWeb'

def main(native_only=False):
    spec = importlib.util.spec_from_file_location('prepare_probe', PROBE / 'prepare.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    # Recreate disposable source/compiler staging for the proven probe.
    probe.main(native_only=native_only)
    shutil.copytree(PROBE / 'stage', ROOT / 'stage', dirs_exist_ok=True)
    if not native_only:
        shutil.copytree(PROBE / 'workspace', ROOT / 'workspace', dirs_exist_ok=True)
    for source in (ROOT / 'native').glob('*'):
        shutil.copy2(source, ROOT / 'stage/native' / source.name)
    legacy = ROOT / 'stage/native/browser.cpp'
    text = legacy.read_text()
    start = text.index('std::wstring configUrl() {')
    end = text.index('\nvoid logError(', start)
    text = text[:start] + 'std::wstring configUrl() { return browseroptions::StartPage(moduleDirectory); }\n' + text[end:]
    legacy.write_text(text.replace('#include "browser.h"', '#include "browser.h"\n#include "options.h"'))
    bindings = ROOT / 'stage/native/base/extensionL2.cpp'
    text = bindings.read_text()
    text = text.replace('#include "../texture_probe.h"', '#include "../texture_probe.h"\n#include "../web_frames.h"')
    text = text.replace('#include "../web_frames.h"', '#include "../web_frames.h"\n#include "../game_input.h"')
    marker = 'L2_NATIVE(4017, TextureProbeStatus, &textureprobe::Status),'
    assert text.count(marker) == 1
    text = text.replace(marker, marker + '''
        L2_NATIVE(4018, TextureWebOpen, &webframes::Open),
        L2_NATIVE(4019, TextureWebHide, &webframes::Hide),
        L2_NATIVE(4020, TextureWebNavigate, &webframes::Navigate),
        L2_NATIVE(4021, TextureWebCommand, &webframes::Command),
        L2_NATIVE(4022, TextureWebStatus, &webframes::Status),
        L2_NATIVE(4023, TextureWebMouse, &gameinput::Mouse),
        L2_NATIVE(4024, TextureWebKey, &gameinput::Key),
        L2_NATIVE(4025, TextureWebFocus, &webframes::Focus),
        L2_NATIVE(4026, TextureWebText, &webframes::Text),
        L2_NATIVE(4027, TextureWebPoll, &gameinput::Poll),
        L2_NATIVE(4028, TextureWebLeftPressed, &gameinput::LeftPressed),
        L2_NATIVE(4029, TextureWebResume, &webframes::Resume),
        L2_NATIVE(4030, TextureWebClose, &webframes::Close),''')
    bindings.write_text(text)
    runtime = ROOT / 'stage/native/base/extension_runtime.cpp'
    runtime_text = runtime.read_text()
    marker = 'BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) {'
    assert runtime_text.count(marker) == 1
    runtime_text = '#include "../web_frames.h"\n' + runtime_text.replace(marker,
        'BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID reserved) {\n'
        '    if (reason == DLL_PROCESS_DETACH && reserved) webframes::AbandonOnProcessExit();')
    runtime.write_text(runtime_text)
    # Reuse actual Core VM tests with the enlarged native table.
    vm = ROOT / 'stage/probe.cpp'
    vm.write_text(vm.read_text().replace('count() != 18', 'count() != 31'))
    if native_only:
        print('HF native sources prepared; client inputs not required')
        return
    for source in (ROOT / 'Classes').glob('*.uc'):
        shutil.copy2(source, ROOT / 'workspace/Interface/Classes' / source.name)
    textures = ROOT / 'workspace/Interface/Textures'
    textures.mkdir(exist_ok=True)
    icon_spec = importlib.util.spec_from_file_location('browser_icon', ROOT / 'icon_asset.py')
    icon = importlib.util.module_from_spec(icon_spec)
    icon_spec.loader.exec_module(icon)
    shutil.copy2(icon.write_assets(), textures / 'BrowserIcon.tga')
    for path in (ROOT / 'workspace/System').iterdir():
        if path.name.lower() == 'interface.u': path.unlink()
    sys.path.insert(0, str(ROOT.parents[2] / 'interface_editor/app'))
    from _interface_core import Document
    schema = (ROOT.parents[2] / 'interface_editor/schemas/schemas.json').read_text(encoding='utf-8')
    doc = Document(schema)
    doc.load(str(BASE / 'result/system/Interface.xdat'), 'ct26.XDAT')
    def find(name, kind):
        return next(i for i in doc.search(name)['matches']
                    if doc.info(i)['name'] == name and doc.info(i)['type'] == kind)
    browser = find('BrowserWnd', 'Window')
    login = find('LoginMenuWnd', 'Window')
    # Stock HF background names verified against Interface_high_five.xdat.
    doc.set_many(login, dict(backTex='L2UI_CT1.Windows.Windows_DF_Drawer_Bg'))
    doc.set_many(find('OptionWnd', 'Window'), dict(backTex='L2UI_CT1.Windows.Windows_DF_Large_Bg'))
    option_children = next(c['id'] for c in doc.children(find('OptionWnd', 'Window')) if c['name'] == 'children')
    option_background = next(c['id'] for c in doc.children(option_children) if c['name'] == 'backgroundtex')
    doc.set_many(option_background, dict(file='L2UI_CT1.tab.Tab_DF_bg_line'))
    login_children = next(c['id'] for c in doc.children(login) if c['name'] == 'children')
    button = next(c['id'] for c in doc.children(login_children) if doc.info(c['id'])['name'] == 'btnTestExt')
    doc.set_many(button, dict(name='btnBrowser', buttonName=-1, buttonNameText='Browser'))
    login_script = ROOT / 'workspace/Interface/Classes/LoginMenuWnd.uc'
    script = login_script.read_bytes()
    assert script.count(b'case "btnTestExt"') == 1
    login_script.write_bytes(script.replace(b'case "btnTestExt"', b'case "btnBrowser"'))
    doc.set_many(browser, dict(alwaysOnTop=0, alwaysOnBack=0, hookKeyInput=1, draggable=0,
        iconable=1, iconName='Interface.BrowserIcon', tooltipIdx=-1,
        size_absolute_width=540, size_absolute_height=592))
    children = next(c['id'] for c in doc.children(browser) if c['name'] == 'children')
    controls = {doc.info(c['id'])['name']: c['id'] for c in doc.children(children)}
    for name, x, width in [('btnBack', 10, 36), ('btnForward', 48, 36),
                           ('btnReload', 86, 64), ('btnHome', 152, 60), ('btnGo', 484, 46)]:
        doc.set_many(controls[name], dict(anchor_x=float(x), size_absolute_width=width))
    doc.set_many(controls['Address'], dict(anchor_x=220.0, size_absolute_width=256))
    surface = doc.duplicate(find('texPledgeCrest', 'Texture'), children)
    doc.set_many(surface, dict(name='ProbeSurface', parentName='BrowserWnd',
        alwaysOnTop=0, alwaysOnBack=0, virtual=0, anchored=1, relativePoint=1, anchorPoint=1,
        relativeTo='', anchor_x=14.0, anchor_y=66.0, size_absolute_width=512,
        size_absolute_height=512, type=0, layer=1, u=0.0, v=0.0,
        uSize=512.0, vSize=512.0, alpha=255, isAnimTex=0, colorModify=0xffffffff))
    # Texture receives hover but HF lets its button presses start window drag.
    # A regular button above it participates in the native input routing.
    input_surface = doc.duplicate(controls['btnGo'], children)
    doc.set_many(input_surface, dict(name='BrowserInput', parentName='BrowserWnd',
        alwaysOnTop=0, alwaysOnBack=0, virtual=0, anchored=1,
        relativePoint=1, anchorPoint=1, relativeTo='', anchor_x=14.0, anchor_y=66.0,
        size_absolute_width=512, size_absolute_height=512,
        normalTex='undefined', pushedTex='undefined', highlightTex='undefined',
        dropTex='undefined', buttonName=-1, buttonNameText='', noHighlight=1,
        defaultSoundOn=0))
    keyboard = doc.duplicate(controls['Address'], children)
    doc.set_many(keyboard, dict(name='BrowserKeyboard', parentName='BrowserWnd',
        anchor_x=14.0, anchor_y=62.0, size_absolute_width=2, size_absolute_height=2,
        virtual=0))
    output = ROOT / 'result/system'
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'options.config', output / 'options.config')
    data = doc.serialize()
    (output / 'Interface.xdat').write_bytes(data)
    check = Document(schema)
    check.load(str(output / 'Interface.xdat'), 'ct26.XDAT')
    assert data == check.serialize()
    print('Browser texture stage prepared; XDAT roundtrip passed')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only', action='store_true')
    main(parser.parse_args().native_only)
