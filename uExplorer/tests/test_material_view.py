"""Material cycles, missing references, read-only navigation and thumbnails."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_graph import prepare_material_graph,ResourceResolver
import test_resource_gui as navigation


class GraphCore:
    def request(self,**kw):
        if kw['operation']=='resource_inventory':
            return {'result':{'candidates':[
                dict(id=1,path='Shader',**{'class':'Engine.Shader'}),
                dict(id=2,path='Picture',**{'class':'Engine.Texture'})]}}
        if kw['object_id']==1:
            return {'result':dict(tags=[
                dict(name='Diffuse',kind=5,value=dict(id=2,path='Picture',**{'class':'Texture'})),
                dict(name='FallbackMaterial',kind=5,value=dict(id=1,path='Shader',**{'class':'Shader'})),
                dict(name='Opacity',kind=5,value=dict(id=-1,path='Missing.Picture',**{'class':'Texture'}))])}
        return {'result':dict(tags=[dict(name='Format',kind=1,value=5)],
                              mips=[dict(width=1,height=1,data_hex='0000ffff')])}


class Graph(unittest.TestCase):
    def test_cycle_deduplicated_and_missing_reference_retained(self):
        graph=prepare_material_graph(GraphCore(),'synthetic.utx',1)
        self.assertEqual(len(graph['nodes']),2)
        self.assertFalse(graph['truncated'])
        links=graph['nodes'][0]['links']
        self.assertEqual(links[0]['node'],1)
        self.assertEqual(links[1]['node'],0)
        self.assertIn('error',links[2])

    def test_external_package_resolution_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'Textures').mkdir();(root/'Animations').mkdir()
            (root/'Textures/Art.utx').write_bytes(b'fixture')
            reference=dict(id=-1,path='Art.Picture',**{'class':'Texture'})
            resolver=ResourceResolver(GraphCore())
            path,identifier=resolver.resolve(root/'Animations/Model.ukx',reference)
            self.assertEqual(identifier,2)
            self.assertEqual(Path(path).name,'Art.utx')
            (root/'Textures/Art.u').write_bytes(b'ambiguous')
            with self.assertRaises(ValueError):
                ResourceResolver(GraphCore()).resolve(root/'Animations/Model.ukx',reference)

    def test_systextures_search_and_sibling_ambiguity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('SysTextures','Textures','Animations'):(root/name).mkdir()
            (root/'SysTextures/Art.utx').write_bytes(b'fixture')
            reference=dict(id=-1,path='Art.Picture')
            path,identifier=ResourceResolver(GraphCore()).resolve(root/'Animations/Model.ukx',reference)
            self.assertEqual(Path(path).parent.name,'SysTextures')
            (root/'Textures/Art.utx').write_bytes(b'duplicate')
            with self.assertRaisesRegex(ValueError,'Ambiguous'):
                ResourceResolver(GraphCore()).resolve(root/'Animations/Model.ukx',reference)
            path,identifier=ResourceResolver(GraphCore(),[root/'SysTextures']).resolve(root/'Animations/Model.ukx',reference)
            self.assertEqual(Path(path).parent.name,'SysTextures')


class MaterialGui(navigation.ResourceGuiTests):
    def test_material_texture_link_navigation(self):
        w=self.window;w.core=GraphCore();data=navigation.response()
        data['package']['classes']=[]
        data['inventory']=w.core.request(operation='resource_inventory')['result']
        w.clear_classes();w.loaded(data);w.mode_tabs.setCurrentIndex(3)
        w.class_list.setCurrentRow(0);self.finish()
        view=w.material_view
        self.assertIs(w.viewer.currentWidget(),view)
        self.assertTrue(view.parameters.isReadOnly())
        view.nodes.setCurrentRow(1);self.finish()
        self.assertFalse(view.preview.pixmap().isNull())
        view.open_button.click();self.finish()
        self.assertEqual(w.mode,'textures')
        self.assertIsNotNone(w.texture_view)
