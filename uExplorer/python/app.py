from __future__ import annotations
import json
from pathlib import Path
import sys
import threading
import traceback
import wave

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QRegularExpression
from PySide6.QtGui import QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout,
    QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QFileDialog,
    QLabel, QLineEdit, QProgressBar, QMessageBox, QAbstractItemView, QCheckBox, QComboBox,
    QStackedWidget, QTabBar, QInputDialog)
from backend import Core, export_classes, targets, view_text
from resource_view import MODES, groups, read_model_preview, summary_text
from audio_analysis import waveform
from texture_decode import prepare_texture
from mesh_decode import mesh_preview
from animation_decode import prepare_animation
from vertmesh_decode import prepare_vertmesh
from material_graph import prepare_material_graph, material_thumbnail, ResourceResolver
from textured_mesh import prepare_textured
from skinning import prepare_skin
from resource_compare import compare_resources


class Highlight(QSyntaxHighlighter):
    def highlightBlock(self, text):
        rules = [(r'\b(class|extends|var|local|function|event|native|static|final|simulated|state|auto|enum|struct|const|config|defaultproperties|return|if|else|while|for|foreach|switch|case|default|break|continue|true|false|None|int|float|bool|string|byte|name|INT64)\b', '#1856a5'),
                 (r'"(?:[^"\\]|\\.)*"|\x27[^\x27]*\x27', '#27632a'),
                 (r'//.*$', '#606870')]
        for pattern, color in rules:
            fmt = QTextCharFormat(); fmt.setForeground(QColor(color))
            iterator = QRegularExpression(pattern).globalMatch(text)
            while iterator.hasNext():
                match = iterator.next(); self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)
    def __init__(self, work, parent):
        super().__init__(parent); self.work = work; self.cancel = threading.Event()
    def run(self):
        try: self.done.emit(self.work(self))
        except Exception: self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('uExplorer — Unreal package explorer'); self.resize(1450, 850)
        root = Path(__file__).resolve().parents[1]
        if (root/'portable.json').is_file():
            (root/'data').mkdir(exist_ok=True)
            self.settings = QSettings(str(root/'data/settings.ini'), QSettings.Format.IniFormat)
            self.settings.setFallbacksEnabled(False)
        else:
            self.settings = QSettings('L2Tools', 'uExplorer')
        self.core = Core(); self.worker = None; self.package = None; self.classes = []; self.result = None
        self.closing = False
        self.mode = 'code'; self.resources = {}; self.mode_states = {}; self.pending_preview = False
        self.sound_view = None
        self.texture_view = None
        self.mesh_view = None
        self.animation_view = None
        self.compare_view = None
        self.volume_view = None
        self.material_view = None;self.navigation_id=None
        self.material_overrides={}
        self.dependencies = []; self.output = self.settings.value('output', '')
        self.setStyleSheet('QPlainTextEdit { background: #ffffff; color: #202020; selection-background-color: #cce4ff; selection-color: #202020; }')
        root = QWidget(); layout = QVBoxLayout(root); self.setCentralWidget(root)
        bar = QHBoxLayout(); layout.addLayout(bar)
        self.open_button = QPushButton('Открыть каталог…'); self.open_button.clicked.connect(self.open_directory)
        self.reload_button = QPushButton('Обновить пакет'); self.reload_button.clicked.connect(self.load_package)
        self.deps_button = QPushButton('Зависимости…'); self.deps_button.clicked.connect(self.add_dependencies)
        self.output_button = QPushButton('Каталог экспорта…'); self.output_button.clicked.connect(self.choose_output)
        self.selected_button = QPushButton('Экспорт выбранных'); self.selected_button.clicked.connect(lambda: self.export(False))
        self.all_button = QPushButton('Экспорт всего .u'); self.all_button.clicked.connect(lambda: self.export(True))
        self.compare_button = QPushButton('Сравнить ресурсы…');self.compare_button.clicked.connect(self.compare_package)
        for widget in (self.open_button, self.reload_button, self.deps_button, self.output_button, self.selected_button, self.all_button, self.compare_button): bar.addWidget(widget)
        self.path_label = QLabel('Выберите каталог с пакетами'); self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addWidget(self.path_label)
        options = QHBoxLayout(); layout.addLayout(options)
        self.force = QCheckBox('Из байткода даже при наличии ScriptText'); self.force.toggled.connect(self.preview)
        options.addWidget(self.force)
        self.use_material=QPushButton('Материал → слот модели…')
        self.use_material.clicked.connect(self.assign_material);options.addWidget(self.use_material)
        self.reset_material=QPushButton('Сброс материалов модели')
        self.reset_material.clicked.connect(self.clear_material_overrides);options.addWidget(self.reset_material)
        options.addWidget(QLabel('ANSI ScriptText:'))
        self.encoding = QComboBox(); self.encoding.addItems(['cp1251', 'cp1252', 'latin1', 'cp949']); self.encoding.currentTextChanged.connect(self.refresh_code); options.addWidget(self.encoding)
        options.addStretch(); self.status_label = QLabel(''); options.addWidget(self.status_label)
        split = QSplitter(Qt.Horizontal); layout.addWidget(split, 1)
        left = QWidget(); l = QVBoxLayout(left); l.addWidget(QLabel('Пакеты .u / .utx / .usx / .ukx / .uax'))
        self.file_filter = QLineEdit(); self.file_filter.setPlaceholderText('Фильтр файлов'); l.addWidget(self.file_filter)
        self.files = QListWidget(); l.addWidget(self.files); split.addWidget(left)
        center = QWidget(); c = QVBoxLayout(center)
        self.mode_tabs = QTabBar(); self.mode_tabs.setExpanding(False); self.mode_tabs.setUsesScrollButtons(True)
        for key, title in MODES: self.mode_tabs.addTab(title)
        c.addWidget(self.mode_tabs)
        self.object_label = QLabel('Классы пакета (Ctrl / Shift — выбор нескольких)'); c.addWidget(self.object_label)
        self.class_filter = QLineEdit(); self.class_filter.setPlaceholderText('Фильтр классов'); c.addWidget(self.class_filter)
        self.class_list = QListWidget(); self.class_list.setSelectionMode(QAbstractItemView.ExtendedSelection); c.addWidget(self.class_list); split.addWidget(center)
        self.viewer = QStackedWidget(); split.addWidget(self.viewer)
        self.code = QPlainTextEdit(); self.code.setReadOnly(True); self.code.setLineWrapMode(QPlainTextEdit.NoWrap); self.code.setFont(QFont('Consolas', 11)); self.viewer.addWidget(self.code); self.highlight = Highlight(self.code.document())
        self.resource_text = QPlainTextEdit(); self.resource_text.setReadOnly(True)
        self.viewer.addWidget(self.resource_text)
        split.setSizes([240, 330, 880])
        bottom = QHBoxLayout(); layout.addLayout(bottom); self.progress = QProgressBar(); bottom.addWidget(self.progress)
        self.cancel_button = QPushButton('Отмена'); self.cancel_button.clicked.connect(self.cancel_work); bottom.addWidget(self.cancel_button)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(135); layout.addWidget(self.log)
        self.files.currentItemChanged.connect(self.load_package); self.class_list.currentItemChanged.connect(self.preview)
        self.file_filter.textChanged.connect(lambda text: self.filter_list(self.files, text))
        self.class_filter.textChanged.connect(lambda text: self.filter_list(self.class_list, text))
        self.mode_tabs.currentChanged.connect(self.change_mode)
        self.set_busy(False)
        previous = self.settings.value('directory', '')
        if previous and Path(previous).is_dir(): self.populate(previous)

    @staticmethod
    def filter_list(widget, text):
        for index in range(widget.count()):
            item = widget.item(index); item.setHidden(text.casefold() not in item.text().casefold())

    def set_busy(self, busy):
        if self.texture_view:self.texture_view.set_loading(busy)
        if self.mesh_view:self.mesh_view.set_loading(busy)
        if self.animation_view:self.animation_view.set_loading(busy)
        if self.compare_view:self.compare_view.set_loading(busy)
        if self.material_view:self.material_view.set_loading(busy)
        self.use_material.setEnabled(not busy and self.mode in ('materials','textures'))
        self.reset_material.setEnabled(not busy and bool(self.material_overrides))
        self.compare_button.setEnabled(not busy and bool(self.package) and self.mode!='code')
        for widget in (self.open_button, self.reload_button, self.deps_button, self.output_button, self.files, self.class_list, self.mode_tabs): widget.setEnabled(not busy)
        self.force.setEnabled(not busy and self.mode == 'code')
        self.encoding.setEnabled(self.mode == 'code')
        self.selected_button.setEnabled(not busy and self.mode == 'code' and bool(self.classes)); self.all_button.setEnabled(not busy and self.mode == 'code' and bool(self.classes)); self.cancel_button.setEnabled(busy)

    def task(self, work, callback):
        if self.worker is not None or self.closing: return
        self.set_busy(True); self.progress.setRange(0, 0)
        worker = Worker(work, self); self.worker = worker
        worker.done.connect(callback)
        worker.failed.connect(self.failure)
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.finished)
        worker.start()

    def finished(self):
        worker = self.worker; self.worker = None
        if worker: worker.deleteLater()
        if self.closing:
            self.pending_preview=False;self.close();return
        self.progress.setRange(0, 100); self.progress.setValue(100); self.set_busy(False)
        if self.pending_preview:
            self.pending_preview = False; self.preview()

    def failure(self, text):
        detail=text.strip().splitlines()[-1] if text.strip() else 'Неизвестная ошибка'
        item=self.class_list.currentItem()
        context=f"Пакет: {self.package or 'не выбран'}"
        if item:context+='\nКласс: '+item.text()
        self.log.appendPlainText(context+'\n'+detail+'\n\nТехнические подробности:\n'+text)
        self.status_label.setText('Ошибка: '+detail)
        if self.mode != 'code':
            self.resource_text.setPlainText('Структурный просмотр недоступен:\n'+detail)
            if self.texture_view and self.viewer.currentWidget() == self.texture_view:
                self.texture_view.error(detail)
            if self.mesh_view and self.viewer.currentWidget() == self.mesh_view:
                self.mesh_view.error(detail)
            if self.animation_view and self.viewer.currentWidget() == self.animation_view:
                self.animation_view.error(detail)
            if self.compare_view and self.viewer.currentWidget() == self.compare_view:
                self.compare_view.error(detail)

    def update_progress(self, value, total, name):
        self.progress.setRange(0, max(1, total)); self.progress.setValue(value); self.status_label.setText(name)

    def cancel_work(self):
        if self.worker:
            self.worker.cancel.set(); self.status_label.setText('Отмена после текущего класса/операции…')

    def open_directory(self):
        directory = QFileDialog.getExistingDirectory(self, 'Каталог с пакетами', self.settings.value('directory', ''))
        if directory: self.populate(directory)

    def populate(self, directory):
        self.save_mode_state()
        self.files.blockSignals(True); self.files.clear(); self.clear_classes(); self.package=None
        try:
            for path in sorted(Path(directory).iterdir(), key=lambda p: p.name.casefold()):
                if path.is_file() and path.suffix.casefold() in {'.u', '.utx', '.usx', '.ukx', '.uax', '.unr'}:
                    item=QListWidgetItem(path.name); item.setData(Qt.UserRole, str(path.resolve())); self.files.addItem(item)
        except OSError as error: self.failure(str(error))
        self.files.blockSignals(False); self.path_label.setText(directory); self.settings.setValue('directory',directory); self.set_busy(False)
        self.filter_list(self.files,self.file_filter.text())

    def add_dependencies(self):
        directory=QFileDialog.getExistingDirectory(self, 'Добавить каталог зависимостей Core.u / Engine.u / NWindow.u')
        if directory and directory not in self.dependencies:
            self.dependencies.append(directory); self.log.appendPlainText('Dependency search: '+directory); self.load_package()

    def load_package(self, *_):
        item=self.files.currentItem()
        if not item or self.worker: return
        self.save_mode_state()
        self.clear_classes(); self.package=item.data(Qt.UserRole)
        path=self.package; deps=list(self.dependencies)
        def work(w):
            inventory=self.core.request(operation='resource_inventory',path=path)['result']
            response={'package':dict(inventory,classes=[]), 'inventory':inventory}
            if inventory.get('excluded_script_exports'):
                try:
                    response.update(self.core.request(operation='inspect',path=path,dependencies=deps,reload=True))
                except Exception as error:
                    response['diagnostics']=['Просмотр классов недоступен: '+str(error)]
            return response
        self.task(work,self.loaded)

    def clear_classes(self):
        # clear() can emit currentItemChanged while the old item's data is still
        # visible. Never start a preview during a package/directory transition.
        self.stop_media()
        previous=self.class_list.blockSignals(True)
        try:self.class_list.clear()
        finally:self.class_list.blockSignals(previous)
        self.classes=[];self.result=None;self.code.clear();self.resource_text.clear()
        self.viewer.setCurrentWidget(self.code if self.mode=='code' else self.resource_text)
        self.resources={};self.pending_preview=False
        self.mode_tabs.blockSignals(True)
        for i in range(len(MODES)): self.mode_tabs.setTabEnabled(i,False)
        self.mode_tabs.blockSignals(False)

    def loaded(self, response):
        self.classes=response['package']['classes']
        self.resources=groups(response['inventory'])
        self.resources['code']=sorted(self.classes,key=lambda row:row['path'].casefold())
        if self.navigation_id is not None:
            for mode,entries in self.resources.items():
                if any(o['id']==self.navigation_id for o in entries):
                    self.mode=mode
                    self.mode_states[(self.package,mode)]=dict(current=self.navigation_id,filter='')
                    break
            self.navigation_id=None
        self.mode_tabs.blockSignals(True)
        for i,(key,_) in enumerate(MODES):self.mode_tabs.setTabEnabled(i,bool(self.resources[key]))
        if not self.resources.get(self.mode):
            self.mode=next((key for key,_ in MODES if self.resources[key]),'code')
        self.mode_tabs.setCurrentIndex(next(i for i,(key,_) in enumerate(MODES) if key==self.mode))
        self.mode_tabs.blockSignals(False)
        self.populate_objects()
        p=response['package'];self.status_label.setText(f"{p['version']}/{p['licensee']} · {len(self.classes)} классов · {p['envelope']}")
        self.log.appendPlainText(self.package)
        for message in response.get('diagnostics',[]): self.log.appendPlainText(message)

    def save_mode_state(self):
        if not self.package:return
        current=self.class_list.currentItem()
        self.mode_states[(self.package,self.mode)]=dict(
            filter=self.class_filter.text(),
            current=current.data(Qt.UserRole)['id'] if current else None,
            selected=[x.data(Qt.UserRole)['id'] for x in self.class_list.selectedItems()],
            scroll=self.class_list.verticalScrollBar().value())

    def change_mode(self,index):
        if index<0 or self.worker:return
        self.save_mode_state();self.mode=MODES[index][0];self.populate_objects();self.set_busy(self.worker is not None)

    def stop_media(self):
        if self.sound_view:self.sound_view.clear()
        if self.texture_view:self.texture_view.clear()
        if self.mesh_view:self.mesh_view.clear()
        if self.animation_view:self.animation_view.clear()
        if self.compare_view:self.compare_view.clear()
        if self.material_view:self.material_view.clear()
        if self.volume_view:self.volume_view.clear()

    def populate_objects(self):
        self.stop_media()
        self.result=None;self.code.clear();self.resource_text.clear()
        self.viewer.setCurrentWidget(self.code if self.mode=='code' else self.resource_text)
        self.object_label.setText('Классы пакета' if self.mode=='code' else 'Объекты пакета')
        self.class_filter.setPlaceholderText('Фильтр классов' if self.mode=='code' else 'Фильтр ресурсов')
        state=self.mode_states.get((self.package,self.mode),{})
        self.class_list.blockSignals(True);self.class_list.clear()
        current=None
        for info in self.resources.get(self.mode,[]):
            item=QListWidgetItem(info['path']);item.setData(Qt.UserRole,info)
            item.setToolTip('extends '+info['super'] if self.mode=='code' else info['class'])
            self.class_list.addItem(item)
            if info['id']==state.get('current'):current=item
        if current:self.class_list.setCurrentItem(current)
        for i in range(self.class_list.count()):
            item=self.class_list.item(i);item.setSelected(item.data(Qt.UserRole)['id'] in state.get('selected',[]))
        self.class_filter.setText(state.get('filter',''))
        self.filter_list(self.class_list,self.class_filter.text())
        self.class_list.verticalScrollBar().setValue(state.get('scroll',0))
        self.class_list.blockSignals(False)
        if current:
            if self.worker:self.pending_preview=True
            else:self.preview()

    def preview(self, *_):
        item=self.class_list.currentItem()
        if not item or self.worker or not self.package: return
        info=item.data(Qt.UserRole);path=self.package;deps=list(self.dependencies);force=self.force.isChecked()
        if self.mode!='code':
            self.stop_media();self.viewer.setCurrentWidget(self.resource_text)
            self.resource_text.clear()
            operation=info.get('operation')
            if not operation:
                self.resource_text.setPlainText('Специализированный reader пока недоступен.\n\n'+summary_text(info));return
            if info.get('serial_bytes',0)>64*1024*1024:
                self.resource_text.setPlainText('Ресурс превышает лимит предпросмотра 64 МиБ.\n\n'+summary_text(info));return
            def work(w):
                if operation=='material':
                    graph=prepare_material_graph(self.core,path,info['id'],deps,w.cancel.is_set)
                    thumbnail=material_thumbnail(self.core,graph['nodes'][0],deps) if graph['nodes'] else None
                    return {'_material':graph,'_thumbnail':thumbnail}
                response=(read_model_preview(self.core,path,info['id']) if operation=='model'
                          else self.core.request(operation=operation,path=path,object_id=info['id']))
                if operation=='blocking_volume':response['_blocking_volume']=True
                if operation=='texture':
                    response['_texture']=prepare_texture(self.core,path,response['result'],dependencies=deps)
                opaque_model=(operation=='model' and
                              response['result'].get('interpretation')=='opaque')
                if operation in ('static_mesh','skeletal_mesh','model','polys') and not opaque_model:
                    response['_mesh']=mesh_preview(response['result'],operation)
                    response['_mesh_operation']=operation
                if operation=='mesh_animation':
                    response['_animation']=prepare_animation(response['result'],0)
                if operation=='vert_mesh':
                    response['_animation']=prepare_vertmesh(response['result'],0)
                    response['_animation_operation']='vert_mesh'
                if operation=='sound':
                    encoded=response['result']['body']['audio_hex']
                    if len(encoded)>128*1024*1024:raise ValueError('Audio preview exceeds 64 MiB')
                    audio=bytes.fromhex(encoded);response['_audio']=audio
                    try:response['_wave']=waveform(audio)
                    except (ValueError, EOFError, wave.Error):response['_wave']=[]
                return response
            self.task(work,self.resource_previewed)
            return
        if info not in self.classes:return
        self.result=None;self.code.clear()
        self.task(lambda w:self.core.request(operation='decompile',path=path,dependencies=deps,force_bytecode=force,**{'class':info['path']}),self.previewed)

    def previewed(self,response):
        self.result=response['result'];self.refresh_code();self.status_label.setText(self.result['method']+' · '+self.result['status'])
        for issue in self.result.get('issues',[]):self.log.appendPlainText(issue['scope']+': '+issue['message'])

    def resource_previewed(self,response):
        if '_blocking_volume' in response:
            if not self.volume_view:
                from volume_view import BlockingVolumeView
                self.volume_view=BlockingVolumeView();self.viewer.addWidget(self.volume_view)
                self.volume_view.navigate.connect(self.navigate_resource)
            self.volume_view.load(response['result'],self.package)
            self.viewer.setCurrentWidget(self.volume_view)
            self.status_label.setText('BlockingVolume · сохранённые свойства · только просмотр')
            return
        if '_material' in response:
            if not self.material_view:
                from material_view import MaterialView
                self.material_view=MaterialView();self.viewer.addWidget(self.material_view)
                self.material_view.requested.connect(self.preview_material)
                self.material_view.navigate.connect(self.navigate_resource)
            self.material_view.load(response['_material'])
            self.material_view.display(response.get('_thumbnail'))
            self.viewer.setCurrentWidget(self.material_view)
            self.material_view.set_loading(self.worker is not None)
            return
        if '_animation' in response:
            if not self.animation_view:
                from animation_view import AnimationView
                self.animation_view=AnimationView();self.viewer.addWidget(self.animation_view)
                self.animation_view.requested.connect(self.preview_animation)
            self.animation_view.load(response['result'],response.get('_animation_operation','mesh_animation'))
            self.viewer.setCurrentWidget(self.animation_view)
            self.animation_previewed(response['_animation'])
            self.animation_view.set_loading(self.worker is not None)
            return
        if '_mesh' in response:
            if not self.mesh_view:
                from mesh_view import MeshView
                self.mesh_view=MeshView();self.viewer.addWidget(self.mesh_view)
                self.mesh_view.requested.connect(self.preview_mesh)
                self.mesh_view.navigate.connect(self.navigate_resource)
                self.mesh_view.frame_requested.connect(self.preview_material_frame)
            self.mesh_view.load(response['result'],response['_mesh_operation'],
                                self.class_list.currentItem().text(),self.package)
            self.viewer.setCurrentWidget(self.mesh_view)
            self.mesh_previewed(response['_mesh'])
            self.mesh_view.set_loading(self.worker is not None)
            return
        if '_texture' in response:
            if not self.texture_view:
                from texture_view import TextureView
                self.texture_view=TextureView();self.viewer.addWidget(self.texture_view)
                self.texture_view.requested.connect(self.preview_texture)
            self.texture_view.load(response['result'],self.class_list.currentItem().text())
            self.viewer.setCurrentWidget(self.texture_view)
            self.texture_previewed(response['_texture'])
            self.texture_view.set_loading(self.worker is not None)
            return
        if '_audio' in response:
            try:
                if not self.sound_view:
                    from sound_view import SoundView
                    self.sound_view=SoundView();self.viewer.addWidget(self.sound_view)
                self.sound_view.load(response['_audio'],response['_wave'],self.class_list.currentItem().text())
                self.viewer.setCurrentWidget(self.sound_view)
                self.status_label.setText('Звук готов · нажмите «Воспроизвести»')
                return
            except ImportError:
                self.resource_text.setPlainText('Для прослушивания установите PySide6-Addons той же версии, что PySide6-Essentials.\n\n'+summary_text(response['result']))
                return
            except Exception:
                self.failure(traceback.format_exc());return
        if response['result'].get('interpretation')=='opaque':
            self.resource_text.setPlainText('Непроверенная форма Model: доступен ограниченный просмотр '
                                            'исходных байтов; геометрия не распознана.\n\n'
                                            +summary_text(response['result']))
            self.status_label.setText('Model не проверена · только просмотр')
        else:
            self.resource_text.setPlainText('Структурные данные; графический/звуковой предпросмотр ещё не подключён.\n\n'+summary_text(response['result']))
            self.status_label.setText('Ресурс прочитан · только просмотр')

    def preview_texture(self, level, face):
        if self.worker or not self.texture_view or self.texture_view.document is None:return
        document=self.texture_view.document;path=self.package
        self.texture_view.canvas.clear()
        deps=list(self.dependencies)
        self.task(lambda w:prepare_texture(self.core,path,document,level,face,deps),self.texture_previewed)

    def assign_material(self):
        if self.worker or not self.class_list.currentItem():return
        identifier=self.class_list.currentItem().data(Qt.UserRole)['id']
        slot,ok=QInputDialog.getInt(self,'Материал модели','Слот (подстановка только для просмотра):',0,0,255)
        if ok:
            self.material_overrides[slot]=(self.package,identifier)
            self.status_label.setText(f'Материал для слота {slot} выбран; откройте модель и текстурный просмотр')
            self.set_busy(False)

    def clear_material_overrides(self):
        self.material_overrides.clear();self.set_busy(self.worker is not None)
        self.status_label.setText('Подстановки материалов сброшены; перечитайте просмотр модели')

    def preview_material(self,index):
        if self.worker or not self.material_view or not self.material_view.graph:return
        node=self.material_view.graph['nodes'][index]
        deps=list(self.dependencies)
        self.task(lambda w:material_thumbnail(self.core,node,deps),self.material_view.display)

    def navigate_resource(self,path,identifier):
        if self.worker:return
        if str(Path(self.package).resolve())!=str(Path(path).resolve()):
            self.populate(str(Path(path).parent));self.navigation_id=identifier
            for i in range(self.files.count()):
                item=self.files.item(i)
                if item.data(Qt.UserRole)==str(Path(path).resolve()):
                    item.setHidden(False);self.files.setCurrentItem(item);return
            self.navigation_id=None;return
        for mode,entries in self.resources.items():
            if any(o['id']==identifier for o in entries):
                self.mode_tabs.setCurrentIndex(next(i for i,(key,_) in enumerate(MODES) if key==mode))
                self.class_filter.clear()
                for i in range(self.class_list.count()):
                    if self.class_list.item(i).data(Qt.UserRole)['id']==identifier:
                        self.class_list.setCurrentRow(i);return

    def preview_mesh(self, source):
        if self.worker or not self.mesh_view or self.mesh_view.document is None:return
        document=self.mesh_view.document;operation=self.mesh_view.operation
        self.mesh_view.canvas.clear()
        if source=='skinning':
            path=self.package;deps=list(self.dependencies)
            overrides=dict(self.material_overrides)
            def work(w):
                resolver=ResourceResolver(self.core,deps)
                target,identifier=resolver.resolve(path,document['body']['animation'])
                animation=self.core.request(operation='mesh_animation',path=target,object_id=identifier)['result']
                surface=prepare_textured(self.core,path,document,'skeletal_mesh',deps,overrides)
                pair=dict(mesh=document,animation=animation,body=animation['body'],surface=surface)
                return dict(result=pair,_animation=prepare_skin(pair,0),_animation_operation='skinning')
            self.task(work,self.resource_previewed);return
        if source=='textured':
            path=self.package;deps=list(self.dependencies)
            overrides=dict(self.material_overrides)
            self.task(lambda w:prepare_textured(self.core,path,document,operation,deps,overrides),self.mesh_previewed)
            return
        self.task(lambda w:mesh_preview(document,operation,source),self.mesh_previewed)

    def preview_material_frame(self,slot,sampler,step):
        if (self.worker or not self.mesh_view or self.mesh_view.document is None
                or self.mesh_view.source.currentData()!='textured'):
            return
        path=self.package;deps=list(self.dependencies);overrides=dict(self.material_overrides)
        document=self.mesh_view.document;operation=self.mesh_view.operation
        self.task(lambda w:prepare_textured(self.core,path,document,operation,deps,overrides,
                                            frame_selection=(slot,sampler,step)),
                  self.mesh_frame_previewed)

    def preview_animation(self, index):
        if self.worker or not self.animation_view or self.animation_view.document is None:return
        document=self.animation_view.document
        prepare={'vert_mesh':prepare_vertmesh,'skinning':prepare_skin}.get(self.animation_view.operation,prepare_animation)
        self.task(lambda w:prepare(document,index),self.animation_previewed)

    def animation_previewed(self, prepared):
        self.animation_view.display(prepared)
        label='VertMesh' if prepared.get('kind')=='vert_mesh' else 'Анимация скелета'
        self.status_label.setText('Предпросмотр недоступен' if 'error' in prepared else label+' · только просмотр')

    def compare_package(self):
        if self.worker or not self.package or self.mode=='code':return
        candidate,_=QFileDialog.getOpenFileName(self,'Пакет реконструкции для сравнения ресурсов',
                                               str(Path(self.package).parent),
                                               'Unreal packages (*.u *.utx *.usx *.ukx *.uax *.unr);;Все файлы (*)')
        if candidate:self.start_comparison(candidate)

    def start_comparison(self, candidate):
        if self.worker or not self.package:return
        self.stop_media()
        if not self.compare_view:
            from compare_view import CompareView
            self.compare_view=CompareView();self.viewer.addWidget(self.compare_view)
            self.compare_view.back.connect(self.preview)
        original=self.package
        self.compare_view.loading(original,candidate);self.viewer.setCurrentWidget(self.compare_view)
        self.task(lambda w:compare_resources(self.core,original,candidate,w.cancel.is_set,w.progress.emit),
                  self.compared)

    def compared(self, report):
        self.compare_view.display(report)
        self.status_label.setText('Сравнение отменено' if report['cancelled'] else 'Сравнение ресурсов завершено')

    def mesh_previewed(self, prepared):
        self.mesh_view.display(prepared)
        self.status_label.setText('Предпросмотр недоступен' if 'error' in prepared else 'Геометрия · только просмотр')

    def mesh_frame_previewed(self, prepared):
        self.mesh_view.display(prepared,preserve_view=True)
        self.status_label.setText('Кадр не выбран · оставлен предыдущий' if 'frame_error' in prepared else
                                  'Предпросмотр недоступен' if 'error' in prepared else
                                  'Сохранённый кадр · только просмотр')

    def texture_previewed(self, prepared):
        try:
            self.texture_view.display(prepared)
            self.status_label.setText('Предпросмотр недоступен' if 'error' in prepared else 'Текстура · только просмотр')
        except Exception:
            self.failure(traceback.format_exc())

    def refresh_code(self,*_):
        if self.result:self.code.setPlainText(view_text(self.result,self.encoding.currentText()))

    def choose_output(self):
        directory=QFileDialog.getExistingDirectory(self,'Каталог экспорта',self.output)
        if directory:self.output=directory;self.settings.setValue('output',directory);self.log.appendPlainText('Export: '+directory)

    def export(self,all_classes):
        if not self.package or self.worker or self.mode!='code':return
        chosen=self.classes if all_classes else [item.data(Qt.UserRole) for item in self.class_list.selectedItems()]
        if not chosen:QMessageBox.information(self,'Экспорт','Выберите хотя бы один класс.');return
        if not self.output:self.choose_output()
        if not self.output:return
        try:existing=[p for p in targets(self.package,chosen,self.output) if p.exists()]
        except Exception as error:self.failure(str(error));return
        overwrite=False
        if existing:
            overwrite=QMessageBox.question(self,'Перезапись',f'Уже существуют {len(existing)} файлов .uc. Перезаписать?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
            if not overwrite:return
        path=self.package;destination=self.output;deps=list(self.dependencies);force=self.force.isChecked()
        self.task(lambda w:export_classes(self.core,path,chosen,destination,deps,force,overwrite,w.cancel.is_set,w.progress.emit),self.exported)

    def exported(self,report):
        text=('Экспорт отменён' if report['cancelled'] else 'Экспорт завершён')+'\n'+json.dumps(report['counts'],ensure_ascii=False)+'\n'+report['report_file']
        self.log.appendPlainText(text);QMessageBox.information(self,'Результат',text)

    def closeEvent(self,event):
        self.stop_media()
        if self.worker:
            self.closing=True;self.pending_preview=False
            self.worker.cancel.set()
            self.status_label.setText('Завершение после текущего класса/операции…')
            self.cancel_button.setEnabled(False);event.ignore();return
        super().closeEvent(event)


def main():
    app=QApplication(sys.argv)
    try:window=MainWindow()
    except Exception as error:QMessageBox.critical(None,'uExplorer',str(error));return 1
    window.show();return app.exec()

if __name__=='__main__':sys.exit(main())
