"""Native float32 phase wrapping and explicit diagnostic UV time lifecycle."""
import copy
import math
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_uv import f32,panner_offset,panner_rate,panner_direction,panner_preview_parameters,timed_uv
from material_math import shared_grid
from material_surface import diffuse
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from mesh_view import MeshView


def document(rate=1.):
    return dict(tags=[dict(name='PanRate',bits=struct.unpack('<I',struct.pack('<f',rate))[0]),
                      dict(name='Material',value=dict(id=2,**{'class':'Texture'}))])


class Panner(unittest.TestCase):
    def test_native_phase_wrap_and_float32_boundary(self):
        self.assertEqual(panner_offset(.25,1),.25)
        self.assertEqual(panner_offset(-.25,1),1023.75)
        self.assertEqual(panner_offset(1024,1),0.)
        self.assertEqual(panner_offset(1024,1.5),512.)
        self.assertEqual(panner_offset(1024,1-2**-26),0.)  # time rounds to float32 1
        for time in (-1,3601,float('nan'),float('inf')):
            with self.assertRaises(ValueError):panner_offset(1,time)
        for rate in (float('nan'),float('inf'),10001):
            with self.assertRaises(ValueError):panner_offset(rate,1)

    def test_direction_and_coordinate_rejections(self):
        d=document();d['tags'].append(dict(name='PanDirection',words=[0,0,0]))
        self.assertEqual(panner_rate(d),1.)
        for words in ([10000,5000,4],[],[0,0]):
            d['tags'][-1]['words']=words
            with self.assertRaises(ValueError):panner_rate(d)
        d=document();d['tags'].append(dict(name='TexCoordSource',value=8))
        with self.assertRaises(ValueError):panner_rate(d)
        with self.assertRaises(ValueError):panner_rate(document(float('nan')))

    def test_subquantum_roll_is_identical_to_zero_only(self):
        doc=document(.7)
        doc['tags'].append(dict(name='PanDirection',words=[10000,5000,0]))
        expected=panner_direction(doc)
        for roll in (1,2,3,65536,65539,0xffff0003):
            doc['tags'][-1]['words'][2]=roll
            self.assertEqual(panner_direction(doc),expected)
        for roll in (4,65532,65535,0xffffffff):
            doc['tags'][-1]['words'][2]=roll
            with self.assertRaisesRegex(ValueError,'precision-invariant'):
                panner_direction(doc)

    def test_nonzero_roll_requires_invariant_direction_and_power_of_two_rate(self):
        doc=document(1.)
        doc['tags'].append(dict(name='PanDirection',words=[61440,8192,32768]))
        expected=(.6532814502716064,.6532814502716064)
        self.assertEqual(panner_direction(doc),expected)
        for seconds,expected_offset in ((.25,.1633203625679016),
                                        (1.,.6532814502716064),
                                        (2.,1.306562900543213)):
            self.assertEqual(tuple(panner_offset(1.,seconds,c) for c in expected),
                             (expected_offset,expected_offset))
        for rate in (1.,2.,-4.,8192.):
            doc['tags'][0]['bits']=struct.unpack('<I',struct.pack('<f',rate))[0]
            self.assertEqual(panner_direction(doc),expected)
            for seconds in (0.,2**-149,.125,1.,443.8770446777344,3600.):
                for component in expected:
                    # Independent extended-distance path has no float32
                    # store between rate*time and directional multiplication.
                    phase=f32(f32(rate)*f32(seconds)*component/1024)
                    self.assertEqual(panner_offset(rate,seconds,component),
                                     f32((phase-math.floor(phase))*1024))
        for rate in (.5,.1,3.,10000.):
            doc['tags'][0]['bits']=struct.unpack('<I',struct.pack('<f',rate))[0]
            with self.assertRaisesRegex(ValueError,'precision-invariant'):
                panner_direction(doc)
        doc['tags'][0]['bits']=struct.unpack('<I',struct.pack('<f',1.))[0]
        doc['tags'][-1]['words']=[10000,5000,32768]
        with self.assertRaisesRegex(ValueError,'precision-invariant'):
            panner_direction(doc)

    def test_stationary_nonzero_roll_ignores_ambiguous_direction(self):
        doc=document(0.)
        doc['tags'].append(dict(name='PanDirection',words=[10000,5000,32768]))
        for rate in (0.,-0.):
            doc['tags'][0]['bits']=struct.unpack('<I',struct.pack('<f',rate))[0]
            direction=panner_direction(doc)
            self.assertEqual(panner_rate(doc),0.)
            for seconds in (0.,2**-149,.025,1.,3600.):
                self.assertEqual(tuple(panner_offset(rate,seconds,c) for c in direction),(0.,0.))
        for rate in (2**-149,-2**-149,.1):
            doc['tags'][0]['bits']=struct.unpack('<I',struct.pack('<f',rate))[0]
            with self.assertRaisesRegex(ValueError,'precision-invariant'):
                panner_direction(doc)

    def test_noninvariant_roll_is_explicitly_approximate_and_cannot_compose(self):
        doc=document(.1)
        doc['tags'].append(dict(name='PanDirection',words=[10000,10000,10000]))
        with self.assertRaisesRegex(ValueError,'precision-invariant'):
            panner_rate(doc)
        rate,direction,approximate=panner_preview_parameters(doc)
        self.assertTrue(approximate)
        # Korean and Japanese cached matrices, at separately inferred clocks;
        # High Five produces a different result even for this same model.
        self.assertEqual(tuple(panner_offset(rate,1239.849365234375,c) for c in direction),
                         (40.928855895996094,58.30428695678711))
        self.assertEqual(tuple(panner_offset(rate,1132.159912109375,c) for c in direction),
                         (37.3739013671875,53.24016189575195))
        self.assertNotEqual(tuple(panner_offset(rate,510.6790771484375,c) for c in direction),
                            (16.85810661315918,24.01483917236328))
        class Resolver:
            dependencies=[]
            def resolve(self,path,ref):return path,ref['id']
            def read(self,path,identifier,budget=None):
                if identifier==1:return dict(path='Pan',**{'class':'TexPanner'}),doc
                return dict(path='Image',**{'class':'Texture'}),dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
        result=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertTrue(result['uv_preview_approximate'])
        self.assertFalse(result['uv_coordinate_exact'])
        self.assertTrue(any('приблизительная' in note for note in result['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([result])
        doc['tags'].append(dict(name='TexCoordProjected',value=True))
        with self.assertRaisesRegex(ValueError,'unprojected'):
            panner_preview_parameters(doc)

    def test_yaw_quantization_wrap_and_cardinal_rounding(self):
        def direction(yaw):
            d=document();d['tags'].append(dict(name='PanDirection',words=[0,yaw,0]))
            return panner_direction(d)
        self.assertEqual(direction(0),(1.,0.))
        self.assertEqual(direction(49152),(0.,-1.))
        self.assertEqual(direction(65536),direction(0))
        self.assertEqual(direction(16000),direction(16003))
        self.assertNotEqual(direction(16000),direction(16004))
        self.assertEqual(direction(0xffffffff),direction(65535))
        x,y=direction(16384)
        self.assertLess(x,0.)
        self.assertEqual(y,1.)
        self.assertEqual(panner_offset(.5,1,x),1024.)
        for value in (float('nan'),float('inf'),1.01):
            with self.assertRaises(ValueError):panner_offset(1,1,value)

    def test_pitched_saved_translation_holdouts(self):
        for pitch,yaw,rate,expected in (
                (12288,0,.6000000238418579,(151.2985382080078,0.)),
                (10000,5000,.699999988079071,(235.14512634277344,122.23058319091797)),
                (32768,52500,.550000011920929,(909.6572875976562,343.90496826171875))):
            doc=document(rate);doc['tags'].append(dict(name='PanDirection',words=[pitch,yaw,0]))
            direction=panner_direction(doc)
            self.assertEqual(tuple(panner_offset(rate,658.9370727539062,c) for c in direction),expected)
            doc['tags'][-1]['words'][0]+=3
            self.assertEqual(panner_direction(doc),direction)
            doc['tags'][-1]['words'][0]+=65533
            self.assertEqual(panner_direction(doc),direction)

    def test_pitched_time_rewinds_immutable_uv(self):
        doc=document();doc['tags'].append(dict(name='PanDirection',words=[10000,5000,0]))
        geometry=dict(uv_base=[[(.25,.5)]],uv=[[(99.,99.)]],face_materials=[0],
                      textures={0:dict(uv_pan_rate=.5,uv_pan_direction=panner_direction(doc))})
        moved=timed_uv(geometry,2)
        self.assertNotEqual(moved,geometry['uv_base'])
        geometry['uv']=moved
        self.assertEqual(timed_uv(geometry,0),geometry['uv_base'])
        self.assertEqual(timed_uv(geometry,2),moved)

    def test_vertical_time_and_composition_direction_validation(self):
        texture=dict(width=2,height=1,pixels=b'\xff'*8,uv_pan_rate=.25,
                     uv_pan_direction=(0.,-1.))
        geometry=dict(uv=[[(.25,.5)]*3],face_materials=[0],textures={0:texture})
        self.assertEqual(timed_uv(geometry,2),[[(.25,1024.)]*3])
        with self.assertRaisesRegex(ValueError,'directions'):
            shared_grid([texture,dict(texture,uv_pan_direction=(1.,0.))])

    def test_distance_is_rounded_before_direction_multiplication(self):
        self.assertEqual(panner_offset(.10000000149011612,31.420978546142578,
                                        .9238795042037964),2.9029200077056885)
        self.assertEqual(panner_offset(.44999998807907104,3067.29541015625,
                                        -.7911693453788757),955.96240234375)

    def test_direct_texture_and_matching_animation_grids(self):
        d=document()
        class Resolver:
            dependencies=[]
            def resolve(self,path,ref):return path,ref['id']
            def read(self,path,identifier,budget=None):
                if identifier==1:return dict(path='Pan',**{'class':'TexPanner'}),d
                return dict(path='Image',**{'class':'Texture'}),dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
        result=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertEqual(result['uv_pan_rate'],1.)
        self.assertTrue(result['uv0_exact'])
        with self.assertRaisesRegex(ValueError,'animation rates'):
            shared_grid([result,dict(result,uv_pan_rate=2.)])
        d['tags'][1]['value']['class']='TexScaler'
        with self.assertRaisesRegex(ValueError,'direct Texture'):
            diffuse(None,Resolver(),'fixture',dict(id=1))

    def test_uv_time_is_absolute_and_preserves_inputs(self):
        geometry=dict(uv=[[(.25,.5)]*3],face_materials=[0],
                      textures={0:dict(uv_pan_rate=.25)})
        original=copy.deepcopy(geometry)
        self.assertEqual(timed_uv(geometry,1),[[(.5,.5)]*3])
        self.assertEqual(timed_uv(geometry,2),[[(.75,.5)]*3])
        self.assertEqual(geometry,original)

    def test_mesh_clock_stops_on_clear_hide_and_loading(self):
        app=QApplication.instance() or QApplication([])
        view=MeshView()
        geometry=dict(points=[(0,0,0),(1,0,0),(0,1,0)],polygons=[[0,1,2]],edges=[],bounds=[],
            uv=[[(0.,0.)]*3],face_materials=[0],
            textures={0:dict(width=1,height=1,pixels=b'\xff'*4,uv_pan_rate=.25)})
        try:
            view.show();view.display(geometry)
            view.uv_time.setValue(2)
            self.assertEqual(view.canvas.geometry['uv'],[[(.5,0.)]*3])
            self.assertEqual(geometry['uv'],[[(0.,0.)]*3])
            view.uv_play.setChecked(True);QTest.qWait(80)
            self.assertGreater(view.uv_time.value(),2)
            view.set_loading(True);self.assertFalse(view.uv_timer.isActive())
            view.set_loading(False);view.uv_play.setChecked(True)
            view.hide();self.assertFalse(view.uv_timer.isActive())
            view.show();view.uv_play.setChecked(True);view.clear()
            self.assertFalse(view.uv_timer.isActive())
        finally:view.close();app.processEvents()


if __name__=='__main__':unittest.main()
