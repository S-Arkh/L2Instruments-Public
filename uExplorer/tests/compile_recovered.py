"""Export Gracia into an isolated compiler workspace; never touch installed files."""
from pathlib import Path
import shutil
import subprocess
import sys
import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'python')]
from backend import Core, export_classes

def main():
    base=ROOT.parent
    package=base/'gameAddWebWithD3D9/profiles/gracia/inputs/Interface.u'
    core=Core();classes=core.request(operation='inspect',path=str(package))['package']['classes']
    workspace=ROOT/'tests'/('compile-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    export_classes(core,package,classes,workspace)
    source=base/'gameAddWebWithD3D9/profiles/gracia/workspace'
    for name in ('Core','nwindow','System'):
        shutil.copytree(source/name,workspace/name)
    (workspace/'System/Interface.u').unlink()
    # The historical compiler reads ANSI input; reproduce byte values emitted
    # by the reference parser's Latin-1 representation for this known fixture.
    for path in (workspace/'Interface/Classes').glob('*.uc'):
        path.write_bytes(path.read_text(encoding='utf-8').encode('latin1'))
    result=subprocess.run([sys.executable,'-B',str(base/'gameAddWebWithD3D9/tools/ue2/run_compile.py'),str(workspace/'System'),
                           '--launcher',str(base/'gameAddWebWithD3D9/toolchain/ucc64.exe')])
    print('WORKSPACE',workspace)
    return result.returncode
if __name__=='__main__':raise SystemExit(main())
