"""Bind-pose identity, blended motion, invalid influences and raster texture smoke."""
import copy
import os
from pathlib import Path
import struct
import sys
import unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from skinning import prepare_skin,skin_geometry
from animation_view import AnimationView
from mesh_view import MeshCanvas
from PySide6.QtWidgets import QApplication
from unittest.mock import patch
from test_animation_view import bits


def pair():
    bones=[dict(name='Root',parent=0,pose_bits=bits(0,0,0,1,0,0,0,1,0,0,0)),
           dict(name='Child',parent=0,pose_bits=bits(0,0,0,1,1,0,0,1,0,0,0))]
    mesh=dict(body=dict(bones=bones,points_bits=[bits(0,0,0),bits(1,0,0),bits(0,0,1)],
        mesh_wedges=[dict(vertex=i,uv_bits=bits(0,0)) for i in range(3)],
        triangles=[dict(wedges=[0,1,2],material=0)],
        influences=[dict(point=0,bone=0,weight_bits=bits(1)[0]),
                    dict(point=1,bone=1,weight_bits=bits(.5)[0]),
                    dict(point=1,bone=0,weight_bits=bits(.5)[0]),
                    dict(point=2,bone=0,weight_bits=bits(1)[0])]))
    tracks=[dict(position_bits=[bits(0,0,0)],rotation_bits=[bits(0,0,0,1)],time_bits=bits(0)),
            dict(position_bits=[bits(1,0,0),bits(3,0,0)],rotation_bits=[bits(0,0,0,1)],time_bits=bits(0,1))]
    animation=dict(body=dict(bones=bones,sequences=[dict(name='Move',frames=2,rate_bits=bits(1)[0])],
        moves=[dict(header=[0,0,0,bits(2)[0],0,0],bone_indices=[0,1],tracks=tracks)]))
    return dict(mesh=mesh,animation=animation,body=animation['body'])


class Skin(unittest.TestCase):
    def animated_material(self):
        doc=pair()
        doc['surface']=dict(uv=[[(.25,.5)]*3],face_materials=[0],
            textures={0:dict(width=2,height=1,pixels=bytes([255,0,0,255,0,255,0,255]),
                            uv_pan_rate=.25)})
        return doc

    def test_skin_and_material_share_seek_loop_stop_without_mutation(self):
        app=QApplication.instance() or QApplication([])
        doc=self.animated_material();prepared=prepare_skin(doc,0);original=copy.deepcopy(prepared)
        view=AnimationView()
        try:
            view.load(doc,'skinning');view.display(prepared);view.set_loading(False)
            view.seek(1000)
            self.assertEqual(view.canvas.geometry['uv'],[[(.5,.5)]*3])
            posed=view.canvas.geometry['points']
            self.assertNotEqual(posed,skin_geometry(prepared,0)['points'])
            view.material_clock.setChecked(False)
            self.assertEqual(view.canvas.geometry['uv'],original['uv'])
            self.assertEqual(view.canvas.geometry['points'],posed)
            view.material_clock.setChecked(True)
            view.repeat.setChecked(True);view.position=2.5;view.render_pose()
            self.assertEqual(view.canvas.geometry['uv'],[[(.375,.5)]*3])
            self.assertEqual(view.canvas.geometry['points'],skin_geometry(prepared,.5,True)['points'])
            view.stop()
            self.assertEqual(view.canvas.geometry['uv'],original['uv'])
            self.assertEqual(prepared,original)
        finally:view.close();app.processEvents()

    def test_material_follows_speed_and_pauses_on_loading_and_hide(self):
        app=QApplication.instance() or QApplication([])
        doc=self.animated_material();view=AnimationView()
        try:
            view.show();view.load(doc,'skinning');view.display(prepare_skin(doc,0));view.set_loading(False)
            view.speed.setCurrentIndex(view.speed.findData(2.))
            view.previous=10.
            with patch('animation_view.time.monotonic',return_value=10.25):view.tick()
            self.assertEqual(view.position,.5)
            self.assertEqual(view.canvas.geometry['uv'],[[(.375,.5)]*3])
            view.toggle();view.set_loading(True)
            self.assertFalse(view.timer.isActive())
            view.set_loading(False);view.toggle();view.hide()
            self.assertFalse(view.timer.isActive())
        finally:view.close();app.processEvents()

    def test_long_clip_material_clock_is_explicitly_disabled(self):
        app=QApplication.instance() or QApplication([])
        doc=self.animated_material();prepared=prepare_skin(doc,0)
        prepared['rate']=.0001
        view=AnimationView()
        try:
            view.load(doc,'skinning');view.display(prepared);view.set_loading(False)
            self.assertFalse(view.material_clock.isEnabled())
            self.assertIn('3600',view.info.text())
            view.seek(4000000)
            self.assertEqual(view.canvas.geometry['uv'],prepared['uv'])
        finally:view.close();app.processEvents()

    def test_bind_identity_and_half_weight_translation(self):
        p=prepare_skin(pair(),0);self.assertNotIn('error',p)
        def points(t):
            return [tuple(v*p['scale']+c for v,c in zip(row,p['center']))
                    for row in skin_geometry(p,t)['points']]
        self.assertEqual(points(0),[(0.,0.,0.),(1.,0.,0.),(0.,0.,1.)])
        self.assertAlmostEqual(points(.5)[1][0],1.5)
        self.assertAlmostEqual(points(1)[1][0],2.)
        doc=pair();doc['mesh']['body']['influences'][0]['bone']=9
        self.assertIn('error',prepare_skin(doc,0))
        doc=pair();doc['mesh']['body']['influences'].pop()
        self.assertIn('error',prepare_skin(doc,0))

    def test_texture_raster_and_skin_player(self):
        app=QApplication.instance() or QApplication([])
        canvas=MeshCanvas();canvas.resize(300,300)
        geometry=dict(points=[(-1,0,-1),(1,0,-1),(0,0,1)],polygons=[[0,1,2]],
            edges=[(0,1),(1,2),(0,2)],uv=[[(0,0),(1,0),(.5,1)]],face_materials=[0],
            textures={0:dict(pixels=bytes([255,0,0,255])*4,width=2,height=2)})
        canvas.display(geometry);canvas.yaw=canvas.pitch=0.;canvas.style=2
        image=canvas.grab().toImage()
        self.assertEqual(image.pixelColor(150,150).red(),255)
        self.assertEqual(image.pixelColor(150,150).green(),0)
        view=AnimationView();doc=pair();view.load(doc,'skinning')
        view.display(prepare_skin(doc,0));view.set_loading(False)
        view.slider.setValue(500)
        self.assertEqual(len(view.canvas.geometry['points']),3)
        view.play.click();self.assertTrue(view.timer.isActive())
        view.clear();self.assertFalse(view.timer.isActive())
        view.close();canvas.close()

    def test_track_binding_uses_names_with_animation_only_root(self):
        doc=pair();body=doc['animation']['body']
        bones=copy.deepcopy(body['bones'])
        bones[0]['parent']=0;bones[1]['parent']=1
        body['bones']=[dict(name='Auxiliary',parent=0)]+bones
        move=body['moves'][0]
        move['tracks']=[copy.deepcopy(move['tracks'][0])]+move['tracks']
        move['bone_indices']=[0,1,2]
        p=prepare_skin(doc,0);self.assertNotIn('error',p)
        geometry=skin_geometry(p,1)
        point=geometry['points'][1][0]*p['scale']+p['center'][0]
        self.assertAlmostEqual(point,2.)


if __name__=='__main__':unittest.main()
