"""Stored fixed-rotation evidence and rejection of unsupported transforms."""
import copy
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_rotation import (fixed_rotation,animated_rotation,rotation_at,rotation_matrix,
                               invariant_constant_velocity,rotation_step,direction)
from material_uv import f32,timed_uv
from material_math import shared_grid
from material_surface import diffuse


def bits(value):
    return struct.unpack('<I',struct.pack('<f',value))[0]


def fixture(double=False):
    c,s,x,y=(.3606105148792267,-.9327164888381958,
             -.07492845505475998,-.10930271446704865) if double else (
             .3606105446815491,-.9327163696289062,
             -.07492844760417938,-.10930269956588745)
    rows=[[c,s,0.,0.],[-s,c,0.,0.],[x,y,1.,0.],[0.,0.,0.,1.]]
    return dict(tags=[dict(name='Rotation',words=[0,53000,0]),
                      dict(name='UOffset',bits=bits(-30.)),
                      dict(name='M',members=[
                          dict(name=name,members=[dict(name=a,bits=bits(v))
                               for a,v in zip(('X','Y','Z','W'),row)])
                          for name,row in zip(('XPlane','YPlane','ZPlane','WPlane'),rows)])])


def stationary_fixture():
    doc=fixture()
    doc['tags'][0]['words']=[0,0,0]
    doc['tags'].append(dict(name='TexRotationType',value=1))
    for i,plane in enumerate(doc['tags'][2]['members']):
        for j,member in enumerate(plane['members']):
            member['bits']=bits(float(i==j))
    doc['tags'].append(dict(name='OscillationRate',words=[2000,0,0]))
    return doc


