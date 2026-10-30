import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1] / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class InstallTests(unittest.TestCase):
    def test_backup_upgrade_config_preservation_and_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            system, package = root / 'client', root / 'package'
            system.mkdir(); package.mkdir()
            for name, data in [('Core.dll', b'core'), ('Interface.u', b'old'), ('options.config', b'custom')]:
                (system / name).write_bytes(data)
            for name, data in [('Interface.u', b'new'), ('ExtensionL2.dll', b'dll'), ('options.config', b'default')]:
                (package / name).write_bytes(data)
            profile = dict(profile='fixture', required_client_files={'Core.dll': installer.digest(system/'Core.dll')},
                supported_ui_inputs={'Interface.u': [installer.digest(system/'Interface.u')]},
                files={p.name: dict(sha256=installer.digest(p)) for p in package.iterdir()})
            result = installer.install(system, package, profile, root/'backups', check=True)
            self.assertTrue(result['check_only'])
            self.assertFalse((root/'backups').exists())
            result = installer.install(system, package, profile, root/'backups')
            self.assertEqual((system/'options.config').read_bytes(), b'custom')
            self.assertEqual((system/'Interface.u').read_bytes(), b'new')
            (system/'Interface.u').write_bytes(b'user edit')
            with self.assertRaises(ValueError): installer.restore(Path(result['backup']))
            self.assertTrue((system/'ExtensionL2.dll').exists())
            (system/'Interface.u').write_bytes(b'new')
            installer.restore(Path(result['backup']))
            self.assertEqual((system/'Interface.u').read_bytes(), b'old')
            self.assertFalse((system/'ExtensionL2.dll').exists())
            (system/'Core.dll').write_bytes(b'unknown')
            with self.assertRaises(ValueError): installer.install(system, package, profile, root/'backups')

if __name__ == '__main__': unittest.main()
