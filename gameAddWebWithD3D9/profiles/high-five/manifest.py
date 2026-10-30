"""Generate the install profile and hashes for the current build."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1] / 'archive/addWeb'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    inventory = json.loads((ROOT.parents[1] / 'reports/inventory.json').read_text())
    names = ['ExtensionL2.dll', 'Interface.u', 'Interface.xdat', 'WebView2Loader.dll', 'options.config']
    files = {n: dict(size=(ROOT/'result/system'/n).stat().st_size, sha256=sha(ROOT/'result/system'/n)) for n in names}
    supported = {}
    previous = ROOT/'result/manifest.json'
    history = json.loads(previous.read_text()).get('supported_ui_inputs', {}) if previous.exists() else {}
    for name in ['Interface.u', 'Interface.xdat']:
        candidates = [BASE/'result/system'/name, ROOT.parents[1]/'prototype/result/system'/name, ROOT/'result/system'/name]
        supported[name] = sorted({sha(p) for p in candidates if p.exists()} | set(history.get(name, [])))
    result = dict(profile='hf5-revision-268-en-wgc-experimental', files=files,
        required_client_files={'Core.dll': sha(BASE/'inputs/Core.dll'),
            'Engine.dll': inventory['hf/engine.dll']['sha256'],
            'NWindow.dll': inventory['hf/nwindow.dll']['sha256']},
        supported_ui_inputs=supported, client_installed=False, browser_in_game_verified=False)
    (ROOT/'result/manifest.json').write_text(json.dumps(result, indent=2))
    print('HF install profile and five package hashes saved')

if __name__ == '__main__': main()