class Rotation(unittest.TestCase):
    def test_fixed_subquantum_pitch_roll_require_full_matrix(self):
        original=fixed_rotation(fixture(),(256,256))
        for value in (1,3,65536,65539):
            doc=fixture();doc['tags'][0]['words'][0]=value;doc['tags'][0]['words'][2]=value
            self.assertEqual(fixed_rotation(doc,(256,256)),original)
            doc['tags'].append(dict(name='TexRotationType',value=1))
            with self.assertRaisesRegex(ValueError,'Pitch/Roll'):
                animated_rotation(doc,(256,256))
        for value in (4,0xffffffff):
            doc=fixture();doc['tags'][0]['words'][0]=value
            with self.assertRaises(ValueError):fixed_rotation(doc,(256,256))

    def test_stationary_constant_is_precision_invariant(self):
        # Irrelevant oscillation parameters must not turn constant mode into
        # oscillation or affect its zero angular velocity.
        doc=stationary_fixture()
        animation=animated_rotation(doc,(256,256))
        self.assertEqual(animation['precision'],'invariant')
        for time in (0,.25,658.9370727539062,3600):
            self.assertEqual(rotation_at(animation,time),((1.,0.,0.,1.),(0.,0.)))
        moving=copy.deepcopy(doc);moving['tags'][0]['words'][1]=1
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            animated_rotation(moving,(256,256))
        for i in range(4):
            for j in range(4):
                bad=copy.deepcopy(doc)
                bad['tags'][2]['members'][i]['members'][j]['bits']=bits(.125)
                with self.assertRaisesRegex(ValueError,'identity'):
                    animated_rotation(bad,(256,256))

    def test_pivot_dot_rounding_regression(self):
        c,s=.7378527522087097,.6749616861343384
        self.assertEqual(rotation_matrix(c,s,(.48828125,.48828125))[2][:2],
                         [.45757272839546204,-.2015695571899414])
        self.assertEqual(rotation_matrix(c,s,(.48828125,.09765625))[2][:2],
                         [.19391584396362305,-.3039708137512207])

    def test_constant_and_oscillating_cache_calibration(self):
        constant=dict(mode=1,yaw=12288,rate=0,amplitude=0,
                      pivot=(.48828125,.09765625),precision='float32')
        rotation,offset=rotation_at(constant,3067.29541015625)
        self.assertEqual(rotation[:2],(.7378527522087097,.6749616861343384))
        self.assertEqual(offset,(.19391584396362305,-.3039708137512207))
        oscillating=dict(mode=2,yaw=0,rate=1500,amplitude=2500,
                         pivot=(0.,0.),precision='float32')
        self.assertEqual(rotation_at(oscillating,3067.29541015625)[0][:2],
                         (.9735566973686218,.22844547033309937))
        for seconds in (-1,3601,float('nan')):
            with self.assertRaises(ValueError):rotation_at(constant,seconds)

    def test_animation_precision_gate_and_absolute_time(self):
        doc=fixture()
        doc['tags'].append(dict(name='TexRotationType',value=1))
        animation=animated_rotation(doc,(256,256))
        self.assertEqual(animation['precision'],'float32')
        geometry=dict(uv=[[(99.,99.)]],uv_base=[[(.2,.7)]],face_materials=[0],
                      textures={0:dict(uv_rotation_animation=animation)})
        first=timed_uv(geometry,2)
        geometry['uv']=first
        self.assertEqual(timed_uv(geometry,2),first)
        self.assertEqual(timed_uv(geometry,0),geometry['uv_base'])
        double=fixture(True);double['tags'].append(dict(name='TexRotationType',value=1))
        with self.assertRaisesRegex(ValueError,'double-angle'):
            animated_rotation(double,(256,256))

    def test_double_angle_constant_power_of_two_velocity(self):
        double=fixture(True)
        double['tags'][0]['words']=[0,256,0]
        double['tags'].append(dict(name='TexRotationType',value=1))
        animation=animated_rotation(double,(256,256))
        self.assertEqual(animation['precision'],'double')
        fixed=fixed_rotation(fixture(True),(256,256))
        self.assertEqual(rotation_at(animation,207.03125),fixed[:2])
        for velocity in (255,257,10000,53000):
            double['tags'][0]['words'][1]=velocity
            with self.assertRaisesRegex(ValueError,'double-angle'):
                animated_rotation(double,(256,256))
        time=f32(.01)
        self.assertNotEqual(int(f32(10000*time))>>2,int(10000*time)>>2)
        for velocity in (-65536,-512,-1,0,1,256,512,65536):
            self.assertTrue(invariant_constant_velocity((velocity,)))
            for seconds in (0.,2**-149,.01,1.,207.03125,3600.):
                self.assertEqual(int(f32(velocity*f32(seconds))),int(velocity*f32(seconds)))
        double['tags'][0]['words'][1]=256
        double['tags'][-1]['value']=2
        with self.assertRaisesRegex(ValueError,'double-angle'):
            animated_rotation(double,(256,256))

    def test_unverified_double_clock_is_marked_preview_and_cannot_compose(self):
        doc=fixture(True)
        doc['tags'][1]['bits']=bits(0.)
        rows=rotation_matrix(*direction(53000,'double'),(0.,0.))
        for plane,row in zip(doc['tags'][2]['members'],rows):
            for member,value in zip(plane['members'],row):member['bits']=bits(value)
        doc['tags'] += [dict(name='TexRotationType',value=1),
                        dict(name='Material',value=dict(id=2,**{'class':'Texture'}))]
        with self.assertRaises(ValueError):rotation_step(doc,(2,1))
        kind,animation=rotation_step(doc,(2,1),preview_precision=True)
        self.assertEqual(kind,'rotation')
        self.assertTrue(animation['preview_approximate'])
        self.assertEqual(animation['precision'],'double')
        # Both products fit the saved instant but choose different table
        # indices at another time. Do not silently call either exact.
        t=f32(.02)
        self.assertNotEqual(direction(int(f32(53000*t)),'double'),
                            direction(int(53000*t),'double'))
        class Resolver:
            dependencies=[]
            def resolve(self,path,ref):return path,ref['id']
            def read(self,path,identifier,budget=None):
                if identifier==1:return dict(path='Rot',**{'class':'TexRotator'}),doc
                return dict(path='Image',**{'class':'Texture'}),dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
        surface=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertTrue(surface['uv_preview_approximate'])
        self.assertFalse(surface['uv_coordinate_exact'])
        self.assertTrue(any('TexRotator: приблизительная' in note for note in surface['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):shared_grid([surface])
        bad=copy.deepcopy(doc);bad['tags'][2]['members'][0]['members'][0]['bits']=bits(.12345)
        with self.assertRaises(ValueError):rotation_step(bad,(2,1),preview_precision=True)

    def test_cardinal_cache_does_not_silently_choose_a_table(self):
        doc=stationary_fixture();doc['tags'][0]['words'][1]=1
        with self.assertRaises(ValueError):rotation_step(doc,(256,256))
        kind,animation=rotation_step(doc,(256,256),preview_precision=True)
        self.assertEqual(kind,'rotation')
        self.assertTrue(animation['preview_approximate'])
        self.assertEqual(animation['precision'],'float32')

    def test_two_stored_precision_variants_and_original_dimensions(self):
        for double in (False,True):
            doc=fixture(double)
            rotation,offset,precision=fixed_rotation(doc,(256,256))
            self.assertEqual(precision,'double' if double else 'float32')
            self.assertLess(rotation[1],0.)
            self.assertLess(offset[0],0.)
            with self.assertRaises(ValueError):fixed_rotation(doc,(128,128))

    def test_full_matrix_gate(self):
        base=fixture()
        for plane in range(4):
            for field in range(4):
                doc=copy.deepcopy(base)
                doc['tags'][2]['members'][plane]['members'][field]['bits']=bits(.125)
                with self.assertRaises(ValueError):fixed_rotation(doc,(256,256))
        with self.assertRaises(ValueError):fixed_rotation(dict(tags=[]),(256,256))

    def test_reject_animated_nonplanar_and_unverified_pivot(self):
        for tag in (dict(name='TexRotationType',value=1),
                    dict(name='VOffset',bits=bits(1.)),
                    dict(name='VOffset',bits=bits(float('nan')))):
            doc=fixture();doc['tags'].append(tag)
            with self.assertRaises(ValueError):fixed_rotation(doc,(256,256))
        doc=fixture();doc['tags'][0]['words'][0]=4
        with self.assertRaises(ValueError):fixed_rotation(doc,(256,256))

    def test_composition_preserves_rotation_and_rejects_mismatch(self):
        rotation,offset,_=fixed_rotation(fixture(),(256,256))
        surface=dict(width=2,height=2,uv_rotation=rotation,uv_offset=offset)
        self.assertEqual(shared_grid([surface,surface])['uv_rotation'],rotation)
        with self.assertRaisesRegex(ValueError,'rotations'):
            shared_grid([surface,dict(surface,uv_rotation=(1.,0.,0.,1.))])


if __name__=='__main__':unittest.main()
