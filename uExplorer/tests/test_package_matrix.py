"""Dependency staging contracts independent of proprietary client data."""
import unittest
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

from package_matrix import dependency_closure, dependency_lookup, package_payload, imported_packages, RESOURCE_TABLE_PROFILES


class DependencyTests(unittest.TestCase):
    def test_resource_table_profiles_do_not_enable_script_decoding(self):
        # One package import in a real name/import-table layout, no payload.
        names = b''.join(bytes([len(n)+1])+n.encode('ascii')+b'\0'+b'\0'*4 for n in ('Core', 'Package', 'Engine'))
        imports = b'\0\x01'+struct.pack('<i', 0)+b'\x02'
        with tempfile.TemporaryDirectory() as directory:
            resource = Path(directory)/'Resource.utx'
            script = Path(directory)/'Script.u'
            for version, licensee in RESOURCE_TABLE_PROFILES:
                header = struct.pack('<IHHI6i', 0x9e2a83c1, version, licensee, 0, 3, 36, 0, 36, 1, 36+len(names))
                resource.write_bytes(header+names+imports)
                self.assertEqual(imported_packages(resource), {'engine'})
            header = struct.pack('<IHHI6i', 0x9e2a83c1, 123, 33, 0, 3, 36, 0, 36, 1, 36+len(names))
            script.write_bytes(header+names+imports)
            with self.assertRaises(ValueError): imported_packages(script)
            resource.write_bytes(header+names+imports[:-1])
            with self.assertRaises(Exception): imported_packages(resource)

    def test_envelope_preserves_entire_payload(self):
        payload = b'\xc1\x83\x2a\x9e' + bytes(range(256))
        for marker in ('Lineage2Ver111', 'GamekitData111'):
            encoded = marker.encode('utf-16le') + bytes(b ^ 0xac for b in payload)
            self.assertEqual(package_payload(encoded), payload)
        self.assertEqual(package_payload(payload), payload)
        with self.assertRaises(ValueError):
            package_payload('Lineage2Ver121'.encode('utf-16le') + payload)
        key = sum(b'mixed.utx') & 255
        encoded = 'Lineage2Ver121'.encode('utf-16le') + bytes(b ^ key for b in payload)
        self.assertEqual(package_payload(encoded, 'MiXeD.utx'), payload)
        with self.assertRaises(ValueError):
            package_payload(encoded, 'different.utx')

    def test_resource_cycle_and_missing_transitive_dependency(self):
        files = {name: Path(name + suffix) for name, suffix in
                 [('script', '.u'), ('core', '.u'), ('texture', '.utx'), ('mesh', '.usx')]}
        graph = {'script': {'core', 'mesh'}, 'core': set(),
                 'mesh': {'texture', 'script'}, 'texture': {'mesh', 'missing'}}
        with patch('package_matrix.imported_packages', side_effect=lambda p: graph[p.stem]):
            self.assertEqual(dependency_closure(files['script'], files),
                             (['core', 'mesh', 'missing', 'texture'], ['missing']))

    def test_chain_reuses_resources_but_never_original_scripts(self):
        profile = {'files': {'core': Path('original/Core.u')},
                   'resources': {'texture': Path('frozen/Texture.utx')}, 'rebuilt': {}}
        self.assertNotIn('core', dependency_lookup(profile, 'chain'))
        self.assertIn('core', dependency_lookup(profile, 'original'))
        self.assertEqual(dependency_lookup(profile, 'chain'), profile['resources'])
        profile['rebuilt']['core'] = Path('rebuilt/Core.u')
        self.assertEqual(dependency_lookup(profile, 'chain')['core'], Path('rebuilt/Core.u'))


if __name__ == '__main__':
    unittest.main()
