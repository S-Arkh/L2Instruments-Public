"""Read-only orthographic diagnostic mesh viewer using Qt's raster painter."""
import math
import os
from PySide6.QtCore import Qt, QPointF, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QImage, QBrush, QTransform
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QComboBox, QDoubleSpinBox, QSpinBox)
from PySide6.QtCore import Signal
from mesh_decode import project


class MeshCanvas(QWidget):
    graphicsUnavailable=Signal(str)
    def __init__(self):
        super().__init__()
        self.setMinimumSize(240, 180)
        self.geometry = None; self.style = 0; self.last = None;self.textures={};self.gpu=None;self.gpu_failed=False
        self.material_states={};self.texture_wrap={}
        self.material_base=None
        self.reset_camera()

    def reset_camera(self):
        self.yaw = math.radians(35); self.pitch = math.radians(25)
        self.zoom = 1.; self.pan = QPointF(); self.update()

    def update(self,*args):
        if self.gpu:
            active=self.style==2 and self.geometry is not None and not self.gpu_failed
            self.gpu.setVisible(active)
            if active:self.gpu.update()
        super().update(*args)

    def resizeEvent(self,event):
        if self.gpu:self.gpu.setGeometry(self.rect())
        super().resizeEvent(event)

    def enable_gpu(self):
        if self.gpu is None and not self.gpu_failed and os.environ.get('QT_QPA_PLATFORM') not in ('offscreen','minimal'):
            try:
                from mesh_gl import GLCanvas
                self.gpu=GLCanvas(self);self.gpu.setGeometry(self.rect())
            except (ImportError,OSError) as error:
                self.gpu_failed=True;self.graphicsUnavailable.emit('OpenGL недоступен; Qt raster: '+str(error))
        self.update()

    def clear(self):
        if self.gpu and self.gpu.isValid():self.gpu.release()
        self.geometry = None; self.last = None;self.textures={}; self.reset_camera()
        self.material_base=None
        self.material_states={};self.texture_wrap={}

    def display(self, geometry):
        self.material_base=geometry
        self.geometry = dict(geometry)
        self.material_states={slot:t['render_state'] for slot,t in geometry.get('textures',{}).items()
                              if 'render_state' in t}
        self.texture_wrap={slot:t.get('wrap',(0,0)) for slot,t in geometry.get('textures',{}).items()}
        self.textures={slot:QImage(t['pixels'],t['width'],t['height'],t['width']*4,QImage.Format_RGBA8888).copy()
                       for slot,t in geometry.get('textures',{}).items()}
        if self.textures:self.enable_gpu()
        self.reset_camera()

    def material_time(self,seconds):
        if self.material_base is None:return
        from material_uv import timed_uv,timed_fragment_uv
        uv=timed_uv(self.material_base,seconds)
        fragment=(timed_fragment_uv(self.material_base,seconds)
                  if 'uv_input' in self.material_base else None)
        self.geometry['uv']=uv
        if fragment is not None:self.geometry['fragment_uv']=fragment
        self.update()

    def camera(self, index):
        self.yaw, self.pitch = [(math.radians(35),math.radians(25)),
                               (0.,0.),(math.pi/2,0.),(0.,math.pi/2)][index]
        self.zoom = 1.; self.pan = QPointF(); self.update()

    def wheelEvent(self, event):
        self.zoom = max(.05,min(40.,self.zoom*(1.2 if event.angleDelta().y()>0 else 1/1.2)))
        self.update(); event.accept()

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton, Qt.RightButton):
            self.last = event.position(); event.accept()

    def mouseMoveEvent(self, event):
        if self.last is None:return
        delta = event.position()-self.last; self.last = event.position()
        if event.buttons() & Qt.LeftButton:
            self.yaw += delta.x()*.01
            self.pitch = max(-math.pi/2,min(math.pi/2,self.pitch+delta.y()*.01))
        else:
            self.pan += delta
        self.update(); event.accept()

    def mouseReleaseEvent(self, event):
        self.last = None

    def paintEvent(self, event):
        painter = QPainter(self); painter.fillRect(self.rect(),QColor('#182129'))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor('#d6e4ed'))
        if not self.geometry:
            painter.drawText(self.rect(),Qt.AlignCenter,'Нет геометрии для просмотра');return
        projected = project(self.geometry['points'],self.yaw,self.pitch)
        scale = min(self.width(),self.height())*.28*self.zoom
        origin = QPointF(self.width()/2,self.height()/2)+self.pan
        screen = [QPointF(origin.x()+x*scale,origin.y()-y*scale) for x,y,z in projected]
        if self.style in (1,2) and self.geometry['polygons']:
            # Painter-order diagnostic fill; not a depth-buffered game renderer.
            ordered = sorted(enumerate(self.geometry['polygons']),
                             key=lambda row:sum(projected[i][2] for i in row[1])/len(row[1]))
            painter.setPen(QPen(QColor('#263a45'),.7))
            for face_index,face in ordered:
                painter.setBrush(QColor('#829ba9'))
                if self.style==2 and 'uv' in self.geometry:
                    texture=self.textures.get(self.geometry['face_materials'][face_index])
                    colors=self.geometry.get('vertex_colors')
                    if texture is not None and colors is not None and colors[face_index] is not None:
                        values=colors[face_index]
                        painter.setBrush(QColor(*(round(sum(color[i] for color in values)/len(values))
                                                  for i in range(4))))
                    elif texture is not None and len(face)==3:
                        uv=self.geometry['uv'][face_index]
                        source=[(u*texture.width(),v*texture.height()) for u,v in uv]
                        ax,ay=source[0];bx,by=source[1];cx,cy=source[2]
                        det=(bx-ax)*(cy-ay)-(cx-ax)*(by-ay)
                        if abs(det)>1e-12:
                            a,b,c=[screen[i] for i in face]
                            m11=((b.x()-a.x())*(cy-ay)-(c.x()-a.x())*(by-ay))/det
                            m21=((c.x()-a.x())*(bx-ax)-(b.x()-a.x())*(cx-ax))/det
                            m12=((b.y()-a.y())*(cy-ay)-(c.y()-a.y())*(by-ay))/det
                            m22=((c.y()-a.y())*(bx-ax)-(b.y()-a.y())*(cx-ax))/det
                            brush=QBrush(texture);brush.setTransform(QTransform(m11,m12,m21,m22,
                                a.x()-m11*ax-m21*ay,a.y()-m12*ax-m22*ay))
                            painter.setBrush(brush)
                painter.drawPolygon(QPolygonF([screen[i] for i in face]))
        else:
            painter.setPen(QPen(QColor('#79d2e6'),.8))
            for a,b in self.geometry['edges']:painter.drawLine(screen[a],screen[b])
        if 'bone_names' in self.geometry:
            painter.setBrush(QColor('#ffd078'))
            for p in screen:painter.drawEllipse(p,2.5,2.5)
        axes = project([(1,0,0),(0,1,0),(0,0,1)],self.yaw,self.pitch)
        origin = QPointF(48,self.height()-48)
        for label,color,(x,y,z) in zip('XYZ',('#ef7777','#7cdd8c','#83aaff'),axes):
            end = origin+QPointF(x*30,-y*30)
            painter.setPen(QPen(QColor(color),2));painter.drawLine(origin,end)
            painter.drawText(end+QPointF(3,-3),label)
        if self.style==2 and self.material_states and (not self.gpu or self.gpu_failed):
            painter.setPen(QColor('#ffcf80'))
            painter.drawText(8,20,'Qt raster: без framebuffer-эффектов, culling, clamp и depth buffer')


