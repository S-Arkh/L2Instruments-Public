"""Synthetic pixel and asynchronous GUI checks; no client fixtures."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from texture_decode import decode_pixels, prepare_texture
import test_resource_gui as navigation
from test_resource_gui import FakeCore
import app


def texture():
    return dict(tags=[dict(name='Format', value=5)], mips=[
        dict(width=2, height=1, data_hex='0000ffff00ff0080'),
        dict(width=1, height=1, data_hex='ff0000ff')])


class Pixels(unittest.TestCase):
    def test_uncompressed(self):
        self.assertEqual(decode_pixels(bytes([1,2,3,4]),1,1,5), bytes([3,2,1,4]))
        self.assertEqual(decode_pixels(b'\xff\x7f',1,1,10), bytes([127,127,127,255]))
        palette=[[1,2,3,255]]*256
        self.assertEqual(decode_pixels(b'\0\1',2,1,0,palette,True),
                         bytes([1,2,3,0,1,2,3,255]))

    def test_dxt1_transparency_and_crop(self):
        block=struct.pack('<HHI',0,65535,0b11100100)
        pixels=decode_pixels(block,3,1,3)
        self.assertEqual(pixels,bytes([0,0,0,255,255,255,255,255,127,127,127,255]))
        self.assertEqual(decode_pixels(block,4,1,3)[12:],b'\0'*4)
        red=struct.pack('<HHI',0xf800,0,0)
        self.assertEqual(decode_pixels(red*2,5,1,3),bytes([255,0,0,255])*5)

    def test_dxt3_alpha(self):
        block=int('fedcba9876543210',16).to_bytes(8,'little')+struct.pack('<HHI',0xf800,0,0)
        pixels=decode_pixels(block,4,4,7)
        self.assertEqual(pixels[3::4],bytes(i*17 for i in range(16)))
        self.assertEqual(pixels[0::4],bytes([255])*16)

    def test_dxt5_both_alpha_modes(self):
        codes=sum((i%8)<<(3*i) for i in range(16)).to_bytes(6,'little')
        for endpoints,expected in [((255,0),[255,0,218,182,145,109,72,36]),
                                   ((0,255),[0,255,51,102,153,204,0,255])]:
            block=bytes(endpoints)+codes+struct.pack('<HHI',0xffff,0,0)
            self.assertEqual(decode_pixels(block,4,4,8)[3::4],bytes(expected*2))

    def test_reject_bad_storage_and_limits(self):
        for data,w,h,fmt in [(b'',1,1,5),(b'\0'*5,1,1,5),
                              (b'',0,1,3),(b'',8192,8192,3),(b'',1,1,99)]:
            with self.assertRaises(ValueError):decode_pixels(data,w,h,fmt)
        with self.assertRaises(ValueError):decode_pixels(b'\0',1,1,0,[[0]]*256)

    def test_face_failure_retains_mips(self):
        document=dict(tags=[dict(name='Faces',value=dict(id=2))])
        large=texture();large['mips'][0].update(width=8192,height=8192)
        core=FakeCore()
        with patch.object(core,'request',return_value={'result':large}):
            result=prepare_texture(core,'synthetic',document,face=0)
            self.assertIn('error',result)
            self.assertEqual(result['mip_sizes'],[(8192,8192),(1,1)])
            self.assertNotIn('error',prepare_texture(core,'synthetic',document,1,0))

    def test_external_cube_face_and_palette_use_target_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('Faces.utx','Colors.utx'):(root/name).write_bytes(b'fixture')
            calls=[]
            class Core:
                def request(self,**kw):
                    calls.append(kw)
                    if kw['operation']=='resource_inventory':
                        name='Face' if Path(kw['path']).stem=='Faces' else 'Palette'
                        return {'result':dict(candidates=[dict(id=1,path=name)])}
                    if kw['operation']=='texture':
                        return {'result':dict(tags=[dict(name='Format',value=0),
                            dict(name='Palette',value=dict(id=-1,path='Colors.Palette'))],
                            mips=[dict(width=1,height=1,data_hex='00')])}
                    return {'result':dict(colors=[[7,8,9,255]]*256)}
            cube=dict(tags=[dict(name='Faces',value=dict(id=-1,path='Faces.Face'))])
            result=prepare_texture(Core(),root/'Root.utx',cube,face=0)
            self.assertNotIn('error',result)
            self.assertEqual(result['pixels'],bytes([7,8,9,255]))
            self.assertEqual([Path(c['path']).name for c in calls if c['operation']=='palette'],['Colors.utx'])


class TextureGui(navigation.ResourceGuiTests):
    def setUp(self):
        super().setUp()
        original=self.window.core.request
        self.window.core.request=lambda **kw: (
            {'result':texture()} if kw['operation']=='texture' else original(**kw))

    # Inherited navigation tests use the original failing reader.
    def test_unsupported_and_failure_clear(self):
        self.window.core.request=FakeCore().request
        super().test_unsupported_and_failure_clear()

    def test_texture_mip_zoom_cleanup(self):
        w=self.window
        w.mode_tabs.setCurrentIndex(1);w.class_list.setCurrentRow(0);self.finish()
        view=w.texture_view
        self.assertIs(w.viewer.currentWidget(),view)
        self.assertEqual(view.canvas.item.pixmap().size().width(),2)
        view.actual.click();view.plus.click()
        self.assertAlmostEqual(view.canvas.transform().m11(),1.25)
        view.mip.setCurrentIndex(1)
        self.assertFalse(view.mip.isEnabled())
        self.finish()
        self.assertEqual(view.canvas.item.pixmap().toImage().pixelColor(0,0).getRgb(),(0,0,255,255))
        view.background.setCurrentIndex(2)
        self.assertEqual(view.canvas.background,2)
        w.mode_tabs.setCurrentIndex(0)
        self.assertIsNone(view.canvas.item)
        self.assertIsNone(view.document)

    def test_failed_mip_recovery(self):
        large=texture();large['mips'][0].update(width=8192,height=8192)
        self.window.core.request=lambda **kw:{'result':large}
        w=self.window;w.mode_tabs.setCurrentIndex(1);w.class_list.setCurrentRow(0);self.finish()
        view=w.texture_view
        self.assertIsNone(view.canvas.item)
        self.assertTrue(view.mip.isEnabled())
        view.mip.setCurrentIndex(1);self.finish()
        self.assertIsNotNone(view.canvas.item)

    def test_face_selection_and_external_error(self):
        cube=dict(tags=[dict(name='Faces',value=dict(id=2,path='Local')),
                        dict(name='Faces',subscript=1,value=dict(id=-1,path='External'))],mips=[])
        self.window.core.request=lambda **kw:{'result':cube if kw['object_id']==2 else texture()}
        # Root export is 2 in the synthetic inventory; local face uses export 3.
        cube['tags'][0]['value']['id']=3
        w=self.window;w.mode_tabs.setCurrentIndex(1);w.class_list.setCurrentRow(0);self.finish()
        view=w.texture_view
        self.assertIsNone(view.canvas.item)
        view.face.setCurrentIndex(1);self.finish()
        self.assertEqual(view.mip.count(),2)
        self.assertIsNotNone(view.canvas.item)
        view.face.setCurrentIndex(2);self.finish()
        self.assertIsNone(view.canvas.item)
        self.assertIn('external',view.info.text().lower())
        self.assertTrue(view.face.isEnabled())
        view.face.setCurrentIndex(1);self.finish()
        self.assertIsNotNone(view.canvas.item)


if __name__=='__main__':unittest.main()
