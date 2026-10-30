"""Prepare Gracia sources and ABI adapter without modifying the client or HF output."""
from pathlib import Path
import importlib.util
import hashlib
import json
import shutil
import sys
import argparse
import re

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from webview_lifetime import adapt as adapt_webview_lifetime
REBUILD = ROOT.parents[2]
BASE = ROOT.parents[1] / 'archive/addWeb'
SHARED = ROOT.parent / 'high-five'
sys.path.insert(0, str(ROOT.parents[1]/'tools/ue2'))
from extract_sources import extract, script_text
from uc_declarations import normalize_file
from compilation_sdk import object_with_runtime_storage
from sdk_enums import augment
from ue2package import Package

def main(native_only=False, classes=None, sources_only=False):
    spec = importlib.util.spec_from_file_location('browser_profiles', ROOT.parents[1]/'tools/client_profiles.py')
    profiles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profiles)
    profile_name = 'gracia_epilogue_0941cac5'
    if not native_only:
        checked = profiles.verify(profile_name, ROOT/'inputs')
        (ROOT/'profile-check.json').write_text(json.dumps(checked, indent=2))
    stage = ROOT/'stage'
    shutil.copytree(SHARED/'native',ROOT/'native',dirs_exist_ok=True)
    (ROOT/'tests').mkdir(exist_ok=True)
    for source in (SHARED/'tests').iterdir():
        if source.is_file() and source.suffix in ['.cpp','.py','.ps1']: shutil.copy2(source,ROOT/'tests'/source.name)
    # Common extension headers/VM probe include the verified UObject bridge.
    if not (SHARED/'stage/native/base/extension_api.h').exists():
        raise RuntimeError('Prepare/build profiles/high-five once to generate the common native bridge')
    shutil.copytree(SHARED/'stage', stage, dirs_exist_ok=True)
    for source in (SHARED/'native').glob('*'):
        shutil.copy2(source, stage/'native'/source.name)
    web_frames = adapt_webview_lifetime((SHARED/'native/web_frames.cpp').read_text())
    (ROOT/'native/web_frames.cpp').write_text(web_frames)
    (stage/'native/web_frames.cpp').write_text(web_frames)
    for name in ['extension_runtime.cpp', 'client_profile.h']:
        shutil.copy2(REBUILD/'dll/src'/name, stage/'native/base'/name)
    runtime = stage/'native/base/extension_runtime.cpp'
    text = runtime.read_text()
    text = '#include "../web_frames.h"\n'+text.replace('BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) {',
        'BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID reserved) {\n'
        '    if (reason == DLL_PROCESS_DETACH && reserved) webframes::AbandonOnProcessExit();')
    runtime.write_text(text)
    probe = stage/'probe.cpp'
    text = probe.read_text()
    marker = 'auto assign = reinterpret_cast<l2client::StringAssign>(GetProcAddress(core, "??4FString@@QAEAAV0@PB_W@Z"));'
    if marker in text:
        text = text.replace(marker, marker+'\n    if (!assign) assign = reinterpret_cast<l2client::StringAssign>(GetProcAddress(core, "??4FString@@QAEAAV0@PBG@Z"));')
    probe.write_text(text)
    (stage/'native/texture_probe.cpp').write_text(profiles.adapter(profile_name))
    if native_only:
        print('Gracia native sources prepared; UI/package not built')
        return

    workspace=ROOT/'workspace';system=workspace/'System'
    (workspace/'nwindow/Inc').mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE/'workspace/System',system,dirs_exist_ok=True)
    for p in system.iterdir():
        if p.name.lower() in ['core.u','nwindow.u','interface.u']: p.unlink()
    shutil.copytree(BASE/'workspace/Core',workspace/'Core',dirs_exist_ok=True)
    report={}
    for name,folder in [('Interface','Interface'),('NWindow','nwindow')]:
        destination=workspace/folder/'Classes'
        if destination.exists(): shutil.rmtree(destination) # generated compiler sources only
        if name == 'Interface' and classes:
            shutil.copytree(classes, destination)
            report[name] = dict(recovered_sources=str(classes), files=len(list(destination.glob('*.uc'))))
        else:
            report[name]=extract(ROOT/'inputs'/f'{name}.u',destination)
            if report[name]['missing'] or report[name]['rejected']: raise RuntimeError(f'Incomplete {name} sources')
    runtime_sdk=REBUILD/'int64/sdk/runtime2226/System'
    client_core=Package(ROOT/'inputs/Core.u');runtime_core=Package(runtime_sdk/'Core.u')
    _,c=client_core.find('Object.ScriptText');_,r=runtime_core.find('Object.ScriptText')
    text=object_with_runtime_storage(script_text(client_core,c)[1],script_text(runtime_core,r)[1])
    (workspace/'Core/Classes/Object.uc').write_bytes(text.encode('latin1'))
    augment(runtime_sdk/'Engine.u',ROOT/'inputs/Engine.u',system/'Engine.u',['Actor.EL2ObjectType','Interactions.EInputKey'])
    for source in (SHARED/'Classes').glob('*.uc'): shutil.copy2(source,workspace/'Interface/Classes'/source.name)
    for source in (ROOT/'Classes').glob('*.uc'): shutil.copy2(source,workspace/'Interface/Classes'/source.name)
    for name in ['AddWebAPI.uc','TextureProbeAPI.uc']:
        shutil.copy2(SHARED/'workspace/Interface/Classes'/name,workspace/'Interface/Classes'/name)
    spec=importlib.util.spec_from_file_location('browser_icon',SHARED/'icon_asset.py')
    icon=importlib.util.module_from_spec(spec);spec.loader.exec_module(icon)
    (workspace/'Interface/Textures').mkdir(exist_ok=True)
    shutil.copy2(icon.write_assets(),workspace/'Interface/Textures/BrowserIcon.tga')
    login=workspace/'Interface/Classes/LoginMenuWnd.uc'
    text=login.read_bytes()
    # Insert after local declarations, before executable code. The recovered
    # function may use a dispatcher, so adding an inner switch case is unsafe.
    function = re.search(rb'function\s+OnClickButton\s*\(string\s+strID\)\s*\{', text)
    if not function: raise RuntimeError('Login button handler not found')
    brace = function.end()
    locals_end = re.match(rb'(?:\s*local\s+[^;]+;)*', text[brace:]).end()
    brace += locals_end
    text=text[:brace]+b'\n if (strID == "btnBrowser") { GetWindowHandle("BrowserWnd").ShowWindow(); return; }\n'+text[brace:]
    login.write_bytes(text)
    for source in workspace.glob('*/Classes/*.uc'):
        if source.parent.parent.name == 'Interface':
            text = source.read_bytes().decode('latin1')
            text = re.sub(r'(?<![\w.])EL2ObjectType\b', 'Actor.EL2ObjectType', text)
            source.write_bytes(text.encode('latin1'))
        normalize_file(source)
    (system/'UE2Runtime.ini').write_text('[Engine.Engine]\nEditorEngine=Editor.EditorEngine\n\n[Core.System]\nPaths=../System/*.u\n\n[Editor.EditorEngine]\nCacheSizeMegs=256\nEditPackages=Core\nEditPackages=Engine\nEditPackages=NWindow\nEditPackages=Interface\n')
    (ROOT/'source-preparation.json').write_text(json.dumps(report,indent=2))
    if not sources_only:
        prepare_xdat()

