"""Manually inspect saved AnimNext links without reconstructing game timing."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_frames import (MAX_FRAME_BYTES,has_saved_next,select_material_frame,
                             select_saved_frame,selectable_samplers)
from material_graph import ResourceResolver
from material_math import shared_grid
from material_surface import diffuse
from material_uv import timed_fragment_uv
from textured_mesh import prepare_textured
from test_coordinate_source_view import mesh
from test_isolated_sampler_view import direct_combiner_fixture,fixture as shader_isolated_fixture
from test_panner_combiner_view import fixture as combiner_fixture
from test_shader_modifier_view import FixtureCore


def animated_combiner_fixture():
    documents=combiner_fixture()
    documents[3][2]['tags'].append(dict(name='AnimNext',
        value=dict(id=5,path='FirstNext',**{'class':'Texture'})))
    documents[4][2]['tags'].append(dict(name='AnimNext',
        value=dict(id=7,path='SecondNext',**{'class':'Texture'})))
    documents[5]=('Texture','FirstNext',dict(tags=[
        dict(name='Format',value=5),
        dict(name='AnimNext',value=dict(id=6,path='FirstLast',**{'class':'Texture'}))],
        mips=[dict(width=2,height=1,data_hex='ff0000ffff0000ff')]))
    documents[6]=('Texture','FirstLast',dict(tags=[dict(name='Format',value=5)],
        mips=[dict(width=2,height=1,data_hex='ffffffffffffffff')]))
    documents[7]=('Texture','SecondNext',dict(tags=[dict(name='Format',value=5)],
        mips=[dict(width=1,height=1,data_hex='ffffffff')]))
    return documents


class SavedMaterialFrames(unittest.TestCase):
    def surface(self,documents):
        core=FixtureCore(documents);resolver=ResourceResolver(core)
        return core,resolver,diffuse(core,resolver,'Fixture.utx',dict(id=1))

    def test_manual_frame_changes_only_selected_sampler(self):
        documents=animated_combiner_fixture();original=copy.deepcopy(documents)
        core,resolver,surface=self.surface(documents)
        self.assertEqual(selectable_samplers(surface),[0,1])
        first=select_material_frame(core,resolver,surface,0,1)
        self.assertEqual(first['fragment_layers'][0]['pixels'],bytes.fromhex('0000ffff0000ffff'))
        self.assertEqual(first['fragment_layers'][1]['pixels'],surface['fragment_layers'][1]['pixels'])
        self.assertEqual(first['fragment_layers'][2]['pixels'],first['fragment_layers'][0]['pixels'])
        self.assertEqual(first['pixels'],first['fragment_layers'][0]['pixels'])
        second=select_material_frame(core,resolver,surface,1,1)
        self.assertEqual(second['fragment_layers'][0]['pixels'],surface['fragment_layers'][0]['pixels'])
        self.assertEqual(second['fragment_layers'][1]['pixels'],b'\xff'*4)
        self.assertEqual(second['pixels'],surface['pixels'])
        self.assertTrue(any('только сохранённый кадр' in note and 'игровая частота' in note
                            and 'частота просмотра задаётся пользователем' in note for note in second['notes']))
        self.assertEqual(select_material_frame(core,resolver,surface,0,0)['pixels'],surface['pixels'])
        self.assertEqual(select_material_frame(core,resolver,surface,0,2)['pixels'],b'\xff'*8)
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([first])
        self.assertEqual(documents,original)

    def test_mesh_selection_preserves_diagnostic_uv_and_other_slot(self):
        documents=animated_combiner_fixture();core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            base=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                  overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)})
            frame=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                   overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)},
                                   frame_selection=(0,1,1))
        self.assertNotIn('error',frame)
        self.assertEqual(frame['frame_selection'],(0,1,1))
        self.assertEqual(frame['textures'][0]['fragment_layers'][1]['pixels'],b'\xff'*4)
        self.assertEqual(frame['textures'][1]['fragment_layers'][1]['pixels'],
                         base['textures'][1]['fragment_layers'][1]['pixels'])
        self.assertEqual(timed_fragment_uv(frame,1.),timed_fragment_uv(base,1.))
        self.assertTrue(any('Шаг AnimNext (диагностика)' in note for note in frame['warnings']))

    def test_isolated_snapshot_allows_only_its_single_sampler(self):
        for factory in (direct_combiner_fixture,shader_isolated_fixture):
            documents=factory()
            documents[8][2]['tags'].append(dict(name='AnimNext',
                value=dict(id=10,path='Next',**{'class':'Texture'})))
            documents[10]=('Texture','Next',dict(tags=[dict(name='Format',value=5)],
                mips=[dict(width=2,height=1,data_hex='ff0000ffff0000ff')]))
            with self.subTest(factory=factory.__name__):
                core,resolver,surface=self.surface(documents)
                self.assertEqual(selectable_samplers(surface),[0])
                result=select_material_frame(core,resolver,surface,0,1)
                self.assertTrue(result['uv_snapshot'] and result['uv_preview_approximate'])
                self.assertEqual(result['pixels'],bytes.fromhex('0000ffff0000ffff'))
                self.assertEqual(result['uv_rotation'],surface['uv_rotation'])
                with self.assertRaises(ValueError):select_material_frame(core,resolver,surface,1,1)
                with self.assertRaises(ValueError):shared_grid([result])

    def test_invalid_links_cycles_dimensions_and_bounds_are_rejected(self):
        changes=('missing','duplicate','invalid_id','bad_class','bad_path','cycle',
                 'dimensions','missing_mip','duplicate_mip','invalid_pixels')
        for change in changes:
            documents=animated_combiner_fixture()
            core,resolver,surface=self.surface(documents)
            frame=documents[5][2]
            if change=='missing':frame['tags'].pop()
            elif change=='duplicate':frame['tags'].append(copy.deepcopy(frame['tags'][-1]))
            elif change=='invalid_id':frame['tags'][-1]['value']['id']=True
            elif change=='bad_class':frame['tags'][-1]['value']['class']='Shader'
            elif change=='bad_path':frame['tags'][-1]['value']['path']='Wrong'
            elif change=='cycle':frame['tags'][-1]['value']=dict(id=3,path='First',**{'class':'Texture'})
            elif change=='dimensions':documents[6][2]['mips'][0]['width']=1
            elif change=='missing_mip':documents[6][2]['mips']=[]
            elif change=='duplicate_mip':documents[6][2]['mips'].append(copy.deepcopy(documents[6][2]['mips'][0]))
            else:documents[6][2]['mips'][0]['data_hex']='00'
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)):
                select_saved_frame(core,resolver,surface['fragment_layers'][0],2)
        core,resolver,surface=self.surface(animated_combiner_fixture())
        for step in (-1,32,True,1.5):
            with self.subTest(step=step),self.assertRaises(ValueError):
                select_saved_frame(core,resolver,surface['fragment_layers'][0],step)
        with self.assertRaisesRegex(ValueError,'ended before'):
            select_saved_frame(core,resolver,surface['fragment_layers'][1],2)

    def test_bad_request_keeps_original_and_explains_fallback(self):
        documents=animated_combiner_fixture();core=FixtureCore(documents)
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            geometry=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                      overrides={0:('Fixture.utx',1),1:('Fixture.utx',1)},
                                      frame_selection=(0,1,2))
        self.assertNotIn('error',geometry)
        self.assertTrue(any('кадр не выбран' in note and 'исходный кадр' in note
                            for note in geometry['warnings']))
        self.assertNotIn('saved_frame_step',geometry['textures'][0]['fragment_layers'][1])
        with patch('textured_mesh.ResourceResolver',return_value=ResourceResolver(core)):
            invalid=prepare_textured(core,'Fixture.utx',mesh(),'static_mesh',
                                     overrides={0:('Fixture.utx',1)},frame_selection=(0,True,1))
        self.assertIn('error',invalid)

    def test_malformed_root_does_not_claim_a_selectable_sequence(self):
        doc=animated_combiner_fixture()[3][2]
        self.assertTrue(has_saved_next(doc))
        doc['tags'].append(copy.deepcopy(doc['tags'][-1]))
        self.assertFalse(has_saved_next(doc))

    def test_chain_read_budget_is_cumulative(self):
        core,resolver,surface=self.surface(animated_combiner_fixture())
        layer=surface['fragment_layers'][0]
        candidates=resolver.inventory(layer['saved_frame_root'][0])['candidates']
        for entry in candidates:
            if entry['id']==3:entry['serial_bytes']=MAX_FRAME_BYTES-1
            elif entry['id']==5:entry['serial_bytes']=2
        with self.assertRaisesRegex(ValueError,'budget'):
            select_saved_frame(core,resolver,layer,1)

    def test_frame_uses_the_matching_saved_mip_without_resampling(self):
        documents=animated_combiner_fixture()
        documents[5][2]['mips'].insert(0,dict(width=4,height=2,data_hex='00'*32))
        core,resolver,surface=self.surface(documents)
        layer=dict(surface['fragment_layers'][0],native_size=(4,2))
        selected=select_saved_frame(core,resolver,layer,1)
        self.assertEqual((selected['width'],selected['height']),(2,1))
        self.assertEqual(selected['pixels'],bytes.fromhex('0000ffff0000ffff'))


if __name__=='__main__':unittest.main()
