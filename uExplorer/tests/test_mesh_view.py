"""Independent geometric fixtures and actual asynchronous widget navigation."""
from copy import deepcopy
import math
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from mesh_decode import mesh_preview, prepare_mesh, project
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
import test_resource_gui as navigation


def bits(x,y,z):
    return list(struct.unpack('<3I',struct.pack('<3f',x,y,z)))


def mesh():
    return dict(vertices=[dict(position_bits=bits(*p)) for p in
                          [(10,20,30),(12,20,30),(12,22,30),(10,22,30)]],
                indices=[0,1,2,0,2,3],
                sections=[dict(first_index=0,face_count=2)],
                collision_faces=[dict(vertices=[0,1,3])])


class Geometry(unittest.TestCase):
    def test_static_sections_collision_and_bounds(self):
        result=prepare_mesh(mesh(),'static_mesh')
        self.assertEqual(result['bounds'],((10,20,30),(12,22,30)))
        self.assertEqual(result['points'][0],(-1,-1,0))
        self.assertEqual(len(result['edges']),5)
        self.assertEqual(result['polygons'],[[0,1,2],[0,2,3]])
        self.assertEqual(prepare_mesh(mesh(),'static_mesh','collision')['polygons'],[[0,1,3]])

    def test_bad_indices_nonfinite_and_limits(self):
        doc=mesh();doc['indices'][2]=99
        with self.assertRaises(ValueError):prepare_mesh(doc,'static_mesh')
        doc=mesh();doc['vertices'][0]['position_bits']=bits(float('nan'),0,0)
        with self.assertRaises(ValueError):prepare_mesh(doc,'static_mesh')
        doc=mesh();doc['sections'][0]['first_index']=1
        with self.assertRaises(ValueError):prepare_mesh(doc,'static_mesh')
        with patch('mesh_decode.MAX_FACES',1):
            with self.assertRaises(ValueError):prepare_mesh(mesh(),'static_mesh')

    def test_polys_bsp_and_skeletal_wedge_mapping(self):
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        p=prepare_mesh(dict(polygons=[dict(vertices_bits=points)]),'polys')
        b=prepare_mesh(dict(points=points,vertices=[[2,-1],[0,-1],[1,-1]],
                            nodes=[dict(vertex_pool=0,vertex_count=3)]),'model')
        self.assertEqual(p['polygons'],[[0,1,2]])
        self.assertTrue(any('игровая коллизия не подтверждены' in note for note in p['warnings']))
        self.assertEqual(b['polygons'],[[2,0,1]])
        s=prepare_mesh(dict(body=dict(points_bits=points,mesh_wedges=[
            dict(vertex=2),dict(vertex=0),dict(vertex=1)],
            triangles=[dict(wedges=[1,2,0])])),'skeletal_mesh')
        self.assertEqual(s['polygons'],[[0,1,2]])

    def test_projection_basis_and_degenerate_scale(self):
        self.assertEqual(project([(1,2,3)],0,0),[(1,3,2)])
        p=project([(1,2,3)],math.pi/2,0)[0]
        self.assertAlmostEqual(p[0],-2);self.assertAlmostEqual(p[2],1)
        doc=mesh()
        for row in doc['vertices']:row['position_bits']=bits(1,1,1)
        self.assertTrue(all(p==(0,0,0) for p in prepare_mesh(doc,'static_mesh')['points']))

    def test_partial_model_geometry_displays_scope_warning(self):
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],status='partial',remaining_bytes=5)
        result=prepare_mesh(doc,'model')
        self.assertEqual(result['polygons'],[[0,1,2]])
        self.assertTrue(any('частичный' in note and '5 байт' in note for note in result['warnings']))
        doc['vertices'].append([9,-1])
        doc.update(remaining_bytes=100,invalid_unused_vertices=[dict(vertex=3,point=9,side=-1)])
        result=prepare_mesh(doc,'model')
        self.assertEqual(result['polygons'],[[0,1,2]])
        self.assertTrue(any('100 байт' in note and 'неверных записей вне диапазонов узлов: 1' in note
                            for note in result['warnings']))
        doc['vertices'][0][0]=9
        with self.assertRaises(ValueError):prepare_mesh(doc,'model')
        doc['vertices'][0][0]=0
        doc['status']='decoded'
        self.assertNotIn('warnings',prepare_mesh(doc,'model'))

    def test_empty_partial_model_keeps_scope_warning(self):
        doc=dict(points=[],vertices=[],nodes=[],status='partial',remaining_bytes=5,
                 invalid_unused_vertices=[dict(vertex=0,point=5,side=-1)])
        result=mesh_preview(doc,'model')
        self.assertIn('No drawable geometry',result['error'])
        self.assertTrue(any('частичный разбор' in note and
                            'неверных записей вне диапазонов узлов: 1' in note
                            for note in result['warnings']))
        self.assertTrue(any('игровое поведение коллизий не подтверждены' in note
                            for note in result['warnings']))

    def test_decoded_model_keeps_saved_data_scope_warning(self):
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],
                 status='decoded',profile=[133,40],
                 invalid_unused_vertices=[dict(vertex=3,point=9,side=-1)],
                 invalid_unlinked_hull_planes=[dict(hull=0,plane=0,word=4)])
        result=prepare_mesh(doc,'model')
        self.assertEqual(result['polygons'],[[0,1,2]])
        note=result['warnings'][0]
        self.assertIn('Сохранённая структура Model 133/40',note)
        self.assertIn('мировое размещение и игровая коллизия не подтверждены',note)
        self.assertIn('неверных записей вне диапазонов узлов: 1',note)
        self.assertIn('неверных плоскостей в hull без связи с узлами: 1',note)
        self.assertIn('Использование этих записей игрой не установлено',note)
        doc.update(points=[],vertices=[],nodes=[])
        self.assertIn('Сохранённая структура Model 133/40',
                      mesh_preview(doc,'model')['warnings'][0])

    def test_adjacent_model_profiles_keep_saved_data_scope_warning(self):
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],status='decoded')
        for version,licensee in ((127,39),(128,39),(130,40),(132,40)):
            with self.subTest(profile=(version,licensee)):
                doc['profile']=[version,licensee]
                note=prepare_mesh(doc,'model')['warnings'][0]
                self.assertIn(f'Model {version}/{licensee}',note)
                self.assertIn('только вариант с пустыми дополнительными массивами',note)
                self.assertIn('мировое размещение и игровая коллизия не подтверждены',note)
        doc['profile']=[129,39]
        self.assertNotIn('warnings',prepare_mesh(doc,'model'))

    def test_unverified_model_warns_for_assumed_and_opaque_data(self):
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],status='unverified',
                 profile=[129,39],remaining_bytes=2)
        result=prepare_mesh(doc,'model')
        self.assertEqual(result['polygons'],[[0,1,2]])
        self.assertIn('Непроверенная форма Model 129/39',result['warnings'][0])
        self.assertIn('предположительной схеме',result['warnings'][0])
        self.assertIn('нераспознанных байтов: 2',result['warnings'][0])
        self.assertIn('игровая коллизия не подтверждены',result['warnings'][0])
        opaque=dict(status='unverified',interpretation='opaque',profile=[132,40],
                    remaining_bytes=20,raw_preview_hex='0102')
        result=mesh_preview(opaque,'model')
        self.assertEqual(result['error'],'Геометрия не распознана')
        self.assertIn('ограниченный просмотр исходных байтов',result['warnings'][0])

    def test_model_frames_drawn_nodes_without_changing_saved_points(self):
        points=[bits(10000,0,0),bits(0,0,0),bits(1,0,0),
                bits(-10000,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[4,-1],[1,-1],[2,-1],[99,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],status='partial',remaining_bytes=5,
                 invalid_unused_vertices=[dict(vertex=3,point=99,side=-1)])
        before=deepcopy(doc)
        result=prepare_mesh(doc,'model')
        self.assertEqual(doc,before)
        self.assertEqual(result['polygons'],[[2,0,1]])
        self.assertEqual(result['edges'],[(0,1),(0,2),(1,2)])
        self.assertEqual(len(result['points']),3)
        self.assertEqual(result['bounds'],((0,0,0),(1,1,0)))
        self.assertEqual(result['source_point_count'],5)
        self.assertEqual(result['frame_point_count'],3)
        self.assertTrue(any('Точки вне отображаемых граней: 2' in note and
                            'остаются в данных' in note and
                            'использование игрой не установлено' in note
                            for note in result['warnings']))
        self.assertTrue(any('частичный разбор' in note for note in result['warnings']))
        self.assertTrue(any('неверных записей вне диапазонов узлов: 1' in note
                            for note in result['warnings']))

    def test_model_framing_keeps_strict_point_validation(self):
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0),bits(float('nan'),0,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)])
        with self.assertRaisesRegex(ValueError,'Non-finite'):
            prepare_mesh(doc,'model')
        doc['points'][3]=bits(100,0,0)
        doc['vertices'][1][0]=99
        with self.assertRaisesRegex(ValueError,'Invalid geometry polygon'):
            prepare_mesh(doc,'model')


