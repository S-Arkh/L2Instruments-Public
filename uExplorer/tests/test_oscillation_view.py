import sys
from pathlib import Path
import unittest
import struct
import math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from material_oscillation import oscillator_at,oscillator_parameters,verified_oscillator_parameters
from material_uv import f32
from material_uv import timed_uv
from material_math import shared_grid
from material_surface import diffuse


class Oscillation(unittest.TestCase):
    def test_stretch_and_pivot_matrix_holdouts(self):
        time=1652.3177490234375
        axes=((0,f32(.2),0.,f32(.0125)),(1,f32(.1),0.,f32(.0125)))
        self.assertEqual(oscillator_at(axes,time),
                         ((1.,1.0124181509017944),(.0028368968050926924,0.)))
        axes=((1,f32(.05),0.,f32(.2),.5),(1,f32(.1),0.,f32(.1),.5))
        self.assertEqual(oscillator_at(axes,time),
                         ((.8669002652168274,1.0993455648422241),
                          (.0665498673915863,-.04967278242111206)))
        axes=((0,.125,1.,f32(.05),.5),(0,f32(.05),1.,f32(.005),.5))
        self.assertEqual(oscillator_at(axes,time)[1],
                         (-.012348830699920654,-.003327488899230957))

    def test_original_size_pivot(self):
        bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        doc=dict(tags=[dict(name='UOffset',bits=bits(256.))])
        self.assertEqual(oscillator_parameters(doc,(512,1024))[0][4],.5)
        with self.assertRaisesRegex(ValueError,'original texture'):
            oscillator_parameters(doc)

    def test_nonzero_phase_saved_matrix(self):
        axis=(0,f32(.11),f32(.1),f32(.1))
        self.assertEqual(oscillator_at((axis,axis),658.9370727539062)[1],
                         (-.04986101761460304,-.04986101761460304))

    def test_saved_pan_matrix_calibration(self):
        axes=((0,f32(.1),0.,f32(.1)),(0,f32(.15),0.,f32(.1)))
        self.assertEqual(oscillator_at(axes,3067.29541015625),
                         ((1.,1.),(-.09917590022087097,.05585957691073418)))

    def test_defaults_and_absolute_time(self):
        axes=oscillator_parameters({'tags':[]})
        self.assertEqual(oscillator_at(axes,0),((1.,1.),(0.,0.)))
        before=oscillator_at(axes,.25)
        oscillator_at(axes,2.75)
        self.assertEqual(oscillator_at(axes,.25),before)
        self.assertEqual(before[1],(f32(.1),f32(.1)))
        for time in (-1,3601,float('nan')):
            with self.assertRaises(ValueError):oscillator_at(axes,time)

    def test_stateful_mode_rejected(self):
        for axis in ('U','V'):
            with self.assertRaisesRegex(ValueError,'random state'):
                verified_oscillator_parameters({'tags':[
                    {'name':axis+'OscillationType','value':3},
                    {'name':axis+'OscillationAmplitude','bits':0}]})
        with self.assertRaisesRegex(ValueError,'random state'):
            oscillator_at(((3,1.,0.,0.),(0,1.,0.,0.)),.5)
        with self.assertRaisesRegex(ValueError,'random state'):
            oscillator_at(((3,1.,0.,0.),(0,1.,0.,0.)),.5,preview_repeat=True)
        # A zero-amplitude jitter may still carry a nonzero saved value
        # until its next state transition.
        bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        with self.assertRaisesRegex(ValueError,'random state'):
            verified_oscillator_parameters({'tags':[
                dict(name='UOscillationType',value=3),
                dict(name='UOscillationAmplitude',bits=bits(0.)),
                dict(name='CurrentUJitter',bits=bits(.02))]})

    def test_triggered_fallback_never_claims_exact_uv(self):
        for kind in ('TexOscillatorTriggered','TexPannerTriggered'):
            class Resolver:
                dependencies=[]
                def resolve(self,path,ref):return path,ref['id']
                def read(self,path,identifier,budget=None):
                    if identifier==1:
                        return dict(path='Triggered',**{'class':kind}),dict(tags=[
                            dict(name='Material',value=dict(id=2,**{'class':'Texture'}))])
                    return dict(path='Image',**{'class':'Texture'}),dict(
                        tags=[dict(name='Format',value=5)],
                        mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
            result=diffuse(None,Resolver(),'fixture',dict(id=1))
            self.assertFalse(result['uv0_exact'])
            self.assertTrue(any(kind in note and 'без эффектов' in note for note in result['notes']))
            self.assertNotIn('uv_oscillation',result)
            self.assertNotIn('uv_pan_rate',result)
            with self.assertRaisesRegex(ValueError,'supported matching UV'):
                shared_grid([result])

    def test_zero_amplitude_stretch_repeat_is_time_invariant(self):
        bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        doc={'tags':[dict(name='UOscillationType',value=2),
                     dict(name='UOscillationAmplitude',bits=bits(-0.)),
                     dict(name='UOscillationRate',bits=bits(-7.5)),
                     dict(name='UOscillationPhase',bits=bits(.375)),
                     dict(name='UOffset',bits=bits(128.)),
                     dict(name='VOscillationAmplitude',bits=bits(0.))]}
        axes=verified_oscillator_parameters(doc,(256,256))
        for time in (0,.125,.5,1.,999.75,3600.,0.):
            self.assertEqual(oscillator_at(axes,time),((1.,1.),(0.,0.)))
        for value in (1.,-1.,2**-149):
            doc['tags'][1]['bits']=bits(value)
            with self.assertRaisesRegex(ValueError,'nonzero stretch-repeat'):
                verified_oscillator_parameters(doc,(256,256))
            with self.assertRaisesRegex(ValueError,'nonzero stretch-repeat'):
                oscillator_at(((2,1.,0.,value),(0,1.,0.,0.)),.5)
        doc['tags'][1]['bits']=bits(0.)
        doc['tags'].append(dict(name='VOscillationType',value=3))
        with self.assertRaisesRegex(ValueError,'random state'):
            verified_oscillator_parameters(doc,(256,256))

    def test_zero_repeat_direct_surface_and_stateful_fallback(self):
        bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        doc=dict(tags=[dict(name='Material',value=dict(id=2,**{'class':'Texture'})),
                       dict(name='UOscillationType',value=2),
                       dict(name='UOscillationAmplitude',bits=bits(0.))])
        class Resolver:
            dependencies=[]
            def resolve(self,path,ref):return path,ref['id']
            def read(self,path,identifier,budget=None):
                if identifier==1:return dict(path='Osc',**{'class':'TexOscillator'}),doc
                return dict(path='Image',**{'class':'Texture'}),dict(tags=[dict(name='Format',value=5)],
                    mips=[dict(width=2,height=1,data_hex='0000ffff00ff00ff')])
        surface=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertEqual(surface['uv_oscillation'][0][0],2)
        doc['tags'][-1]['bits']=bits(.01)
        preview=diffuse(None,Resolver(),'fixture',dict(id=1))
        self.assertTrue(preview['uv_preview_approximate'])
        self.assertTrue(preview['uv_oscillation_preview'])
        self.assertFalse(preview['uv0_exact'])
        self.assertFalse(preview['uv_coordinate_exact'])
        self.assertTrue(any('приблизительная' in note for note in preview['notes']))
        with self.assertRaisesRegex(ValueError,'supported matching UV'):
            shared_grid([preview])
        geometry=dict(uv_base=[[(.25,.5)]],face_materials=[0],textures={0:preview})
        start=timed_uv(geometry,0)
        self.assertNotEqual(timed_uv(geometry,.5),start)
        self.assertEqual(timed_uv(geometry,0),start)
        doc['tags'][-1]['bits']=bits(0.)
        doc['tags'][1]['value']=3
        with self.assertRaisesRegex(ValueError,'random state'):
            diffuse(None,Resolver(),'fixture',dict(id=1))

    def test_repeat_preview_saved_holdouts_and_unverified_precision(self):
        zero=(0,1.,0.,0.)
        # Different saved package clocks are independently corroborated by
        # six or 29 panners. These are not measured game clocks.
        for axis,time,expected in (
                ((2,1.,0.,f32(.3)),3089.6494140625,1.2556476593017578),
                ((2,f32(.1),3.,f32(.1)),3089.6494140625,1.0998483896255493),
                ((2,2.,f32(.1),f32(.1)),2689.3583984375,1.098321795463562),
                ((2,2.,f32(.1),f32(.1)),247.52291870117188,1.064446210861206)):
            axes=(axis,zero)
            with self.assertRaisesRegex(ValueError,'nonzero stretch-repeat'):
                oscillator_at(axes,time)
            self.assertEqual(oscillator_at(axes,time,preview_repeat=True)[0][0],expected)
        # Saved scales at those clocks do not settle angle precision elsewhere.
        axes=((2,1.,0.,f32(.3)),zero)
        single=oscillator_at(axes,.5,preview_repeat=True)[0][0]
        double=f32(1.+f32(math.sin(.5*math.pi/2)*f32(.3)))
        self.assertNotEqual(single,double)

    def test_repeat_preview_wrap_phase_pivot_and_rewind(self):
        axes=((2,-1.,f32(.1),f32(.5),.25),(0,1.,0.,0.))
        first=oscillator_at(axes,.25,preview_repeat=True)
        fraction=.75
        angle=f32(fraction*f32(math.pi/2)+f32(.1)*f32(math.tau))
        scale=f32(1.+f32(math.sin(angle)*f32(.5)))
        offset=f32(f32(f32(-.25*scale))+.25)
        self.assertEqual(first,((scale,1.),(offset,0.)))
        self.assertEqual(oscillator_at(axes,1.25,preview_repeat=True),first)
        self.assertNotEqual(oscillator_at(axes,1.,preview_repeat=True),first)
        self.assertEqual(oscillator_at(axes,.25,preview_repeat=True),first)
        for time in (-1.,3601.,float('nan')):
            with self.assertRaises(ValueError):oscillator_at(axes,time,preview_repeat=True)

    def test_stationary_zero_phase_repeat_with_nonzero_amplitude(self):
        bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        doc={'tags':[dict(name='UOscillationType',value=2),
                     dict(name='UOscillationAmplitude',bits=bits(.5)),
                     dict(name='UOscillationRate',bits=bits(-0.)),
                     dict(name='UOscillationPhase',bits=bits(0.)),
                     dict(name='UOffset',bits=bits(128.)),
                     dict(name='VOscillationAmplitude',bits=bits(0.))]}
        axes=verified_oscillator_parameters(doc,(256,256))
        for time in (0.,2**-149,.025,.25,1.,3600.,0.):
            self.assertEqual(oscillator_at(axes,time),((1.,1.),(0.,0.)))
        for name,value in (('UOscillationRate',2**-149),
                           ('UOscillationRate',1.),
                           ('UOscillationPhase',2**-149),
                           ('UOscillationPhase',.25)):
            changed={'tags':[dict(tag) for tag in doc['tags']]}
            next(tag for tag in changed['tags'] if tag['name']==name)['bits']=bits(value)
            with self.assertRaisesRegex(ValueError,'nonzero stretch-repeat'):
                verified_oscillator_parameters(changed,(256,256))
        for axes in (((2,0.,.25,.5),(0,1.,0.,0.)),
                     ((2,2**-149,0.,.5),(0,1.,0.,0.))):
            with self.assertRaisesRegex(ValueError,'nonzero stretch-repeat'):
                oscillator_at(axes,1.)

    def test_uv_rewind_and_composition_gate(self):
        axes=oscillator_parameters({'tags':[]})
        surface=dict(width=2,height=2,uv_oscillation=axes)
        geometry=dict(uv_base=[[(.2,.3)]],uv=[[(99.,99.)]],
                      face_materials=[0],textures={0:surface})
        first=timed_uv(geometry,.25)
        geometry['uv']=first
        self.assertEqual(timed_uv(geometry,.25),first)
        self.assertEqual(timed_uv(geometry,0),geometry['uv_base'])
        self.assertEqual(shared_grid([surface,surface])['uv_oscillation'],axes)
        with self.assertRaisesRegex(ValueError,'oscillations'):
            shared_grid([surface,dict(width=2,height=2)])
