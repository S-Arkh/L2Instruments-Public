import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_profile
from package_candidate import assemble, digest


class PipelineBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root/'inputs'
        self.inputs.mkdir()
        for name in ('Core.dll', 'Core.u', 'Interface.u', 'Interface.xdat'):
            (self.inputs/name).write_bytes(name.encode())
        self.out = self.root/'test_interfaces/local/output'

    def run_pipeline(self):
        return prepare_profile.run(self.inputs, self.inputs, self.inputs,
                                   self.inputs, self.inputs, self.inputs/'library.dll', self.out)

    def test_unknown_profile_never_loads_or_patches(self):
        with patch.object(prepare_profile, 'ROOT', self.root), \
             patch.object(prepare_profile, 'analyze', return_value={'approved_profile': None}), \
             patch.object(prepare_profile, 'Core') as core, \
             patch.object(prepare_profile, 'prepare') as native:
            with self.assertRaisesRegex(ValueError, 'No UI adapter'):
                self.run_pipeline()
            core.assert_not_called()
            native.assert_not_called()
        report = json.loads((self.out/'pipeline.json').read_text())
        self.assertFalse(report['completed'])
        self.assertFalse((self.out/'native').exists())

    def test_missing_dependency_stops_before_library_load(self):
        with patch.object(prepare_profile, 'ROOT', self.root), \
             patch.object(prepare_profile, 'analyze', return_value={'approved_profile': 'gracia_epilogue_0941cac5'}), \
             patch.object(prepare_profile, 'Core') as core:
            with self.assertRaisesRegex(ValueError, 'Missing original dependency'):
                self.run_pipeline()
            core.assert_not_called()
        report = json.loads((self.out/'pipeline.json').read_text())
        self.assertEqual(report['stages']['dependencies'], 'failed')

    def test_changed_artifact_prevents_candidate_creation(self):
        compile_dir, layout_dir, native_dir = [self.root/n for n in ('compile', 'layout', 'native')]
        (compile_dir/'System').mkdir(parents=True)
        layout_dir.mkdir()
        (native_dir/'client').mkdir(parents=True)
        package = compile_dir/'System/Interface.u'
        package.write_bytes(b'compiled')
        (compile_dir/'result.json').write_text(json.dumps(dict(profile='gracia', compiled=True,
            compiler_exit=0, sha256=digest(package), build_identity='build')))
        layout = layout_dir/'Interface.xdat'
        layout.write_bytes(b'layout')
        (layout_dir/'Interface.json').write_text(json.dumps(dict(schema='ct24.XDAT',
            position='bottom_right_menu', unrelated_bytes_preserved=True, output_sha256=digest(layout))))
        files = {}
        for name in ('Core.dll', 'ExtensionL2.dll'):
            p = native_dir/'client'/name
            p.write_bytes(name.encode())
            files[name] = digest(p)
        (native_dir/'report.json').write_text(json.dumps(dict(patch={'profile': 'gracia_epilogue_0941cac5'},
            native_bundle_verified=True, tests={n: {'passed': True} for n in ('loader', 'vm')}, files=files)))
        package.write_bytes(b'changed after compilation')
        with self.assertRaisesRegex(ValueError, 'Artifact hash mismatch'):
            assemble(compile_dir, layout_dir, native_dir, self.out)
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
