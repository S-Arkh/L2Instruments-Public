"""Windows launcher selection without starting the GUI or installing dependencies."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell launcher')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='launcher test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'uExplorer'
        self.app.mkdir()
        for name in ('run.ps1', 'run.cmd', 'launch.py'):
            shutil.copyfile(ROOT / name, self.app / name)
        self.python = self.root / 'interface_editor/.venv/Scripts/python.exe'
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(self.python.parents[1])], check=True)
        package = self.python.parents[1] / 'Lib/site-packages/PySide6'
        package.mkdir()
        (package / '__init__.py').write_text('')
        (package / 'QtCore.py').write_text('def qVersion(): return "test-qt"\n')
        for module in ('QtGui', 'QtWidgets'):
            (package / (module + '.py')).write_text('')

    def run_launcher(self, *args):
        return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(self.app / 'run.ps1'), *args], cwd=self.root, capture_output=True, text=True, timeout=45)

    def test_broken_local_python_falls_back_to_editor_environment(self):
        broken = self.app / '.venv/Scripts/python.exe'
        broken.parent.mkdir(parents=True)
        broken.write_bytes(b'not an executable')
        result = self.run_launcher('-CheckRuntime')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(self.python), result.stdout)
        self.assertIn('test-qt', result.stdout)

    def test_local_environment_is_preferred(self):
        local = self.app / '.venv'
        shutil.copytree(self.python.parents[1], local)
        result = self.run_launcher('-CheckRuntime')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(local / 'Scripts/python.exe'), result.stdout)

    def test_explicit_python_without_qt_does_not_silently_fall_back(self):
        shim = self.root / 'no qt.cmd'
        shim.write_text('@echo off\n"' + sys.executable + '" -S %*\n')
        result = self.run_launcher('-Python', str(shim), '-CheckRuntime')
        self.assertEqual(result.returncode, 1)
        self.assertIn('requirements.txt', result.stdout)
        self.assertNotIn('Traceback', result.stdout + result.stderr)
        self.assertNotIn('test-qt', result.stdout)

    def test_cmd_forwards_arguments_and_exit_status(self):
        result = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/c', 'call',
            str(self.app / 'run.cmd'), '-Python', str(self.python), '-CheckRuntime'],
            cwd=self.root, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('test-qt', result.stdout)
        failed = subprocess.run([os.environ.get('COMSPEC', 'cmd.exe'), '/c', 'call',
            str(self.app / 'run.cmd'), '-Python', 'missing-python-executable', '-CheckRuntime'],
            cwd=self.root, capture_output=True, text=True, timeout=45)
        self.assertEqual(failed.returncode, 1)
        self.assertIn('requirements.txt', failed.stdout)


if __name__ == '__main__':
    unittest.main()
