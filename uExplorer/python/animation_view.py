"""Timed skeletal and vertex animation; no autoplay or script event execution."""
import time
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QComboBox, QSlider, QCheckBox)
from mesh_view import MeshCanvas
from animation_decode import animation_pose, skeleton_geometry
from vertmesh_decode import vertex_geometry
from skinning import skin_geometry
from material_uv import has_timed_uv,timed_uv,timed_fragment_uv


class AnimationView(QWidget):
    requested = Signal(int)
    def __init__(self):
        super().__init__()
        self.document=None;self.prepared=None;self.position=0.;self.previous=0.
        layout=QVBoxLayout(self);controls=QHBoxLayout();layout.addLayout(controls)
        self.sequence=QComboBox();controls.addWidget(self.sequence,1)
        self.play=QPushButton('Воспроизвести');controls.addWidget(self.play)
        self.stop_button=QPushButton('Стоп');controls.addWidget(self.stop_button)
        self.repeat=QCheckBox('Повтор');controls.addWidget(self.repeat)
        self.speed=QComboBox()
        for speed in (.25,.5,1.,2.):self.speed.addItem(f'{speed:g}×',speed)
        self.speed.setCurrentIndex(2);controls.addWidget(self.speed)
        self.fit=QPushButton('Вписать');controls.addWidget(self.fit)
        self.style=QComboBox();self.style.addItems(['Каркас','Грани','Текстуры'])
        controls.addWidget(self.style)
        self.material_clock=QCheckBox('UV по времени клипа (диагностика)')
        self.material_clock.setChecked(True);self.material_clock.hide()
        layout.addWidget(self.material_clock)
        self.material_clock.toggled.connect(lambda _:self.render_pose())
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        self.canvas=MeshCanvas();layout.addWidget(self.canvas,1)
        self.canvas.graphicsUnavailable.connect(lambda message:self.info.setText(self.info.text()+'\n'+message))
        self.slider=QSlider(Qt.Horizontal);layout.addWidget(self.slider)
        self.clock=QLabel();layout.addWidget(self.clock)
        self.help=QLabel();layout.addWidget(self.help)
        self.operation='mesh_animation'
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick)
        self.sequence.currentIndexChanged.connect(self.select_sequence)
        self.play.clicked.connect(self.toggle);self.stop_button.clicked.connect(self.stop)
        self.slider.valueChanged.connect(self.seek)
        self.repeat.toggled.connect(lambda _:self.render_pose())
        self.fit.clicked.connect(self.canvas.reset_camera)
        self.style.currentIndexChanged.connect(self.set_style)
        self.set_loading(False)

    def set_loading(self, busy):
        if busy:self.pause()
        self.sequence.setEnabled(not busy and self.sequence.count()>0)
        for widget in (self.play,self.stop_button,self.slider):
            widget.setEnabled(not busy and self.prepared is not None)
        self.material_clock.setEnabled(not busy and self.prepared is not None and self.duration()<=3600)

    def hideEvent(self,event):
        self.pause()
        super().hideEvent(event)

    def pause(self):
        self.timer.stop();self.play.setText('Воспроизвести')

    def set_style(self,index):
        self.canvas.style=index;self.canvas.update()

    def clear(self):
        self.pause();self.document=None;self.prepared=None;self.position=0.
        self.material_clock.hide()
        self.canvas.clear();self.info.clear();self.clock.clear()
        self.sequence.blockSignals(True);self.sequence.clear();self.sequence.blockSignals(False)
        self.slider.blockSignals(True);self.slider.setRange(0,0);self.slider.blockSignals(False)
        self.set_loading(False)

    def load(self, document, operation='mesh_animation'):
        self.clear();self.document=document;self.operation=operation
        label=('VertMesh без материалов' if operation=='vert_mesh' else
               'Линейный skinning · diffuse-диагностика' if operation=='skinning' else 'Скелет без skinning')
        self.help.setText(label+' · ЛКМ: вращение · ПКМ: перемещение · колесо: масштаб')
        self.sequence.blockSignals(True)
        for i,sequence in enumerate(document['body']['sequences']):
            self.sequence.addItem(sequence['name'],i)
        if operation=='vert_mesh':
            self.sequence.addItem('Сохранённые кадры (диагностика, 30 кадров/с)',
                                  len(document['body']['sequences']))
        self.sequence.blockSignals(False)

    def select_sequence(self, index):
        if index<0 or self.document is None:return
        self.pause();self.prepared=None;self.canvas.clear();self.position=0.
        self.material_clock.hide()
        self.requested.emit(index)

    def display(self, prepared):
        self.pause();self.position=0.
        if 'error' in prepared:
            self.error(prepared['error']);return
        self.prepared=prepared
        self.slider.blockSignals(True)
        self.slider.setRange(0,max(1,round(prepared['frames']/prepared['rate']*1000)))
        self.slider.setValue(0);self.slider.blockSignals(False)
        count=(f'{prepared["vertices"]} вершин' if prepared.get('kind') in ('vert_mesh','skinning')
               else f'{len(prepared["parents"])} костей')
        self.info.setText(f'{prepared["name"]} · {count} · '
                          f'{prepared["frames"]} кадров · {prepared["rate"]:g} кадров/с')
        if prepared.get('warnings'):self.info.setText(self.info.text()+'\n'+'\n'.join(prepared['warnings']))
        animated=prepared.get('kind')=='skinning' and any(
            has_timed_uv(t) for t in prepared.get('textures',{}).values())
        self.material_clock.setVisible(animated)
        self.material_clock.setEnabled(self.duration()<=3600)
        if animated:
            self.info.setText(self.info.text()+('\nUV: время клипа, отдельная диагностика; не игровые часы'
                if self.duration()<=3600 else '\nUV: t=0; клип превышает предел времени материалов 3600 с'))
        self.canvas.display(dict(points=[],polygons=[],edges=[],textures=prepared.get('textures',{})))
        self.canvas.style=2 if prepared.get('textures') else 0
        self.style.blockSignals(True);self.style.setCurrentIndex(self.canvas.style);self.style.blockSignals(False)
        self.canvas.reset_camera();self.render_pose()

    def error(self, message):
        self.pause();self.prepared=None;self.canvas.clear();self.clock.clear()
        self.material_clock.hide()
        self.info.setText('Предпросмотр недоступен: '+message)
        self.set_loading(False)

    def duration(self):
        return self.prepared['frames']/self.prepared['rate'] if self.prepared else 0.

    def toggle(self):
        if not self.prepared:return
        if self.timer.isActive():self.pause();return
        if self.position>=self.duration():self.position=0.
        self.previous=time.monotonic();self.timer.start();self.play.setText('Пауза')

    def stop(self):
        self.pause();self.position=0.;self.render_pose()

    def seek(self, value):
        if not self.prepared:return
        self.position=value/1000;self.previous=time.monotonic();self.render_pose()

    def tick(self):
        if not self.prepared:self.pause();return
        now=time.monotonic()
        if not self.slider.isSliderDown():
            self.position+=(now-self.previous)*self.speed.currentData()
        self.previous=now
        if self.position>=self.duration():
            if self.repeat.isChecked():self.position%=self.duration()
            else:self.position=self.duration();self.pause()
        self.render_pose()

    def render_pose(self):
        if not self.prepared:return
        prepared=self.prepared
        if prepared.get('kind')=='skinning':
            self.canvas.geometry=skin_geometry(prepared,self.position,self.repeat.isChecked())
            if (self.material_clock.isChecked() and self.material_clock.isEnabled()
                    and any(has_timed_uv(t) for t in prepared.get('textures',{}).values())):
                seconds=max(0.,self.position)
                seconds=seconds%self.duration() if self.repeat.isChecked() else min(seconds,self.duration())
                try:
                    uv=timed_uv(prepared,seconds)
                    fragment=(timed_fragment_uv(prepared,seconds)
                              if 'uv_input' in prepared else None)
                    self.canvas.geometry['uv']=uv
                    if fragment is not None:self.canvas.geometry['fragment_uv']=fragment
                except ValueError as error:
                    self.pause();self.info.setText('Анимация UV недоступна: '+str(error))
        elif prepared.get('kind')=='vert_mesh':
            self.canvas.geometry=vertex_geometry(prepared,self.position,self.repeat.isChecked())
        else:
            points=animation_pose(prepared,self.position,self.repeat.isChecked())
            self.canvas.geometry=skeleton_geometry(points,prepared['parents'],prepared['names'],
                                                    prepared['center'],prepared['scale'])
        self.canvas.update()
        self.slider.blockSignals(True);self.slider.setValue(round(self.position*1000));self.slider.blockSignals(False)
        self.clock.setText(f'{self.position:.3f} / {self.duration():.3f} с')
