import sys
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from ue2package import Package, Reader
from sdk_enums import augment, compact, enum_members
from compilation_sdk import object_with_runtime_storage, native_storage
from extract_sources import script_text
from local_paths import PACKAGES, RUNTIME_SDK

integration = unittest.skipUnless(os.environ.get('L2_INTEGRATION') == '1',
                                  'Set L2_INTEGRATION=1 and external input paths')


class SdkTests(unittest.TestCase):
    @integration
    def test_symbolic_vehicle_field_shapes(self):
        client = Package(PACKAGES / 'Engine.u')
        for name in ('MaxFuel', 'CurFuel', 'DriverID'):
            _, entry = client.find('Vehicle.' + name)
            self.assertEqual(client.ref(entry.cls), 'Core.IntProperty')
            r = Reader(client.data[entry.offset:entry.offset + entry.size])
            self.assertEqual(client.name(r.index()), 'None')
            self.assertEqual(r.index(), 0)
            r.index()
            self.assertEqual(r.unpack('<i'), 1)
            self.assertEqual(r.unpack('<I'), 0)
            client.name(r.index())
            self.assertEqual(r.pos, len(r.data))
    def test_compact_index_round_trip(self):
        for value in [0, 1, -1, 63, 64, -64, 8191, 8192, 0x7fffffff, -0x80000000]:
            data = compact(value)
            r = Reader(data)
            self.assertEqual(r.index(), value)
            self.assertEqual(r.pos, len(data))

    @integration
    def test_native_storage_keeps_client_apis(self):
        runtime = Package(RUNTIME_SDK / 'System/Core.u')
        core = PACKAGES / 'Core.u'
        client = Package(core if core.exists() else PACKAGES.parent / 'Core.u')
        _, re = runtime.find('Object.ScriptText')
        _, ce = client.find('Object.ScriptText')
        _, rt, _ = script_text(runtime, re)
        _, ct, _ = script_text(client, ce)
        result = object_with_runtime_storage(ct, rt)
        _, spans = native_storage(result)
        _, expected = native_storage(rt)
        self.assertEqual([result[a:b] for a, b in spans], [rt[a:b] for a, b in expected])
        self.assertIn('INT64', result)
        self.assertIn('native(400)', result)
        self.assertNotIn('var native int CacheIndex;', result)

    @integration
    def test_enum_augmentation_preserves_native_objects(self):
        runtime = RUNTIME_SDK / 'System/Engine.u'
        client = PACKAGES / 'Engine.u'
        original = Package(runtime)
        source = Package(client)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'Engine.u'
            augment(runtime, client, output, ['Actor.EL2ObjectType', 'Interactions.EInputKey'])
            result = Package(output)
            self.assertEqual(len(result.exports), len(original.exports) + 1)
            for path in ['Actor.EL2ObjectType', 'Interactions.EInputKey']:
                _, _, expected, _ = enum_members(source, path)
                _, _, actual, _ = enum_members(result, path)
                self.assertEqual([source.name(i) for i in expected], [result.name(i) for i in actual])
            for i, entry in enumerate(original.exports, 1):
                if original.ref(i) in ('Actor', 'Interactions.EInputKey'):
                    continue
                new = result.exports[i - 1]
                self.assertEqual((new.offset, new.size, new.flags), (entry.offset, entry.size, entry.flags))
                self.assertEqual(result.data[new.offset:new.offset + new.size],
                                 original.data[entry.offset:entry.offset + entry.size])
            self.assertEqual(result.class_flags('Actor'), original.class_flags('Actor'))
            _, actor = result.find('Actor')
            r = Reader(result.data[actor.offset:actor.offset + actor.size])
            for _ in range(3):
                r.index()
            self.assertEqual(result.ref(r.index()), 'Actor.EL2ObjectType')


if __name__ == '__main__':
    unittest.main()
