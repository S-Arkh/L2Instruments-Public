"""Transactional checks with isolated miniature texture bundles."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install as tool


class Installation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.client, self.bundle, self.backup = [root / n for n in ('client', 'bundle', 'backup')]
        files = []
        for n in ('A.utx', 'B.utx'):
            for folder, content in ((self.client, b'original'), (self.bundle, b'pink')):
                (folder / 'SysTextures').mkdir(parents=True, exist_ok=True)
                (folder / 'SysTextures' / n).write_bytes(content + n.encode())
            files.append({'path': 'SysTextures/' + n,
                          'original_sha256': tool.sha(self.client / 'SysTextures' / n),
                          'sha256': tool.sha(self.bundle / 'SysTextures' / n)})
        (self.bundle / 'manifest.json').write_text(json.dumps({'profile': 'test', 'revision': 'v1', 'files': files}))

    def test_check_install_rollback(self):
        tool.install(self.client, self.bundle, self.backup, check=True)
        self.assertFalse(self.backup.exists())
        tool.install(self.client, self.bundle, self.backup)
        self.assertEqual((self.client / 'SysTextures/A.utx').read_bytes(), b'pinkA.utx')
        tool.rollback(self.backup)
        self.assertEqual((self.client / 'SysTextures/A.utx').read_bytes(), b'originalA.utx')
        tool.rollback(self.backup)

    def test_unknown_client_rejected(self):
        (self.client / 'SysTextures/B.utx').write_bytes(b'user-work')
        with self.assertRaises(ValueError):
            tool.install(self.client, self.bundle, self.backup)
        self.assertFalse(self.backup.exists())
        self.assertEqual((self.client / 'SysTextures/A.utx').read_bytes(), b'originalA.utx')

    def test_mid_install_failure_restores(self):
        real_copy = tool.atomic_copy
        def copy(src, dst):
            if src == self.bundle / 'SysTextures/B.utx':
                raise OSError('simulated write failure')
            real_copy(src, dst)
        with patch.object(tool, 'atomic_copy', copy), self.assertRaises(OSError):
            tool.install(self.client, self.bundle, self.backup)
        self.assertEqual((self.client / 'SysTextures/A.utx').read_bytes(), b'originalA.utx')

    def test_rollback_preserves_later_changes(self):
        tool.install(self.client, self.bundle, self.backup)
        (self.client / 'SysTextures/B.utx').write_bytes(b'later-user-work')
        with self.assertRaises(ValueError):
            tool.rollback(self.backup)
        self.assertEqual((self.client / 'SysTextures/A.utx').read_bytes(), b'pinkA.utx')

    def test_multiple_inputs_journal_pins_actual_version(self):
        path = self.bundle / 'manifest.json'
        manifest = json.loads(path.read_text())
        for f in manifest['files']:
            f['accepted_input_sha256'] = [f['original_sha256'], 'another-supported-hash']
            f['original_sha256'] = 'another-supported-hash'
        path.write_text(json.dumps(manifest))
        tool.install(self.client, self.bundle, self.backup)
        journal = json.loads((self.backup / 'journal.json').read_text())
        self.assertNotEqual(journal['files'][0]['original_sha256'], 'another-supported-hash')
        tool.rollback(self.backup)
        self.assertEqual((self.client / 'SysTextures/A.utx').read_bytes(), b'originalA.utx')

    def test_theme_switch_rejects_unrelated_library(self):
        previous = self.bundle.parent / 'previous'
        previous.mkdir()
        (previous / 'manifest.json').write_text(json.dumps({'library_sha256': 'unrelated'}))
        with self.assertRaises(ValueError):
            tool.install(self.client, self.bundle, self.backup, from_bundle=previous)
        self.assertFalse(self.backup.exists())


if __name__ == '__main__':
    unittest.main()