def prepare_xdat():
    sys.path.insert(0,str(REBUILD/'interface_editor/app'))
    from _interface_core import Document
    schema=(REBUILD/'interface_editor/schemas/schemas.json').read_text()
    d=Document(schema);d.load(str(ROOT/'inputs/Interface.xdat'),'ct24.XDAT')
    hf=Document(schema);hf.load(str(SHARED/'result/system/Interface.xdat'),'ct26.XDAT')
    def find(doc,name,kind):
        return next(i for i in doc.search(name)['matches'] if doc.info(i)['name']==name and doc.info(i)['type']==kind)
    def children(doc,i):return next(c['id'] for c in doc.children(i) if c['name']=='children')
    # ct24 has legacy field names. The optional HF scrollbar-height field is absent.
    aliases=dict(extendsName='superName',alwaysOnTop='unk2',alwaysOnBack='unk3',parentName='unk4',
        preOrder='unk5',postOrder='unk6',anchored='unk7',superChild='unk8',usePosition='anchor',
        relativePoint='anchor_parent',anchorPoint='anchor_this',relativeTo='anchor_ctrl',virtual='unk23',
        tooltipType='popupType',tooltipText='popupValue',tooltipAppearanceTime='unk27',scrollBarOffsetX='unk28',scrollBarOffsetY='unk29')
    window_fields=['parent','backTex','script','state','frame','iconable','stuckable','hidden','alwaysFullAlpha',
        'savePosition','saveSize','title','resizeFrame','frameSize','frameDirection','exitbutton','draggable',
        'resizeFrameDirection','resizeFrameX','resizeFrameY','resizeFrameWidth','resizeFrameHeight','resizeMaxIncrease',
        'drawerDirection','notUsed01','notUsed02','notUsed03','ownerWindow','showAnimType','hideAnimType',
        'notUsed11','notUsed12','notUsed13','notUsed14','iconName','tooltipIdx','hookKeyInput','workingConfiguration',
        'leftTextureName','midTextureName','rightTextureName','minimizeBtnTextureNormal','minimizeBtnTexturePushed',
        'closeBtnTextureNormal','closeBtnTexturePushed','leftBackTextureWidth','midBackTextureWidth']
    walias={name:'unk'+str(100+i) for i,name in enumerate(window_fields)}
    walias['useParentClipRect']='unk149'
    def transfer(src,dst,window=False):
        allowed={p['name'] for p in d.properties(dst)};values={}
        for prop in hf.properties(src):
            name=walias.get(prop['name'],prop['name']) if window else prop['name']
            name=aliases.get(name,name)
            if name in allowed: values[name]=prop['value']
        d.set_many(dst,values)
    macro=find(d,'MacroListWnd','Window')
    browser=d.duplicate(macro)
    transfer(find(hf,'BrowserWnd','Window'),browser,True)
    # Login's native dialog is above normal UI windows in this client.
    d.set_many(browser, {'unk2': 1})  # ct24 alwaysOnTop
    bc=children(d,browser)
    for child in list(d.children(bc)):d.remove(child['id'])
    # Reuse Gracia controls, then copy supported common properties from the HF browser layout.
    def first_kind(kind):
        def walk(i):
            if d.info(i)['type']==kind:return i
            for c in d.children(i):
                value=walk(c['id'])
                if value is not None:return value
        return walk(d.summary()['root'])
    templates={kind:first_kind(kind) for kind in ['Button','EditBox','Texture']}
    for child in hf.children(children(hf,find(hf,'BrowserWnd','Window'))):
        kind=child['type'];target=d.duplicate(templates[kind],bc);transfer(child['id'],target)
    # Add LoginState alongside the primary GamingState using the existing ct24 state entry.
    state_list=next(c['id'] for c in d.children(browser) if c['name']=='unk147')
    types=d.allowed_types(state_list)
    print('Additional-state types:',types)
    login=find(d,'LoginMenuWnd','Window');lc=children(d,login)
    button=d.duplicate(next(c['id'] for c in d.children(lc) if c['name']=='btnReplay'),lc)
    d.set_many(button,dict(name='btnBrowser',buttonName=-1,buttonNameText='Browser',anchor_y=138.0))
    d.set_many(login,dict(size_absolute_height=175))
    # State entry creation is schema-specific; preserve serialized type and set its only name value.
    entry=d.add(state_list,types[0])
    props=d.properties(entry)
    d.set_many(entry,{props[0]['name']:'LoginState'})
    out=ROOT/'result/system';out.mkdir(parents=True,exist_ok=True)
    data=d.serialize();(out/'Interface.xdat').write_bytes(data)
    check=Document(schema);check.load(str(out/'Interface.xdat'),'ct24.XDAT');assert check.serialize()==data
    shutil.copy2(SHARED/'options.config',out/'options.config')
    sys.path.insert(0, str(REBUILD/'dll/tools'))
    from patch_core import patch_core
    patched = out/'Core.dll'
    if not patched.exists():
        patch_core(ROOT/'inputs/Core.dll', patched)
    print('Gracia sources/native profile/XDAT prepared')

if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--classes', type=Path)
    parser.add_argument('--sources-only', action='store_true')
    args = parser.parse_args()
    main(args.native_only, args.classes, args.sources_only)
