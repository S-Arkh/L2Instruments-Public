"""Offscreen navigation checks; synthetic inventories, no client packages."""
import os
from pathlib import Path
import sys
import unittest
import io
import struct
import time
import wave
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
import app
from resource_view import groups, read_model_preview, summary_text


class Settings:
    def value(self, key, default=''):
        return default
    def setValue(self, *args):
        pass


class FakeCore:
    def __init__(self):
        self.calls = []
    def request(self, **request):
        self.calls.append(request)
        if request['operation'] == 'sound':
            data=io.BytesIO()
            with wave.open(data,'wb') as output:
                output.setparams((1,2,8000,0,'NONE',''))
                output.writeframes(b'\x10\x20'*4000)
            return {'result': {'body': {'audio_hex': data.getvalue().hex(), 'format': 'wav'}}}
        if request['operation'] == 'texture':
            raise RuntimeError('Unsupported material profile')
        return {'result': {'code': 'class Example;', 'method': 'source', 'status': 'source'}}


def response():
    entries = [
        {'id': 2, 'path': 'Group.Picture', 'class': 'Engine.Texture'},
        {'id': 3, 'path': 'Group.Sound', 'class': 'Engine.Sound'},
        {'id': 4, 'path': 'Unknown', 'class': 'Engine.CustomResource'},
    ]
    return {'package': {'classes': [{'id': 1, 'path': 'Example', 'super': 'Object'}],
                        'version': 133, 'licensee': 40, 'envelope': 'plain'},
            'inventory': {'candidates': entries}}


class ResourceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
    def setUp(self):
        with patch.object(app, 'Core', FakeCore), patch.object(app, 'QSettings', lambda *a: Settings()):
            self.window = app.MainWindow()
        self.window.package = 'synthetic.u'
        self.window.loaded(response())
    def finish(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            self.application.processEvents()
            if self.window.worker is None:
                return
            QTest.qWait(5)
        self.fail('Background resource read did not finish')
    def tearDown(self):
        self.finish()
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
    def test_switch_restore_and_readonly(self):
        w = self.window
        w.class_list.setCurrentRow(0); self.finish()
        w.class_filter.setText('Example')
        w.mode_tabs.setCurrentIndex(2)
        self.assertEqual(w.mode, 'sounds')
        self.assertEqual(w.class_list.count(), 1)
        self.assertFalse(w.selected_button.isEnabled())
        w.class_list.setCurrentRow(0); self.finish()
        self.assertEqual(w.core.calls[-1]['object_id'], 3)
        self.assertIsNotNone(w.sound_view)
        self.assertTrue(w.sound_view.plot.wave)
        self.assertEqual(w.sound_view.player.playbackState().name, 'StoppedState')
        self.assertTrue(w.resource_text.isReadOnly())
        w.mode_tabs.setCurrentIndex(0); self.finish()
        self.assertEqual(w.class_filter.text(), 'Example')
        self.assertEqual(w.class_list.currentItem().data(Qt.UserRole)['id'], 1)
        self.assertIn('class Example;', w.code.toPlainText())
        self.assertIsNone(w.sound_view.buffer)
    def test_unsupported_and_failure_clear(self):
        w = self.window
        w.mode_tabs.setCurrentIndex(6); w.class_list.setCurrentRow(0)
        self.assertIn('Unknown', w.resource_text.toPlainText())
        self.assertEqual(len(w.core.calls), 0)
        w.mode_tabs.setCurrentIndex(1); w.class_list.setCurrentRow(0); self.finish()
        self.assertIn('Unsupported material profile', w.resource_text.toPlainText())
        self.assertNotIn('Unknown', w.resource_text.toPlainText())
        w.clear_classes()
        self.assertEqual(w.class_list.count(), 0)
        self.assertEqual(w.resource_text.toPlainText(), '')
    def test_inventory_without_code(self):
        r = response(); r['package']['classes'] = []
        self.window.clear_classes(); self.window.loaded(r)
        self.assertEqual(self.window.mode, 'textures')
        self.assertFalse(self.window.mode_tabs.isTabEnabled(0))
        self.assertFalse(self.window.all_button.isEnabled())
    def test_routing_and_display_bounds(self):
        result = groups({'candidates': [
            {'id': 1, 'path': 'A', 'class': 'Engine.AnimNotify_Sound'},
            {'id': 2, 'path': 'B', 'class': 'Engine.Model'},
            {'id': 3, 'path': 'C', 'class': 'Engine.BlockingVolume'},
        ]})
        self.assertEqual(result['animations'][0]['operation'], 'animation_notify')
        self.assertEqual(result['models'][0]['operation'], 'model')
        self.assertEqual(result['other'][0]['operation'], 'blocking_volume')
        self.assertLess(len(summary_text({'huge': list(range(100000))})), 2000)

    def test_blocking_volume_saved_properties_and_model_navigation(self):
        w=self.window
        data=response()
        data['inventory']['candidates'].extend([
            {'id':8,'path':'Model1','class':'Engine.Model'},
            {'id':9,'path':'BlockingVolume1','class':'Engine.BlockingVolume'},
        ])
        bits=lambda xyz:list(struct.unpack('<3I',struct.pack('<3f',*xyz)))
        model=dict(points=[bits(p) for p in ((0,0,0),(1,0,0),(0,1,0))],
                   vertices=[[0,-1],[1,-1],[2,-1]],
                   nodes=[dict(vertex_pool=0,vertex_count=3)],status='partial',remaining_bytes=5)
        actor=dict(path='BlockingVolume1',status='saved_properties_decoded',
                   brush={'id':8,'path':'Model1','class':'Model'},
                   properties=[{'name':'bDeleteMe','value':True}],
                   inherited_defaults_resolved=False,world_transform_applied=False)
        def request(**kw):
            w.core.calls.append(kw)
            if kw['operation']=='blocking_volume':return {'result':actor}
            if kw['operation']=='model':return {'result':model}
            raise AssertionError(kw)
        w.core.request=request
        w.clear_classes();w.loaded(data);w.mode_tabs.setCurrentIndex(6)
        for row in range(w.class_list.count()):
            if w.class_list.item(row).data(Qt.UserRole)['id']==9:
                w.class_list.setCurrentRow(row);break
        else:self.fail('BlockingVolume is missing')
        self.finish()
        self.assertIs(w.viewer.currentWidget(),w.volume_view)
        self.assertTrue(w.volume_view.properties.isReadOnly())
        self.assertIn('мировое преобразование',w.volume_view.warning.text())
        self.assertIn('сохранён признак удаления',w.volume_view.warning.text())
        self.assertIn('BlockingVolume1',w.volume_view.properties.toPlainText())
        self.assertTrue(w.volume_view.model_button.isEnabled())
        w.volume_view.load(dict(actor,properties=[{'name':'bPendingDelete','value':False}]),w.package)
        self.assertNotIn('сохранён признак удаления',w.volume_view.warning.text())
        w.volume_view.load(dict(actor,properties=[{'name':'bPendingDelete','value':True}]),w.package)
        self.assertIn('сохранён признак удаления',w.volume_view.warning.text())
        QTest.mouseClick(w.volume_view.model_button,Qt.LeftButton);self.finish()
        self.assertEqual(w.mode,'models')
        self.assertEqual(w.class_list.currentItem().data(Qt.UserRole)['id'],8)
        self.assertIs(w.viewer.currentWidget(),w.mesh_view)
        self.assertEqual(w.mesh_view.canvas.geometry['polygons'],[[0,1,2]])
        self.assertEqual(w.volume_view.model_id,0)
        self.assertFalse(w.volume_view.model_button.isEnabled())
        self.assertEqual(w.volume_view.properties.toPlainText(),'')

    def test_empty_model_opens_saved_polys_only_on_request(self):
        w=self.window
        data=response()
        data['inventory']['candidates'].extend([
            {'id':8,'path':'Model1','class':'Engine.Model'},
            {'id':9,'path':'BlockingVolume1','class':'Engine.BlockingVolume'},
            {'id':10,'path':'Polys1','class':'Engine.Polys'},
        ])
        bits=lambda xyz:list(struct.unpack('<3I',struct.pack('<3f',*xyz)))
        points=[bits(p) for p in ((0,0,0),(1,0,0),(0,1,0))]
        actor=dict(path='BlockingVolume1',status='saved_properties_decoded',
                   brush={'id':8,'path':'Model1','class':'Model'},properties=[])
        model=dict(points=points,vertices=[],nodes=[],status='partial',remaining_bytes=5,
                   polys={'id':10,'path':'Polys1','class':'Polys'})
        polys=dict(polygons=[dict(vertices_bits=points)],status='decoded',
                   reconstruction_supported=False)
        calls=[]
        def request(**kw):
            calls.append((kw['operation'],kw['object_id']))
            if kw['operation']=='blocking_volume':return {'result':actor}
            if kw['operation']=='model':return {'result':model}
            if kw['operation']=='polys':return {'result':polys}
            raise AssertionError(kw)
        w.core.request=request
        w.clear_classes();w.loaded(data);w.mode_tabs.setCurrentIndex(6)
        for row in range(w.class_list.count()):
            if w.class_list.item(row).data(Qt.UserRole)['id']==9:
                w.class_list.setCurrentRow(row);break
        else:self.fail('BlockingVolume is missing')
        self.finish()
        QTest.mouseClick(w.volume_view.model_button,Qt.LeftButton);self.finish()
        view=w.mesh_view
        self.assertIs(w.viewer.currentWidget(),view)
        self.assertIsNone(view.canvas.geometry)
        self.assertIn('No drawable geometry',view.info.text())
        self.assertIn('частичный разбор',view.info.text())
        self.assertIn('5 байт не расшифрованы',view.info.text())
        self.assertTrue(view.polys_button.isEnabled())
        self.assertIn('игровая коллизия не подтверждены',view.polys_warning.text())
        self.assertEqual(calls,[('blocking_volume',9),('model',8)])
        QTest.mouseClick(view.polys_button,Qt.LeftButton);self.finish()
        self.assertEqual(w.class_list.currentItem().data(Qt.UserRole)['id'],10)
        self.assertEqual(view.operation,'polys')
        self.assertEqual(view.canvas.geometry['polygons'],[[0,1,2]])
        self.assertIn('игровая коллизия не подтверждены',view.info.text())
        self.assertFalse(view.polys_button.isEnabled())
        self.assertEqual(calls[-1],('polys',10))

    def test_polys_navigation_requires_valid_local_reference_and_clears(self):
        from mesh_view import MeshView
        view=MeshView()
        emitted=[]
        view.navigate.connect(lambda path,identifier:emitted.append((path,identifier)))
        for ref in (None,{}, {'id':0,'class':'Polys'}, {'id':-1,'class':'Polys'},
                    {'id':True,'class':'Polys'}, {'id':3,'class':'Model'}):
            view.load({'polys':ref},'model','Model','synthetic.u')
            self.assertFalse(view.polys_button.isEnabled())
            view.open_polys()
        view.load({'polys':{'id':3,'class':'Polys'}},'model','Model','synthetic.u')
        self.assertTrue(view.polys_button.isEnabled())
        view.set_loading(True);self.assertFalse(view.polys_button.isEnabled())
        view.set_loading(False);self.assertTrue(view.polys_button.isEnabled())
        view.open_polys();self.assertEqual(emitted,[('synthetic.u',3)])
        view.clear()
        self.assertFalse(view.polys_button.isEnabled())
        view.open_polys();self.assertEqual(len(emitted),1)
        view.load({'polys':{'id':3,'class':'Polys'}},'model','Model')
        self.assertFalse(view.polys_button.isEnabled())
        view.load({'polys':{'id':3,'class':'Polys'}},'polys','Polys','synthetic.u')
        self.assertFalse(view.polys_button.isEnabled())
        view.close();view.deleteLater()

    def test_model_fallback_only_for_unsupported_profile(self):
        class ModelCore:
            def __init__(self,error=None):self.calls=[];self.error=error
            def request(self,**kw):
                self.calls.append(kw['operation'])
                if kw['operation']=='model' and self.error:raise RuntimeError(self.error)
                return {'result':{'status':'partial' if kw['operation']=='model_collision' else 'decoded'}}
        ordinary=ModelCore()
        self.assertEqual(read_model_preview(ordinary,'fixture',2)['result']['status'],'decoded')
        self.assertEqual(ordinary.calls,['model'])
        unsupported=ModelCore('Unsupported Model class/profile')
        self.assertEqual(read_model_preview(unsupported,'fixture',2)['result']['status'],'partial')
        self.assertEqual(unsupported.calls,['model','model_collision'])
        malformed=ModelCore('Invalid Model vertex point')
        with self.assertRaisesRegex(RuntimeError,'Invalid Model'):
            read_model_preview(malformed,'fixture',2)
        self.assertEqual(malformed.calls,['model'])
        class LevelCore:
            def __init__(self,error='Unsupported Model zones'):self.calls=[];self.error=error
            def request(self,**kw):
                self.calls.append(kw['operation'])
                if kw['operation']=='model':raise RuntimeError('Unsupported Model class/profile')
                if kw['operation']=='model_collision':raise RuntimeError(self.error)
                return {'result':{'status':'partial','remaining_bytes':100}}
        level=LevelCore()
        self.assertEqual(read_model_preview(level,'fixture',2)['result']['remaining_bytes'],100)
        self.assertEqual(level.calls,['model','model_collision','model_level_geometry'])
        malformed_level=LevelCore('Invalid Model vertex point')
        with self.assertRaisesRegex(RuntimeError,'Invalid Model vertex point'):
            read_model_preview(malformed_level,'fixture',2)
        self.assertEqual(malformed_level.calls,['model','model_collision'])


if __name__ == '__main__':
    unittest.main()
