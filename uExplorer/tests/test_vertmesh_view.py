"""Packed signed coordinates, temporal boundaries and GUI transitions."""
import os
from pathlib import Path
import sys
import struct
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from vertmesh_decode import unpack_vertex, prepare_vertmesh, vertex_geometry
import test_resource_gui as navigation


def document():
    return {'body':dict(vertex_count=3, animated_vertex_count=3, frame_count=2,
        packed_original_vertices=[0,2,2<<11,2,4,2|(2<<11)],
        transforms=[0x3f800000]*3+[0]*6,
        wedges=[{'vertex':i} for i in range(3)], faces=[[0,1,2,0]],
        sequences=[dict(name='Move',start=0,frames=2,rate_bits=0x3f800000),
                   dict(name='Still',start=1,frames=1,rate_bits=0x3f800000)])}


class Sampling(unittest.TestCase):
    def test_signed_boundaries(self):
        self.assertEqual(unpack_vertex(0xffffffff),(-1,-1,-1))
        self.assertEqual(unpack_vertex(1024|(1024<<11)|(512<<22)),(-1024,-1024,-512))
        self.assertEqual(unpack_vertex(1023|(1023<<11)|(511<<22)),(1023,1023,511))

    def test_interpolation_and_fixed_bounds(self):
        p=prepare_vertmesh(document(),0)
        def first(t,repeat=False):
            g=vertex_geometry(p,t,repeat)
            return tuple(v*p['scale']+c for v,c in zip(g['points'][0],p['center']))
        self.assertEqual(first(.5),(1.,0.,0.))
        self.assertEqual(first(1.5),(2.,0.,0.))
        self.assertEqual(first(1.5,True),(1.,0.,0.))
        self.assertEqual(first(2,True),(0.,0.,0.))
        self.assertEqual(vertex_geometry(p,0)['bounds'],vertex_geometry(p,1)['bounds'])

    def test_float_precision_and_nonfinite_rejection(self):
        doc=document();body=doc['body'];del body['packed_original_vertices']
        points=[(.25,0.,0.),(2.,0.,0.),(0.,2.,0.),(2.25,0.,0.),(4.,0.,0.),(2.,2.,0.)]
        body['vertices_bits']=[list(struct.unpack('<3I',struct.pack('<3f',*p))) for p in points]
        prepared=prepare_vertmesh(doc,0)
        self.assertEqual(prepared['storage'],'float')
        geometry=vertex_geometry(prepared,.5)
        recovered=geometry['points'][0][0]*prepared['scale']+prepared['center'][0]
        self.assertEqual(recovered,1.25)
        body['vertices_bits'][0][0]=0x7f800000
        self.assertIn('error',prepare_vertmesh(doc,0))

    def test_invalid_declared_range_has_separate_stored_frame_view(self):
        doc=document();doc['body']['sequences'][0]['frames']=12
        self.assertIn('error',prepare_vertmesh(doc,0))
        stored=prepare_vertmesh(doc,len(doc['body']['sequences']))
        self.assertEqual(stored['frames'],2)
        self.assertTrue(stored['diagnostic_frames'])
        self.assertEqual(stored['rate'],30.)
        self.assertEqual(doc['body']['sequences'][0]['frames'],12)

    def test_reject_bad_indices_ranges_rates_and_transforms(self):
        changes=[
            lambda b:b['wedges'][0].update(vertex=3),
            lambda b:b['faces'][0].__setitem__(0,3),
            lambda b:b['sequences'][0].update(start=1),
            lambda b:b['sequences'][0].update(rate_bits=0),
            lambda b:b['transforms'].__setitem__(6,1),
            lambda b:b['packed_original_vertices'].pop(),
            lambda b:b.update(animated_vertex_count=2),
            lambda b:b.update(vertices_bits=[[0,0,0]])]
        for change in changes:
            doc=document();change(doc['body'])
            self.assertIn('error',prepare_vertmesh(doc,0))
        self.assertIn('error',prepare_vertmesh(document(),-1))


class VertexGui(navigation.ResourceGuiTests):
    def test_vertex_playback_seek_sequence_and_mode_cleanup(self):
        w=self.window;data=navigation.response()
        data['inventory']['candidates'].append(dict(id=7,path='VertexMesh',**{'class':'Engine.VertMesh'}))
        w.clear_classes();w.loaded(data)
        original=w.core.request
        w.core.request=lambda **kw:{'result':document()} if kw['operation']=='vert_mesh' else original(**kw)
        w.mode_tabs.setCurrentIndex(4)
        for i in range(w.class_list.count()):
            if w.class_list.item(i).text()=='VertexMesh':w.class_list.setCurrentRow(i);break
        self.finish();view=w.animation_view
        self.assertIs(w.viewer.currentWidget(),view)
        self.assertFalse(view.timer.isActive())
        self.assertEqual(view.prepared['kind'],'vert_mesh')
        self.assertEqual(len(view.canvas.geometry['polygons']),1)
        view.play.click();self.assertTrue(view.timer.isActive())
        view.slider.setValue(500);self.assertEqual(view.position,.5)
        view.stop_button.click();self.assertEqual(view.position,0)
        view.sequence.setCurrentIndex(1);self.finish()
        self.assertEqual(view.prepared['name'],'Still')
        view.play.click();w.mode_tabs.setCurrentIndex(0)
        self.assertFalse(view.timer.isActive());self.assertIsNone(view.canvas.geometry)


if __name__=='__main__':unittest.main()
