import io
import math
import os
from pathlib import Path
import struct
import sys
import unittest
import wave
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from audio_analysis import pcm_samples, spectrum, waveform
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QByteArray
from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat, QMediaPlayer
from PySide6.QtTest import QTest
from sound_view import SoundView


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application=QApplication.instance() or QApplication([])
    def test_fft_known_tone_and_silence(self):
        bins=spectrum([math.sin(2*math.pi*64*i/1024) for i in range(1024)])
        self.assertEqual(max(range(len(bins)),key=bins.__getitem__),64)
        self.assertGreater(bins[64],-.1)
        self.assertEqual(set(spectrum([0.]*1024)),{-80.})
        with self.assertRaises(ValueError):spectrum([0.],1000)
    def test_pcm_and_waveform_transient(self):
        self.assertEqual(pcm_samples(b'\0\x80\xff',1),[-1.,0.,127/128])
        self.assertEqual(pcm_samples(b'\0\0\x80',3),[-1.])
        self.assertEqual(pcm_samples(struct.pack('<f',float('nan')),4,floating=True),[0.])
        data=io.BytesIO()
        with wave.open(data,'wb') as output:
            output.setparams((1,2,8000,0,'NONE',''))
            output.writeframes(b'\0\0'*99+b'\xff\x7f'+b'\0\0'*100)
        overview=waveform(data.getvalue(),10)
        self.assertGreater(max(high for low,high in overview),.99)
    def test_controls_and_live_buffer(self):
        view=SoundView()
        try:
            self.assertFalse(view.play.isEnabled())
            fmt=QAudioFormat();fmt.setSampleRate(8192);fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.Int16)
            pcm=b''.join(struct.pack('<h',int(30000*math.sin(2*math.pi*64*i/1024))) for i in range(1024))
            buffer=QAudioBuffer(QByteArray(pcm),fmt)
            with patch.object(view.player,'playbackState',return_value=QMediaPlayer.PlayingState):
                view.audio_buffer(buffer)
            self.assertEqual(len(view.plot.levels),513)
            self.assertEqual(max(range(513),key=view.plot.levels.__getitem__),64)
            self.assertNotEqual(view.plot.history.pixelColor(511,119).name(),'#101820')
            view.volume.setValue(25);self.assertAlmostEqual(view.output.volume(),.25)
            view.mute.setChecked(True);self.assertTrue(view.output.isMuted())
            view.repeat.setChecked(True);self.assertEqual(view.player.loops(),QMediaPlayer.Infinite)
            view.visual.setCurrentIndex(2);self.assertEqual(view.plot.mode,2)
            view.stop();self.assertEqual(view.player.position(),0)
            view.clear();self.assertFalse(view.play.isEnabled());self.assertFalse(view.plot.wave)
        finally:
            view.clear();view.deleteLater();self.application.processEvents()

    def test_memory_play_pause_seek_stop(self):
        data=io.BytesIO()
        with wave.open(data,'wb') as output:
            output.setparams((1,2,8000,0,'NONE',''))
            output.writeframes(b''.join(struct.pack('<h',int(12000*math.sin(2*math.pi*440*i/8000)))
                                       for i in range(16000)))
        view=SoundView();view.mute.setChecked(True)
        try:
            view.load(data.getvalue(),waveform(data.getvalue()),'Synthetic tone')
            for _ in range(200):
                QTest.qWait(10)
                if view.player.duration():break
            self.assertEqual(view.player.duration(),2000)
            self.assertEqual(view.player.playbackState(),QMediaPlayer.StoppedState)
            view.toggle()
            for _ in range(500):
                QTest.qWait(10)
                if view.player.position()>0 and view.plot.levels:break
            self.assertEqual(view.player.error(),QMediaPlayer.NoError,view.player.errorString())
            self.assertGreater(view.player.position(),0,
                               f'{view.player.playbackState()} {view.player.mediaStatus()} '
                               f'FFT bins={len(view.plot.levels)}')
            self.assertTrue(view.plot.levels)
            view.toggle();self.assertEqual(view.player.playbackState(),QMediaPlayer.PausedState)
            view.position.setValue(1000);view.position.sliderReleased.emit()
            self.assertEqual(view.player.position(),1000)
            view.restart.click();self.assertEqual(view.player.position(),0)
            view.stop_button.click();self.assertEqual(view.player.playbackState(),QMediaPlayer.StoppedState)
        finally:
            view.clear();view.deleteLater();self.application.processEvents()


if __name__=='__main__':unittest.main()
