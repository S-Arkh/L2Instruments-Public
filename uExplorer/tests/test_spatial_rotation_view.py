"""Spatial cached-matrix gates and row-vector projection regressions."""
import copy
import unittest
from test_rotation_view import bits,fixture,stationary_fixture
from material_rotation import rotation_step
from material_rotation3d import spatial_animation,spatial_at,spatial_matrix,cached_precisions
from material_chain import chain_matrix
from material_uv import f32,timed_uv


def spatial_fixture():
    doc=fixture()
    doc['tags'][0]['words']=[1000,50,150]
    doc['tags'][1]['bits']=bits(70.)
    doc['tags']+=[
        dict(name='VOffset',bits=bits(20.)),
        dict(name='TexRotationType',value=2),
        dict(name='OscillationRate',words=[0,0,12000]),
        dict(name='OscillationAmplitude',words=[0,0,1000]),
        dict(name='OscillationPhase',words=[0,0,2000])]
    rows=((1.021572470664978,.012059464119374752,.09572699666023254,0.),
          (.006971174851059914,1.002907156944275,.0652294009923935,0.),
          (-.10350275039672852,-.07001979649066925,.9619966745376587,0.),
          (0.,0.,0.,1.))
    for plane,row in zip(doc['tags'][2]['members'],rows):
        for member,value in zip(plane['members'],row):member['bits']=bits(value)
    return doc,tuple(tuple(row[:3]) for row in rows[:3])


def double_spatial_fixture():
    doc=fixture();doc['tags'][0]['words']=[256,512,0]
    doc['tags'][1]['bits']=bits(0.)
    doc['tags'].append(dict(name='TexRotationType',value=1))
    matrix=((.9582323431968689,.25492045283317566,.12963896989822388),
            (-.2570899724960327,.9663874506950378,0.),
            (-.1252814680337906,-.03332887962460518,.991561233997345))
    rows=[(*row,0.) for row in matrix]+[(0.,0.,0.,1.)]
    for plane,row in zip(doc['tags'][2]['members'],rows):
        for member,value in zip(plane['members'],row):member['bits']=bits(value)
    return doc,matrix


