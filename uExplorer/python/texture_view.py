"""Read-only texture canvas with zoom, pan and per-mip display."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QColor, QBrush, QPainter
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGraphicsView, QGraphicsScene)
from texture_decode import faces


class TextureCanvas(QGraphicsView):
    zoom_changed = Signal(float)
    def __init__(self):
        super().__init__(); self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.fit_mode = True; self.background = 0; self.item = None
        self.set_background(0)
    def set_background(self, index):
        self.background = index
        if index == 0:
            tile = QPixmap(32,32); tile.fill(QColor('#bcbcbc'))
            painter = QPainter(tile); painter.fillRect(0,0,16,16,QColor('#eeeeee'))
            painter.fillRect(16,16,16,16,QColor('#eeeeee')); painter.end()
            self.setBackgroundBrush(QBrush(tile))
        else:
            self.setBackgroundBrush(QColor('black' if index == 1 else 'white'))
        self.viewport().update()
    def clear(self):
        self.scene().clear(); self.item = None; self.scene().setSceneRect(0,0,0,0)
        self.resetTransform(); self.fit_mode = True; self.zoom_changed.emit(1.)
    def display(self, pixels, width, height):
        self.clear()
        image = QImage(pixels,width,height,width*4,QImage.Format_RGBA8888).copy()
        if image.isNull():raise ValueError('Unable to allocate texture preview')
        self.item = self.scene().addPixmap(QPixmap.fromImage(image))
        self.scene().setSceneRect(self.item.boundingRect()); self.fit_image()
    def fit_image(self):
        self.fit_mode = True
        if self.item:
            self.fitInView(self.item,Qt.KeepAspectRatio)
            self.zoom_changed.emit(self.transform().m11())
    def actual_size(self):
        self.fit_mode = False; self.resetTransform(); self.zoom_changed.emit(1.)
    def zoom(self, factor):
        if not self.item:return
        self.fit_mode = False
        current = self.transform().m11()
        target = max(.01,min(64.,current*factor)); self.scale(target/current,target/current)
        self.zoom_changed.emit(target)
    def wheelEvent(self, event):
        self.zoom(1.25 if event.angleDelta().y()>0 else .8); event.accept()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:self.fit_image()


class TextureView(QWidget):
    requested = Signal(int, int)  # mip, face
    def __init__(self):
        super().__init__(); self.document = None; self.name = ''
        layout = QVBoxLayout(self)
        controls = QHBoxLayout(); layout.addLayout(controls)
        self.minus = QPushButton('−'); self.plus = QPushButton('+')
        self.actual = QPushButton('1:1'); self.fit = QPushButton('Вписать')
        for button in (self.minus,self.plus,self.actual,self.fit):controls.addWidget(button)
        self.scale_label = QLabel('100%'); controls.addWidget(self.scale_label)
        self.background = QComboBox();self.background.addItems(['Прозрачность','Чёрный фон','Белый фон'])
        controls.addWidget(self.background)
        selectors = QHBoxLayout();layout.addLayout(selectors)
        selectors.addWidget(QLabel('Mip:'));self.mip = QComboBox();selectors.addWidget(self.mip)
        selectors.addWidget(QLabel('Грань:'));self.face = QComboBox();selectors.addWidget(self.face)
        self.info = QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        self.canvas = TextureCanvas();layout.addWidget(self.canvas,1)
        self.minus.clicked.connect(lambda:self.canvas.zoom(.8))
        self.plus.clicked.connect(lambda:self.canvas.zoom(1.25))
        self.actual.clicked.connect(self.canvas.actual_size);self.fit.clicked.connect(self.canvas.fit_image)
        self.background.currentIndexChanged.connect(self.canvas.set_background)
        self.canvas.zoom_changed.connect(lambda scale:self.scale_label.setText(f'{scale*100:.1f}%'))
        self.mip.currentIndexChanged.connect(self.select_mip)
        self.face.currentIndexChanged.connect(self.select_face)
    def clear(self):
        self.document=None;self.name='';self.canvas.clear();self.info.clear()
        for combo in (self.mip,self.face):
            combo.blockSignals(True);combo.clear();combo.blockSignals(False)
    def set_loading(self, loading):
        self.mip.setEnabled(not loading and self.mip.count()>0)
        self.face.setEnabled(not loading and self.face.count()>1)
    def load(self, document, name):
        self.clear();self.document=document;self.name=name
        self.face.blockSignals(True);self.face.addItem('Основная текстура',-1)
        for index, reference in sorted(faces(document).items()):
            self.face.addItem(f'{index}: {reference.get("path","None")}',index)
        self.face.blockSignals(False)
        self.set_mips([(m['width'],m['height']) for m in document.get('mips',[])],0)
        self.set_loading(False)
    def set_mips(self, sizes, level):
        self.mip.blockSignals(True);self.mip.clear()
        for i,(w,h) in enumerate(sizes):self.mip.addItem(f'{i} · {w}×{h}',i)
        self.mip.setCurrentIndex(level if level<len(sizes) else -1);self.mip.blockSignals(False)
    def display(self, prepared):
        self.set_mips(prepared['mip_sizes'],prepared['level'])
        if 'error' in prepared:
            self.error(prepared['error']);return
        self.canvas.display(prepared['pixels'],prepared['width'],prepared['height'])
        self.info.setText(f'{self.name} · {prepared["width"]}×{prepared["height"]} · '
                          f'{prepared["format"]} · {len(prepared["mip_sizes"])} mip · только просмотр')
    def error(self, message):
        self.canvas.clear();self.info.setText('Предпросмотр недоступен: '+message)
    def select_mip(self, index):
        if index>=0 and self.document:self.requested.emit(index,self.face.currentData())
    def select_face(self, index):
        if index>=0 and self.document:
            self.set_mips([],0);self.requested.emit(0,self.face.currentData())
