"""GPU test fixtures must not replace a selected bundle's application imports."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class GPUImportIsolation(unittest.TestCase):
    def test_fixtures_keep_selected_application_path(self):
        explorer=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='uex-gpu-imports-') as temp:
            bundle=Path(temp)/'bundle'
            target=bundle/'python'
            target.mkdir(parents=True)
            for source in (explorer/'python').glob('*.py'):
                shutil.copy2(source,target/source.name)
            script=explorer/'tests/material_gpu_smoke.py'
            probe="""
import importlib, pathlib, runpy, sys
script, bundle = sys.argv[1:]
sys.argv = [script, bundle]
runpy.run_path(script, run_name='import_probe')
target = (pathlib.Path(bundle)/'python').resolve()
source = (pathlib.Path(script).resolve().parents[1]/'python').resolve()
for name in ('material_uv','material_rotation','material_rotation3d',
             'material_oscillation','material_coordinates','material_chain','material_surface',
             'material_snapshot','material_multisample','material_frames'):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().parent == target, name
assert not any(path and pathlib.Path(path).resolve() == source for path in sys.path)
"""
            subprocess.run([sys.executable,'-I','-B','-c',probe,str(script),str(bundle)],
                           check=True,timeout=60)


if __name__=='__main__':unittest.main()