class MeshGui(navigation.ResourceGuiTests):
    def setUp(self):
        super().setUp()
        w=self.window
        data=navigation.response()
        data['inventory']['candidates'].append(dict(id=5,path='Mesh',**{'class':'Engine.StaticMesh'}))
        w.clear_classes();w.loaded(data)
        original=w.core.request
        w.core.request=lambda **kw: {'result':mesh()} if kw['operation']=='static_mesh' else original(**kw)

    def test_render_orbit_source_and_cleanup(self):
        w=self.window;w.mode_tabs.setCurrentIndex(4);w.class_list.setCurrentRow(0);self.finish()
        view=w.mesh_view
        self.assertIs(w.viewer.currentWidget(),view)
        self.assertEqual(len(view.canvas.geometry['polygons']),2)
        view.resize(600,500);view.show()
        view.style.setCurrentIndex(1)
        image=view.grab().toImage()
        self.assertFalse(image.isNull())
        old=view.canvas.yaw
        QTest.mousePress(view.canvas,Qt.LeftButton,pos=QPoint(100,100))
        QTest.mouseMove(view.canvas,QPoint(140,120))
        QTest.mouseRelease(view.canvas,Qt.LeftButton,pos=QPoint(140,120))
        self.assertNotEqual(view.canvas.yaw,old)
        view.source.setCurrentIndex(1)
        self.assertFalse(view.source.isEnabled());self.finish()
        self.assertEqual(view.canvas.geometry['polygons'],[[0,1,3]])
        view.camera.setCurrentIndex(3)
        self.assertAlmostEqual(view.canvas.pitch,math.pi/2)
        w.mode_tabs.setCurrentIndex(0)
        self.assertIsNone(view.canvas.geometry)
        self.assertIsNone(view.document)

    def test_empty_collision_recovers(self):
        doc=mesh();doc['collision_faces']=[]
        w=self.window;w.core.request=lambda **kw:{'result':doc}
        w.mode_tabs.setCurrentIndex(4);w.class_list.setCurrentRow(0);self.finish()
        view=w.mesh_view;view.source.setCurrentIndex(1);self.finish()
        self.assertIsNone(view.canvas.geometry)
        self.assertIn('No drawable',view.info.text())
        view.source.setCurrentIndex(0);self.finish()
        self.assertIsNotNone(view.canvas.geometry)

    def test_partial_model_fallback_warns_in_mainwindow(self):
        w=self.window
        data=navigation.response()
        data['inventory']['candidates'].append(dict(id=8,path='Model',**{'class':'Engine.Model'}))
        w.clear_classes();w.loaded(data)
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],status='partial',remaining_bytes=5)
        calls=[]
        def request(**kw):
            calls.append(kw['operation'])
            if kw['operation']=='model':raise RuntimeError('Unsupported Model class/profile')
            if kw['operation']=='model_collision':return {'result':doc}
            raise AssertionError(kw)
        w.core.request=request
        w.mode_tabs.setCurrentIndex(4);w.class_list.setCurrentRow(0);self.finish()
        self.assertEqual(calls,['model','model_collision'])
        self.assertIs(w.viewer.currentWidget(),w.mesh_view)
        self.assertIn('частичный разбор',w.mesh_view.info.text())
        self.assertEqual(w.mesh_view.canvas.geometry['polygons'],[[0,1,2]])

    def test_opaque_model_shows_raw_preview_and_warning(self):
        w=self.window
        data=navigation.response()
        data['inventory']['candidates'].append(dict(id=8,path='Model',**{'class':'Engine.Model'}))
        w.clear_classes();w.loaded(data)
        doc=dict(status='unverified',interpretation='opaque',profile=[129,39],
                 remaining_bytes=2,raw_preview_hex='0102',reconstruction_supported=False)
        w.core.request=lambda **kw:{'result':doc}
        w.mode_tabs.setCurrentIndex(4);w.class_list.setCurrentRow(0);self.finish()
        self.assertIs(w.viewer.currentWidget(),w.resource_text)
        self.assertIn('Непроверенная форма Model',w.resource_text.toPlainText())
        self.assertIn('0102',w.resource_text.toPlainText())
        self.assertIn('Model не проверена',w.status_label.text())

    def test_unverified_model_draws_with_warning(self):
        w=self.window
        data=navigation.response()
        data['inventory']['candidates'].append(dict(id=8,path='Model',**{'class':'Engine.Model'}))
        w.clear_classes();w.loaded(data)
        points=[bits(0,0,0),bits(1,0,0),bits(0,1,0)]
        doc=dict(points=points,vertices=[[0,-1],[1,-1],[2,-1]],
                 nodes=[dict(vertex_pool=0,vertex_count=3)],status='unverified',
                 profile=[129,39],remaining_bytes=0)
        w.core.request=lambda **kw:{'result':doc}
        w.mode_tabs.setCurrentIndex(4);w.class_list.setCurrentRow(0);self.finish()
        self.assertIs(w.viewer.currentWidget(),w.mesh_view)
        self.assertEqual(w.mesh_view.canvas.geometry['polygons'],[[0,1,2]])
        self.assertIn('Непроверенная форма Model 129/39',w.mesh_view.info.text())
        self.assertIn('предположительной схеме',w.mesh_view.info.text())


if __name__=='__main__':unittest.main()
