"""Read-only in-memory audio player and live FFT display."""
from PySide6.QtCore import Qt, QBuffer, QByteArray, QIODevice, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QSlider, QLabel, QCheckBox, QComboBox)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioFormat
try:
    from PySide6.QtMultimedia import QAudioBufferOutput
except ImportError:
    QAudioBufferOutput = None
from audio_analysis import pcm_samples, spectrum


class AudioPlot(QWidget):
    seek = Signal(float)
    def __init__(self):
        super().__init__(); self.setMinimumHeight(180)
        self.mode = 0; self.wave = []; self.levels = []; self.position = 0.
        self.rate = 0; self.history = QImage(512, 128, QImage.Format_RGB32)
        self.history.fill(QColor('#101820'))
    def reset(self):
        self.wave = []; self.levels = []; self.position = 0.; self.rate = 0
        self.history.fill(QColor('#101820')); self.update()
    def feed(self, values, rate):
        self.levels = spectrum(values); self.rate = rate
        shifted = self.history.copy(1, 0, 511, 128)
        painter = QPainter(self.history); painter.drawImage(0, 0, shifted); painter.end()
        for y in range(128):
            start = y*len(self.levels)//128; end = max(start+1, (y+1)*len(self.levels)//128)
            value = (max(self.levels[start:end])+80)/80
            self.history.setPixelColor(511, 127-y, QColor.fromHsvF((1-value)*0.68, 1., max(.08, value)))
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self); painter.fillRect(self.rect(), QColor('#101820'))
        width, height = self.width(), max(1, self.height()-24)
        painter.setPen(QPen(QColor('#52d5bb'), 1))
        if self.mode == 0 and self.wave:
            for i, (low, high) in enumerate(self.wave):
                x = int(i*width/len(self.wave))
                painter.drawLine(x, int((1-high)*height/2), x, int((1-low)*height/2))
            painter.setPen(QColor('#ffffff'))
            x = int(self.position*max(0,width-1)); painter.drawLine(x,0,x,height)
        elif self.mode == 1 and self.levels:
            for i, value in enumerate(self.levels):
                x = int(i*width/len(self.levels))
                painter.drawLine(x,height,x,int(-value*height/80))
        elif self.mode == 2:
            painter.drawImage(self.rect().adjusted(0,0,0,-24), self.history)
        painter.setPen(QColor('#ffffff'))
        label = ('Волна · первый канал · щелчок для перехода' if self.mode == 0 else
                 f'FFT · первый канал · 0–{self.rate//2} Гц · −80…0 dBFS' if self.mode == 1 else
                 f'Спектрограмма · частота ↑ 0–{self.rate//2} Гц · время →')
        if self.mode == 0 and not self.wave: label = 'Обзор волны недоступен для этого кодека'
        painter.drawText(6,self.height()-6,label)
    def mousePressEvent(self, event):
        if self.mode == 0 and event.button() == Qt.LeftButton:
            self.seek.emit(max(0.,min(1.,event.position().x()/max(1,self.width()))))


