"""Exercise installation/rollback on isolated copies, never the actual client."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    profile=json.loads((ROOT/'result/manifest.json').read_text())
    temp_root=Path('/tmp/opencode') if sys.platform!='win32' else ROOT/'tests'
    with tempfile.TemporaryDirectory(prefix='gracia-install-',dir=temp_root) as temp:
        temp=Path(temp);system=temp/'system';system.mkdir()
        for name in ('Core.dll','Engine.dll','NWindow.dll','D3DDrv.dll','Interface.u','Interface.xdat'):
            shutil.copy2(ROOT/'inputs'/name,system/name)
        config=system/'options.config';config.write_text('{"browser":{"startPage":"https://example.org/"}}')
        before={p.name:digest(p) for p in system.iterdir()}
        package=ROOT/'result/system'
        checked=install.install(system,package,profile,temp/'backups',True)
        assert checked['check_only'] and not (temp/'backups').exists()
        assert before=={p.name:digest(p) for p in system.iterdir()}
        result=install.install(system,package,profile,temp/'backups')
        assert digest(config)==before['options.config']
        assert digest(system/'Core.dll')==profile['files']['Core.dll']['sha256']
        assert digest(system/'Interface.u')==profile['files']['Interface.u']['sha256']
        install.restore(Path(result['backup']))
        assert before=={p.name:digest(p) for p in system.iterdir()}
        # Unknown UI must be rejected before any replacement/backup is made.
        (system/'Interface.xdat').write_bytes(b'unknown client')
        try:install.install(system,package,profile,temp/'rejected')
        except ValueError:pass
        else:raise AssertionError('Unknown UI was accepted')
        assert not (temp/'rejected').exists() and digest(system/'Core.dll')==before['Core.dll']
    print('PASS --check is read-only; manifest install; Core/UI install; config preservation; exact rollback; unknown-UI rejection')

if __name__=='__main__':main()
