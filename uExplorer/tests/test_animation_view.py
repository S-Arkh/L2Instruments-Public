"""Known transforms, interpolation boundaries, playback and transition cleanup."""
import copy
import math
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from animation_decode import (prepare_animation,animation_pose,world_pose,slerp,
                              reference_skeleton)
import test_resource_gui as navigation


def bits(*values):
    return list(struct.unpack('<'+'I'*len(values),struct.pack('<'+'f'*len(values),*values)))


def animation():
    track=dict(flags=0,rotation_bits=[bits(0,0,0,1)],
               position_bits=[bits(0,0,0),bits(2,0,0)],time_bits=bits(0,1))
    child=dict(flags=0,rotation_bits=[bits(0,0,0,1)],position_bits=[bits(0,0,1)],time_bits=bits(0))
    move=dict(header=[0,0,0,bits(2)[0],0,0],bone_indices=[0,1],tracks=[track,child])
    sequence=dict(name='Move',frames=2,rate_bits=bits(1)[0])
    return dict(body=dict(bones=[dict(name='Root',parent=0),dict(name='Child',parent=0)],
                          moves=[move,copy.deepcopy(move)],sequences=[sequence,dict(sequence,name='Other')]))


class Sampling(unittest.TestCase):
    def test_interpolation_clamp_loop_and_duration_scale(self):
        prepared=prepare_animation(animation(),0)
        self.assertNotIn('error',prepared)
        self.assertEqual(animation_pose(prepared,.5),[(1.,0.,0.),(1.,0.,1.)])
        self.assertEqual(animation_pose(prepared,1.5),[(2.,0.,0.),(2.,0.,1.)])
        self.assertEqual(animation_pose(prepared,1.5,True),[(1.,0.,0.),(1.,0.,1.)])
        self.assertEqual(animation_pose(prepared,2.,True),[(0.,0.,0.),(0.,0.,1.)])
        doc=animation()
        doc['body']['moves'][0]['header'][3]=bits(4)[0]
        doc['body']['moves'][0]['tracks'][0]['time_bits']=bits(0,2)
        self.assertEqual(animation_pose(prepare_animation(doc,0),.5)[0],(1.,0.,0.))

    def test_quaternion_hierarchy_and_sign(self):
        q=(0,0,math.sqrt(.5),math.sqrt(.5))
        points=world_pose([0,0,1],[(0,0,0),(1,0,0),(1,0,0)],[q,q,(0,0,0,1)])
        self.assertAlmostEqual(points[1][0],0);self.assertAlmostEqual(points[1][1],1)
        self.assertAlmostEqual(points[2][0],1);self.assertAlmostEqual(points[2][1],1)
        self.assertEqual(slerp((0,0,0,1),(0,0,0,-1),.5),(0.,0.,0.,1.))
        half=slerp((0,0,0,1),q,.5)
        self.assertAlmostEqual(half[2],math.sin(math.pi/8))
        doc=dict(body=dict(bones=[
            dict(name='Root',parent=0,pose_bits=bits(*q,0,0,0,1,0,0,0)),
            dict(name='Child',parent=0,pose_bits=bits(0,0,0,1,1,0,0,1,0,0,0))]))
        points,_,_=reference_skeleton(doc)
        self.assertAlmostEqual(points[1][1],1)

    def test_reject_partial_invalid_time_and_missing_keys(self):
        for change in ('parent','mapping','time','empty','nan'):
            doc=animation();move=doc['body']['moves'][0]
            if change=='parent':doc['body']['bones'][1]['parent']=1
            elif change=='mapping':move['bone_indices']=[1,0]
            elif change=='time':move['tracks'][0]['time_bits']=bits(0,0)
            elif change=='empty':move['tracks'][0]['position_bits']=[]
            elif change=='nan':move['tracks'][0]['rotation_bits']=[bits(float('nan'),0,0,1)]
            self.assertIn('error',prepare_animation(doc,0),change)


class AnimationGui(navigation.ResourceGuiTests):
    def setUp(self):
        super().setUp()
        w=self.window;data=navigation.response()
        data['inventory']['candidates'].append(dict(id=6,path='Animation',**{'class':'Engine.MeshAnimation'}))
        w.clear_classes();w.loaded(data)
        original=w.core.request
        w.core.request=lambda **kw:{'result':animation()} if kw['operation']=='mesh_animation' else original(**kw)

    def test_play_pause_seek_repeat_and_cleanup(self):
        w=self.window;w.mode_tabs.setCurrentIndex(5);w.class_list.setCurrentRow(0);self.finish()
        view=w.animation_view
        self.assertIs(w.viewer.currentWidget(),view)
        self.assertFalse(view.timer.isActive())
        self.assertEqual(len(view.canvas.geometry['points']),2)
        view.play.click();self.assertTrue(view.timer.isActive())
        with patch('animation_view.time.monotonic',return_value=view.previous+.5):view.tick()
        self.assertAlmostEqual(view.position,.5)
        view.play.click();self.assertFalse(view.timer.isActive())
        view.slider.setValue(1500);self.assertAlmostEqual(view.position,1.5)
        view.repeat.setChecked(True);view.play.click()
        with patch('animation_view.time.monotonic',return_value=view.previous+1):view.tick()
        self.assertAlmostEqual(view.position,.5)
        view.sequence.setCurrentIndex(1)
        self.assertFalse(view.timer.isActive());self.assertFalse(view.play.isEnabled());self.finish()
        self.assertEqual(view.prepared['name'],'Other')
        view.play.click();w.mode_tabs.setCurrentIndex(0)
        self.assertFalse(view.timer.isActive());self.assertIsNone(view.prepared)
        self.assertIsNone(view.canvas.geometry)

    def test_error_sequence_can_recover(self):
        doc=animation();doc['body']['moves'][0]['tracks'][0]['position_bits']=[]
        w=self.window;w.core.request=lambda **kw:{'result':doc}
        w.mode_tabs.setCurrentIndex(5);w.class_list.setCurrentRow(0);self.finish()
        view=w.animation_view
        self.assertFalse(view.play.isEnabled())
        self.assertTrue(view.sequence.isEnabled())
        view.sequence.setCurrentIndex(1);self.finish()
        self.assertTrue(view.play.isEnabled())
        view.play.click();view.stop_button.click()
        self.assertFalse(view.timer.isActive());self.assertEqual(view.position,0)


if __name__=='__main__':unittest.main()