class SoundView(QWidget):
    def __init__(self):
        super().__init__(); self.buffer = None
        self.player = QMediaPlayer(self); self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        layout = QVBoxLayout(self)
        self.info = QLabel(); self.info.setWordWrap(True); layout.addWidget(self.info)
        self.plot = AudioPlot(); layout.addWidget(self.plot,1)
        self.visual = QComboBox(); self.visual.addItems(['Звуковая волна','Спектр FFT','Спектрограмма'])
        self.visual.currentIndexChanged.connect(self.set_visual); layout.addWidget(self.visual)
        controls = QHBoxLayout(); layout.addLayout(controls)
        self.play = QPushButton('Воспроизвести'); self.play.clicked.connect(self.toggle)
        self.stop_button = QPushButton('Стоп'); self.stop_button.clicked.connect(self.stop)
        self.restart = QPushButton('Сначала'); self.restart.clicked.connect(lambda:self.player.setPosition(0))
        for button in (self.play,self.stop_button,self.restart): controls.addWidget(button)
        self.repeat = QCheckBox('Повтор'); self.repeat.toggled.connect(
            lambda enabled:self.player.setLoops(QMediaPlayer.Infinite if enabled else QMediaPlayer.Once))
        controls.addWidget(self.repeat)
        self.position = QSlider(Qt.Horizontal); self.position.setRange(0,0)
        self.position.sliderReleased.connect(lambda:self.player.setPosition(self.position.value()))
        layout.addWidget(self.position)
        self.time = QLabel('0:00 / 0:00'); layout.addWidget(self.time)
        volume = QHBoxLayout(); layout.addLayout(volume); volume.addWidget(QLabel('Громкость'))
        self.volume = QSlider(Qt.Horizontal); self.volume.setRange(0,100); self.volume.setValue(70)
        self.output.setVolume(.7); self.volume.valueChanged.connect(lambda v:self.output.setVolume(v/100))
        volume.addWidget(self.volume)
        self.mute = QCheckBox('Без звука'); self.mute.toggled.connect(self.output.setMuted); volume.addWidget(self.mute)
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda duration:self.position.setMaximum(duration))
        self.player.errorOccurred.connect(lambda error,message:self.info.setText('Не удалось воспроизвести: '+message))
        self.plot.seek.connect(lambda fraction:self.player.setPosition(int(fraction*self.player.duration())))
        self.analysis = QAudioBufferOutput(self) if QAudioBufferOutput else None
        if self.analysis:
            self.player.setAudioBufferOutput(self.analysis); self.analysis.audioBufferReceived.connect(self.audio_buffer)
        else:
            self.visual.setItemText(1,'FFT требует Qt 6.8+')
            self.visual.setItemText(2,'Спектрограмма требует Qt 6.8+')
        self.set_controls(False)
    def set_controls(self, enabled):
        for widget in (self.play,self.stop_button,self.restart,self.position):
            widget.setEnabled(enabled)
    def set_visual(self, mode):
        self.plot.mode=mode;self.plot.update()
    def clear(self):
        self.player.stop(); self.player.setSource(QUrl())
        if self.buffer:
            self.buffer.close();self.buffer.deleteLater();self.buffer=None
        self.plot.reset();self.info.clear();self.position.setRange(0,0)
        self.time.setText('0:00 / 0:00');self.set_controls(False)
    def load(self, audio, overview, name):
        self.clear()
        if len(audio)>64*1024*1024:raise ValueError('Audio preview exceeds 64 MiB')
        self.buffer=QBuffer(self);self.buffer.setData(QByteArray(audio));self.buffer.open(QIODevice.ReadOnly)
        self.plot.wave=overview;self.plot.update();self.info.setText(name+' · только прослушивание')
        self.player.setSourceDevice(self.buffer,QUrl('resource.wav'));self.set_controls(True)
    def toggle(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause()
        else:self.player.play()
    def stop(self):
        self.player.stop();self.player.setPosition(0);self.position_changed(0)
        self.plot.levels=[];self.plot.history.fill(QColor('#101820'));self.plot.update()
    def state_changed(self, state):
        self.play.setText('Пауза' if state==QMediaPlayer.PlayingState else 'Воспроизвести')
    def position_changed(self, position):
        if not self.position.isSliderDown():self.position.setValue(position)
        def clock(ms):return f'{ms//60000}:{ms//1000%60:02d}'
        self.time.setText(clock(position)+' / '+clock(self.player.duration()))
        self.plot.position=position/max(1,self.player.duration());self.plot.update()
    def audio_buffer(self, buffer):
        if not buffer.isValid() or self.player.playbackState()!=QMediaPlayer.PlayingState:return
        fmt=buffer.format()
        widths={QAudioFormat.UInt8:1,QAudioFormat.Int16:2,QAudioFormat.Int32:4,QAudioFormat.Float:4}
        width=widths.get(fmt.sampleFormat())
        if not width:return
        raw=bytes(buffer.constData())[:buffer.byteCount()]
        stride=width*fmt.channelCount()
        values=pcm_samples(raw[-1024*stride:],width,fmt.channelCount(),fmt.sampleFormat()==QAudioFormat.Float)
        self.plot.feed(values,fmt.sampleRate())