class SpatialRotation(unittest.TestCase):
    def test_nonzero_phase_cached_components(self):
        doc,expected=spatial_fixture()
        animation=spatial_animation(doc,(256,256))
        self.assertEqual(cached_precisions(expected,(70/256,20/256)),['float32'])
        self.assertEqual(spatial_at(animation,658.9370727539062),expected)
        self.assertEqual(rotation_step(doc,(256,256))[0],'matrix_rotation')

    def test_all_stored_components_gate(self):
        original,_=spatial_fixture()
        for i in range(4):
            for j in range(4):
                doc=copy.deepcopy(original)
                doc['tags'][2]['members'][i]['members'][j]['bits']=bits(.125)
                with self.assertRaises(ValueError):rotation_step(doc,(256,256))

    def test_zero_amplitude_keeps_base_orientation(self):
        doc=fixture()
        doc['tags'][0]['words']=[1,53000,1]
        doc['tags']+=[dict(name='TexRotationType',value=2),
                      dict(name='OscillationRate',words=[1,0,0])]
        animation=spatial_animation(doc,(256,256))
        self.assertIn('fixed_matrix',animation)
        self.assertNotEqual(animation['fixed_matrix'],((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)))
        for time in (0,.25,3600):
            self.assertEqual(spatial_at(animation,time),animation['fixed_matrix'])
        for time in (-1,3601,float('nan'),float('inf')):
            with self.assertRaises(ValueError):spatial_at(animation,time)

    def test_fallback_retains_moving_precision_gates(self):
        doc=stationary_fixture();doc['tags'][0]['words']=[0,1,0]
        with self.assertRaises(ValueError):rotation_step(doc,(256,256))
        doc=fixture(True);doc['tags'].append(dict(name='TexRotationType',value=1))
        with self.assertRaises(ValueError):rotation_step(doc,(256,256))
        gimbal=spatial_matrix((16384,0,0),(0.,0.),'float32')
        self.assertEqual(cached_precisions(gimbal,(0.,0.)),[])

    def test_double_angle_spatial_power_of_two_velocities(self):
        doc,matrix=double_spatial_fixture()
        self.assertEqual(cached_precisions(matrix,(0.,0.)),['double'])
        animation=spatial_animation(doc,(256,256))
        self.assertEqual(animation['precision'],'double')
        self.assertEqual(spatial_at(animation,5.3),matrix)
        for velocity in (255,257,5000):
            doc['tags'][0]['words'][0]=velocity
            with self.assertRaisesRegex(ValueError,'ambiguous or unsupported'):
                spatial_animation(doc,(256,256))
        doc['tags'][0]['words'][0]=256
        doc['tags'][-1]['value']=2
        doc['tags'].append(dict(name='OscillationAmplitude',words=[4,0,0]))
        with self.assertRaisesRegex(ValueError,'ambiguous or unsupported'):
            spatial_animation(doc,(256,256))

    def test_double_angle_spatial_with_verified_pivot(self):
        doc,_=double_spatial_fixture()
        pivot=(.25,.125);matrix=spatial_matrix((1356,2713,0),pivot,'double')
        doc['tags'][1]['bits']=bits(64.)
        doc['tags'].append(dict(name='VOffset',bits=bits(32.)))
        for plane,row in zip(doc['tags'][2]['members'],
                             [(*row,0.) for row in matrix]+[(0.,0.,0.,1.)]):
            for member,value in zip(plane['members'],row):member['bits']=bits(value)
        animation=spatial_animation(doc,(256,256))
        self.assertEqual(animation['precision'],'double')
        self.assertEqual(spatial_at(animation,5.3),matrix)

    def test_double_spatial_noninvariant_clock_is_explicit_preview(self):
        doc,matrix=double_spatial_fixture()
        doc['tags'][0]['words'][0]=255
        with self.assertRaisesRegex(ValueError,'ambiguous or unsupported'):
            spatial_animation(doc,(256,256))
        animation=spatial_animation(doc,(256,256),preview_precision=True)
        self.assertTrue(animation['preview_approximate'])
        self.assertEqual(animation['precision'],'double')
        step=rotation_step(doc,(256,256),preview_precision=True)
        self.assertEqual(step[0],'matrix_rotation')
        self.assertTrue(step[1]['preview_approximate'])
        self.assertEqual(spatial_at(animation,0),spatial_matrix((0,0,0),(0.,0.),'double'))
        self.assertNotEqual(spatial_at(animation,5.3),matrix)
        # An invalid saved matrix cannot be admitted merely by requesting preview.
        doc['tags'][2]['members'][3]['members'][3]['bits']=bits(.5)
        with self.assertRaises(ValueError):rotation_step(doc,(256,256),preview_precision=True)

    def test_exact_precision_search_and_candidate_budget(self):
        pivot=tuple(map(f32,(-74108.47142016896,95598.80307095882)))
        matrix=spatial_matrix((40324,35956,40296),pivot,'float32')
        matches=cached_precisions(matrix,pivot)
        self.assertEqual(matches,['float32'])
        matches.clear()
        self.assertEqual(cached_precisions(matrix,pivot),['float32'])
        pivot=tuple(map(f32,(-6964.1107592200715,-85037.88217286934)))
        matrix=spatial_matrix((49192,20120,23020),pivot,'float32')
        with self.assertRaisesRegex(ValueError,'candidate budget'):
            cached_precisions(matrix,pivot)

    def test_z_coupling_order_projection_and_rewind(self):
        # Two quarter turns around pitch: dropping Z between stages would
        # erase U. A perspective divide would negate V as well.
        quarter=((0.,0.,1.),(0.,1.,0.),(-1.,0.,0.))
        step=('matrix_rotation',dict(fixed_matrix=quarter))
        matrix=chain_matrix((step,step),0)
        self.assertEqual(matrix,((-1.,0.,0.),(0.,1.,0.),(0.,0.,-1.)))
        geometry=dict(uv=[[(99.,99.)]],uv_base=[[(.25,.75)]],
                      face_materials=[0],textures={0:dict(uv_chain=(step,step))})
        self.assertEqual(timed_uv(geometry,0),[[(-.25,.75)]])
        pan=('panner',(.5,(1.,0.)))
        self.assertNotEqual(chain_matrix((step,pan),1),chain_matrix((pan,step),1))
        doc,_=spatial_fixture()
        geometry['textures'][0]['uv_chain']=(rotation_step(doc,(256,256)),pan)
        start=timed_uv(geometry,0);later=timed_uv(geometry,17)
        self.assertNotEqual(start,later)
        geometry['uv']=later
        self.assertEqual(timed_uv(geometry,0),start)
        self.assertEqual(timed_uv(geometry,17),later)


if __name__=='__main__':unittest.main()
