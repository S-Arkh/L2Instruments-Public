"""Manual saved-frame controls stay separate from diagnostic UV time."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from material_graph import ResourceResolver
from mesh_view import MeshView
from textured_mesh import prepare_textured
from test_coordinate_source_view import mesh
from test_saved_material_frames import animated_combiner_fixture
from test_shader_modifier_view import FixtureCore


class SavedMaterialFramesGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application=QApplication.instance() or QApplication([])

    def test_manual_selection_and_view_preservation(self):
        documents=animated_combiner_fixture();core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            base=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                  overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
            selected=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)},
                                      frame_selection=(0,1,1))
        view=MeshView()
        try:
            view.show();view.display(base);self.application.processEvents()
            self.assertTrue(view.frame_controls.isVisible())
            self.assertEqual(view.frame_sampler.count(),4)
            calls=[];view.frame_requested.connect(lambda *values:calls.append(values))
            view.frame_sampler.setCurrentIndex(1);view.frame_step.setValue(1);view.frame_apply.click()
            self.assertEqual(calls,[(0,1,1)])
            view.uv_time.setValue(1.)
            view.canvas.yaw=.7;view.canvas.pitch=.2;view.canvas.zoom=2.
            previous_uv=view.canvas.geometry['uv']
            view.display(selected,preserve_view=True);self.application.processEvents()
            self.assertEqual(view.frame_sampler.currentData(),(0,1))
            self.assertEqual(view.frame_step.value(),1)
            self.assertEqual(view.uv_time.value(),1.)
            self.assertEqual((view.canvas.yaw,view.canvas.pitch,view.canvas.zoom),(.7,.2,2.))
            self.assertEqual(view.canvas.geometry['uv'],previous_uv)
            self.assertIn('Шаг AnimNext (диагностика)',view.info.text())
            view.set_loading(True);self.assertFalse(view.frame_controls.isEnabled())
            view.set_loading(False);self.assertTrue(view.frame_controls.isEnabled())
            view.clear();self.assertFalse(view.frame_controls.isVisible())
        finally:
            view.close();self.application.processEvents()

    def test_diagnostic_playback_stops_at_end_and_keeps_last_frame(self):
        documents=animated_combiner_fixture();core=FixtureCore(documents)
        def prepare(selection=None):
            with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
                return prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                        overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)},
                                        frame_selection=selection)
        view=MeshView()
        try:
            view.show();view.display(prepare());self.application.processEvents()
            calls=[]
            def request(slot,sampler,step):
                calls.append((slot,sampler,step))
                view.set_loading(True)
                view.display(prepare((slot,sampler,step)),preserve_view=True)
                view.set_loading(False)
            view.frame_requested.connect(request)
            view.frame_fps.setValue(12.)
            view.uv_time.setValue(.75)
            view.frame_play.setChecked(True)
            deadline=time.monotonic()+10
            while view.frame_play.isChecked() and time.monotonic()<deadline:
                QTest.qWait(10)
            self.assertEqual(calls,[(0,0,0),(0,0,1),(0,0,2),(0,0,3)])
            self.assertFalse(view.frame_play.isChecked())
            self.assertFalse(view.frame_timer.isActive())
            self.assertEqual(view.frame_step.value(),2)
            self.assertEqual(view.canvas.material_base['textures'][0]['fragment_layers'][0]['pixels'],b'\xff'*8)
            self.assertEqual(view.uv_time.value(),.75)
            self.assertIn('оставлен предыдущий кадр',view.info.text())
            self.assertIn('игровое время и синхронизация с UV не подтверждены',view.info.text())
        finally:
            view.close();self.application.processEvents()

    def test_playback_stops_at_limit_and_when_hidden(self):
        core=FixtureCore(animated_combiner_fixture())
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
        view=MeshView()
        try:
            view.show();view.display(geometry);self.application.processEvents()
            view.frame_step.setValue(31);view.frame_play.setChecked(True)
            view.tick_saved_frames()
            self.assertFalse(view.frame_play.isChecked())
            self.assertIn('предел 31',view.info.text())
            view.frame_step.setValue(0);view.frame_play.setChecked(True)
            view.hide();self.application.processEvents()
            self.assertFalse(view.frame_play.isChecked())
            self.assertFalse(view.frame_timer.isActive())
        finally:
            view.close();self.application.processEvents()


if __name__=='__main__':unittest.main()