class MeshView(QWidget):
    requested = Signal(str)
    navigate = Signal(str, int)
    frame_requested = Signal(int, int, int)  # material slot, sampler, saved-link step
    def __init__(self):
        super().__init__(); self.document = None; self.operation = ''; self.name = ''
        self.path = '';self.polys_id = 0
        layout = QVBoxLayout(self); controls = QHBoxLayout(); layout.addLayout(controls)
        self.fit = QPushButton('Вписать'); controls.addWidget(self.fit)
        self.camera = QComboBox(); self.camera.addItems(['Объём','Спереди','Сбоку','Сверху'])
        controls.addWidget(self.camera)
        self.style = QComboBox();self.style.addItems(['Каркас','Грани (диагностика)'])
        controls.addWidget(self.style)
        self.source = QComboBox();controls.addWidget(self.source)
        self.polys_button=QPushButton('Открыть сохранённые Polys')
        self.polys_button.setToolTip('Отдельные сохранённые полигоны, не подтверждение игровой коллизии')
        self.polys_button.clicked.connect(self.open_polys);layout.addWidget(self.polys_button)
        self.polys_warning=QLabel('Polys — отдельные сохранённые полигоны; их соответствие узлам Model, '
                                  'мировое размещение и игровая коллизия не подтверждены.')
        self.polys_warning.setWordWrap(True);layout.addWidget(self.polys_warning)
        self.polys_button.setEnabled(False);self.polys_button.hide();self.polys_warning.hide()
        self.uv_controls=QWidget();uv_layout=QHBoxLayout(self.uv_controls)
        uv_layout.setContentsMargins(0,0,0,0)
        uv_layout.addWidget(QLabel('Время UV (диагностика), с:'))
        self.uv_time=QDoubleSpinBox();self.uv_time.setRange(0,3600);self.uv_time.setDecimals(3)
        self.uv_time.setSingleStep(.1);uv_layout.addWidget(self.uv_time)
        self.uv_play=QPushButton('Пуск UV');self.uv_play.setCheckable(True);uv_layout.addWidget(self.uv_play)
        layout.addWidget(self.uv_controls);self.uv_controls.hide()
        self.uv_timer=QTimer(self);self.uv_timer.setInterval(33)
        self.uv_elapsed=QElapsedTimer();self.uv_started=0.
        self.uv_timer.timeout.connect(self.tick_uv)
        self.uv_play.toggled.connect(self.play_uv)
        self.uv_time.valueChanged.connect(self.set_uv_time)
        self.frame_controls=QWidget();frame_layout=QHBoxLayout(self.frame_controls)
        frame_layout.setContentsMargins(0,0,0,0)
        frame_layout.addWidget(QLabel('Кадр AnimNext (диагностика):'))
        self.frame_sampler=QComboBox();frame_layout.addWidget(self.frame_sampler)
        self.frame_step=QSpinBox();self.frame_step.setRange(0,31);frame_layout.addWidget(self.frame_step)
        self.frame_apply=QPushButton('Показать кадр');frame_layout.addWidget(self.frame_apply)
        frame_layout.addWidget(QLabel('Кадров/с (диагн.):'))
        self.frame_fps=QDoubleSpinBox();self.frame_fps.setRange(.5,12.)
        self.frame_fps.setDecimals(1);self.frame_fps.setValue(4.);frame_layout.addWidget(self.frame_fps)
        self.frame_play=QPushButton('Пуск кадров');self.frame_play.setCheckable(True)
        frame_layout.addWidget(self.frame_play)
        self.frame_timer=QTimer(self);self.frame_timer.setSingleShot(True)
        self.frame_timer.timeout.connect(self.tick_saved_frames)
        self.frame_play.toggled.connect(self.play_saved_frames)
        self.frame_sampler.currentIndexChanged.connect(lambda _:self.frame_step.setValue(0))
        self.frame_apply.clicked.connect(self.request_frame)
        self.frame_pending=False;self.frame_displayed=None
        layout.addWidget(self.frame_controls);self.frame_controls.hide()
        self.info = QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        self.canvas = MeshCanvas();layout.addWidget(self.canvas,1)
        self.canvas.graphicsUnavailable.connect(lambda message:self.info.setText(self.info.text()+'\n'+message))
        layout.addWidget(QLabel('ЛКМ: вращение · ПКМ/средняя: перемещение · колесо: масштаб'))
        self.fit.clicked.connect(self.canvas.reset_camera)
        self.camera.currentIndexChanged.connect(self.canvas.camera)
        self.style.currentIndexChanged.connect(self.set_style)
        self.source.currentIndexChanged.connect(self.select_source)

    def set_style(self, index):
        self.canvas.style = index;self.canvas.update()

    def select_source(self, index):
        if index >= 0 and self.document is not None:
            self.frame_play.setChecked(False)
            self.requested.emit(self.source.currentData())

    def set_loading(self, busy):
        self.source.setEnabled(not busy and self.source.count()>1)
        self.polys_button.setEnabled(not busy and bool(self.path and self.polys_id))
        if busy:self.uv_play.setChecked(False)
        if busy:
            self.frame_timer.stop()
            if self.frame_play.isChecked() and not self.frame_pending:self.frame_play.setChecked(False)
        self.uv_controls.setEnabled(not busy)
        self.frame_controls.setEnabled(not busy)
        if not busy and self.frame_pending:
            self.frame_pending=False
            if self.frame_play.isChecked():
                self.frame_timer.start(round(1000/self.frame_fps.value()))

    def request_frame(self):
        target=self.frame_sampler.currentData()
        if (isinstance(target,(tuple,list)) and len(target)==2
                and all(type(value) is int for value in target)):
            self.frame_pending=True
            self.frame_requested.emit(target[0],target[1],self.frame_step.value())

    def play_saved_frames(self,playing):
        self.frame_play.setText('Пауза кадров' if playing else 'Пуск кадров')
        for control in (self.frame_sampler,self.frame_step,self.frame_apply,self.frame_fps):
            control.setEnabled(not playing)
        if playing:self.request_frame()
        else:self.frame_timer.stop()

    def tick_saved_frames(self):
        if self.frame_step.value()>=self.frame_step.maximum():
            self.frame_play.setChecked(False)
            self.info.setText(self.info.text()+'\nДостигнут предел 31 шага AnimNext; просмотр остановлен.')
            return
        self.frame_step.setValue(self.frame_step.value()+1)
        self.request_frame()

    def open_polys(self):
        if self.path and self.polys_id and self.polys_button.isEnabled():
            self.navigate.emit(self.path,self.polys_id)

    def play_uv(self,playing):
        self.uv_play.setText('Пауза UV' if playing else 'Пуск UV')
        if playing:
            self.uv_started=self.uv_time.value();self.uv_elapsed.start();self.uv_timer.start()
        else:self.uv_timer.stop()

    def set_uv_time(self,seconds):
        try:self.canvas.material_time(seconds)
        except ValueError as error:
            self.uv_play.setChecked(False);self.info.setText(str(error))
        if self.uv_play.isChecked():
            self.uv_started=seconds;self.uv_elapsed.start()

    def tick_uv(self):
        value=min(3600.,self.uv_started+self.uv_elapsed.elapsed()/1000)
        self.uv_time.blockSignals(True);self.uv_time.setValue(value);self.uv_time.blockSignals(False)
        try:self.canvas.material_time(value)
        except ValueError as error:
            self.uv_play.setChecked(False);self.info.setText(str(error))
        if value>=3600:self.uv_play.setChecked(False)

    def hideEvent(self,event):
        self.uv_play.setChecked(False);self.frame_play.setChecked(False)
        super().hideEvent(event)

    def clear(self):
        self.uv_play.setChecked(False);self.frame_play.setChecked(False)
        self.uv_controls.hide();self.frame_controls.hide();self.frame_pending=False;self.frame_displayed=None
        self.canvas.clear();self.document=None;self.operation='';self.name='';self.info.clear()
        self.path='';self.polys_id=0
        self.polys_button.setEnabled(False);self.polys_button.hide();self.polys_warning.hide()
        self.source.blockSignals(True);self.source.clear();self.source.blockSignals(False)
        self.frame_sampler.clear();self.frame_step.setValue(0)

    def load(self, document, operation, name, path=''):
        self.clear();self.document=document;self.operation=operation;self.name=name
        self.path=str(path) if path else ''
        polys=document.get('polys') if operation=='model' else None
        if isinstance(polys,dict):
            identifier=polys.get('id')
            if type(identifier) is int and identifier>0 and polys.get('class')=='Polys':
                self.polys_id=identifier
        self.polys_button.setVisible(bool(self.polys_id))
        self.polys_warning.setVisible(bool(self.polys_id))
        self.polys_button.setEnabled(bool(self.path and self.polys_id))
        self.source.blockSignals(True)
        self.source.addItem('Исходная геометрия' if operation=='skeletal_mesh' else 'Геометрия','render')
        if operation=='static_mesh':self.source.addItem('Коллизия: треугольники','collision')
        if operation=='skeletal_mesh':self.source.addItem('Скелет: опорная поза','skeleton')
        if operation in ('static_mesh','skeletal_mesh'):
            self.source.addItem('Материалы и текстуры (диагностика)','textured')
        if operation=='skeletal_mesh':self.source.addItem('Анимация модели (skinning)','skinning')
        self.source.blockSignals(False)

    def display(self, prepared, preserve_view=False):
        if preserve_view and prepared.get('frame_error'):
            self.frame_play.setChecked(False)
            if self.frame_displayed is not None:
                target=self.frame_displayed[:2]
                self.frame_sampler.blockSignals(True)
                for index in range(self.frame_sampler.count()):
                    if self.frame_sampler.itemData(index)==target:
                        self.frame_sampler.setCurrentIndex(index);break
                self.frame_sampler.blockSignals(False)
                self.frame_step.setValue(self.frame_displayed[2])
            self.info.setText(self.info.text()+'\nСохранённый кадр не выбран; '
                              'оставлен предыдущий кадр: '+prepared['frame_error'])
            return
        camera=(self.canvas.yaw,self.canvas.pitch,self.canvas.zoom,QPointF(self.canvas.pan))
        previous_time=self.uv_time.value()
        if not preserve_view:self.frame_play.setChecked(False)
        self.uv_play.setChecked(False);self.uv_controls.hide();self.frame_controls.hide()
        if 'error' in prepared:
            self.error(prepared['error'])
            if prepared.get('warnings'):
                self.info.setText(self.info.text()+'\n'+'\n'.join(prepared['warnings']))
            return
        self.canvas.display(prepared)
        self.uv_time.blockSignals(True);self.uv_time.setValue(0);self.uv_time.blockSignals(False)
        from material_uv import has_timed_uv
        self.uv_controls.setVisible(any(has_timed_uv(t) for t in prepared.get('textures',{}).values()))
        from material_frames import selectable_samplers
        self.frame_sampler.blockSignals(True);self.frame_sampler.clear()
        for slot,texture in sorted(prepared.get('textures',{}).items()):
            for sampler in selectable_samplers(texture):
                self.frame_sampler.addItem(f'Материал {slot}, sampler {sampler}',(slot,sampler))
        selection=prepared.get('frame_selection')
        self.frame_step.setValue(selection[2] if isinstance(selection,(tuple,list)) and len(selection)==3 else 0)
        if isinstance(selection,(tuple,list)) and len(selection)==3:
            for index in range(self.frame_sampler.count()):
                if self.frame_sampler.itemData(index)==tuple(selection[:2]):
                    self.frame_sampler.setCurrentIndex(index);break
        self.frame_sampler.blockSignals(False)
        target=self.frame_sampler.currentData()
        self.frame_displayed=((*target,self.frame_step.value())
                              if isinstance(target,(tuple,list)) and len(target)==2 else None)
        self.frame_controls.setVisible(self.frame_sampler.count()>0)
        if 'textures' in prepared:self.canvas.style=2
        else:self.canvas.style=self.style.currentIndex()
        if preserve_view:
            self.canvas.yaw,self.canvas.pitch,self.canvas.zoom,self.canvas.pan=camera
            self.uv_time.setValue(previous_time)
        self.canvas.update()
        bounds_label=('Границы отображаемой геометрии XYZ' if self.operation=='model'
                      else 'Границы XYZ')
        self.info.setText(f'{self.name} · {len(prepared["points"])} вершин · '
                          f'{len(prepared["polygons"])} граней · геометрия без материалов\n'
                           f'{bounds_label}: {prepared["bounds"]}'
                           +('\n'+'\n'.join(prepared.get('warnings',[])) if prepared.get('warnings') else ''))
        if 'textures' in prepared:
            backend='OpenGL, depth buffer' if self.canvas.gpu else 'Qt raster, сортировка без z-buffer'
            self.info.setText(f'{self.name} · материалов/текстур: {len(prepared["textures"])} · '
                              f'ортографическая диагностика · {backend}\n'
                              +'\n'.join(prepared.get('warnings',[])))
            if self.frame_sampler.count():
                self.info.setText(self.info.text()+'\nAnimNext: частота просмотра задана пользователем; '
                                  'игровое время и синхронизация с UV не подтверждены. '
                                  'Конец, цикл или ошибка останавливают просмотр; загрузка влияет на темп.')

    def error(self, message):
        self.uv_play.setChecked(False);self.frame_play.setChecked(False)
        self.uv_controls.hide();self.frame_controls.hide()
        self.canvas.clear();self.info.setText('Предпросмотр недоступен: '+message)
