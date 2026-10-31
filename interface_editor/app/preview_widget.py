"""Read-only image preview. QWidget/QPixmap stay on the GUI thread."""
from pathlib import Path
import re

from PySide6.QtCore import Qt, QTimer, QSaveFile, QIODevice, QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QScrollArea, QFileDialog, QTreeWidget, QTreeWidgetItem, QDialog, QDialogButtonBox, QSpinBox

from preview_render import render_preview, PREVIEW_PROFILES, SUPPORTED_PREVIEW_SCHEMAS, SCALABLE_PREVIEW_SCHEMAS


def save_png(image, filename):
    output = QSaveFile(str(filename))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    if not image.save(output, 'PNG'):
        output.cancelWriting()
        raise OSError('PNG encoding failed')
    if not output.commit():
        raise OSError(output.errorString())


class PreviewWidget(QWidget):
    def __init__(self, pane):
        super().__init__()
        self.pane = pane
        self.window = pane.window
        self.result = None
        self.generation = 0
        self.running = False
        self.pending = False
        self.status_key = 'Выберите элемент для предпросмотра'
        self.status_values = {}
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.context = QComboBox()
        self.context.addItem('', False)
        self.context.addItem('', True)
        self.context.currentIndexChanged.connect(self.invalidate)
        controls.addWidget(self.context)
        self.state = QComboBox()
        for value in ('normal', 'pressed', 'hover'):
            self.state.addItem('', value)
        self.state.currentIndexChanged.connect(self.invalidate)
        controls.addWidget(self.state)
        layout.addLayout(controls)
        tools = QHBoxLayout()
        self.zoom = QComboBox()
        for label, value in (('', 0), ('50%', .5), ('100%', 1), ('200%', 2), ('400%', 4)):
            self.zoom.addItem(label, value)
        self.zoom.currentIndexChanged.connect(self.update_image)
        tools.addWidget(self.zoom)
        self.refresh = QPushButton()
        self.refresh.clicked.connect(lambda: self.window.reload_resources())
        tools.addWidget(self.refresh)
        self.png = QPushButton()
        self.png.setEnabled(False)
        self.png.clicked.connect(self.export_dialog)
        tools.addWidget(self.png)
        layout.addLayout(tools)
        profile_tools = QHBoxLayout()
        self.scale_label = QLabel()
        profile_tools.addWidget(self.scale_label)
        self.ui_scale = QSpinBox()
        self.ui_scale.setRange(0, 100)
        self.ui_scale.setEnabled(False)
        self.ui_scale.valueChanged.connect(self.invalidate)
        profile_tools.addWidget(self.ui_scale)
        self.clients = QPushButton()
        self.clients.clicked.connect(self.show_clients)
        profile_tools.addWidget(self.clients)
        layout.addLayout(profile_tools)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.canvas)
        self.scroll.viewport().installEventFilter(self)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.details = QTreeWidget()
        self.details.setHeaderHidden(True)
        self.details.setMaximumHeight(180)
        self.details.setWordWrap(True)
        self.notice_groups = []
        self.details.hide()
        layout.addWidget(self.details)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.start)

    def active(self):
        return hasattr(self.pane, 'tabs') and self.pane.tabs.currentWidget() is self

    def retranslate(self):
        tr = self.window.t
        self.context.setItemText(0, tr('Только элемент'))
        self.context.setItemText(1, tr('В контексте родителя'))
        for i, key in enumerate(('Обычное состояние', 'Нажато', 'Под курсором')):
            self.state.setItemText(i, tr(key))
        self.zoom.setItemText(0, tr('Вписать'))
        self.refresh.setText(tr('Обновить'))
        self.png.setText(tr('Сохранить PNG'))
        self.clients.setText(tr('Поддерживаемые клиенты…'))
        self.scale_label.setText(tr('Уровень UI:'))
        self.ui_scale.setToolTip(tr('Индекс ScalableData 0–100; отдельно от масштаба просмотра.'))
        self.note.setText(tr('Статический макет: шрифты, локализованный текст и динамические состояния могут отличаться от игры.'))
        self.set_status(self.status_key, **self.status_values)
        self.show_notices(self.notice_groups)

    def show_clients(self):
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(self.window.t('Поддерживаемые клиенты…'))
        layout = QVBoxLayout(dialog)
        table = QTreeWidget()
        table.setHeaderLabels([self.window.t('Клиент'), self.window.t('Профиль')])
        for schema, label in PREVIEW_PROFILES.items():
            item = QTreeWidgetItem(table, [label, schema])
            detail = ('ScalableData: размеры и таблицы шрифтов; шрифты приблизительные.' if schema in SCALABLE_PREVIEW_SCHEMAS
                      else 'Статический макет; шрифты приблизительные.')
            QTreeWidgetItem(item, [self.window.t(detail)])
            if schema == 'ct24.XDAT':
                QTreeWidgetItem(item, [self.window.t('Фон Window стандартный; поля unk* не интерпретируются.')])
        table.resizeColumnToContents(0)
        layout.addWidget(table)
        note = QLabel(self.window.t('Контролы: Window, Button, Texture, TextBox, ScrollArea. Скрипты, анимации и 3D не исполняются.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.resize(620, 340)
        dialog.open()

    def show_notices(self, groups):
        expanded = {self.details.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
                    for i in range(self.details.topLevelItemCount()) if self.details.topLevelItem(i).isExpanded()}
        self.notice_groups = groups
        self.details.clear()
        for group in groups:
            entries = group['entries']
            count = len({entry['element'] for entry in entries if entry['element']}) or len(entries)
            item = QTreeWidgetItem(self.details, [self.window.t('{reason} — {count}', reason=self.window.t(group['reason']), count=count)])
            item.setData(0, Qt.ItemDataRole.UserRole, group['reason'])
            for entry in entries:
                name = entry['element'].rsplit('.', 1)[-1]
                text = ' — '.join(value for value in (name, entry['detail']) if value)
                child = QTreeWidgetItem(item, [text or self.window.t(group['reason'])])
                child.setToolTip(0, ' — '.join(value for value in (entry['element'], entry['detail']) if value) or child.text(0))
            item.setExpanded(group['reason'] in expanded)
        self.details.setVisible(bool(groups))

    def set_status(self, key, **values):
        self.status_key, self.status_values = key, values
        self.status.setText(self.window.t(key, **values))

    def invalidate(self, *_):
        self.generation += 1
        self.timer.stop()
        self.pending = True
        self.result = None
        self.png.setEnabled(False)
        self.canvas.clear()
        self.canvas.resize(1, 1)
        self.notice_groups = []
        self.details.hide()
        document = self.pane.document
        self.ui_scale.setEnabled(document is not None and document.summary()['schema'] in SCALABLE_PREVIEW_SCHEMAS)
        if self.active():
            self.set_status('Подготовка предпросмотра…')
            self.timer.start()

    def start(self):
        if not self.active():
            return
        if self.window.busy:
            self.timer.start()
            return
        if self.running:
            self.pending = True
            return
        document, node = self.pane.document, self.pane.node_id
        if document is None or node is None:
            self.pending = False
            self.set_status('Выберите элемент для предпросмотра')
            return
        if document.summary()['schema'] not in SUPPORTED_PREVIEW_SCHEMAS:
            self.pending = False
            self.set_status('Предпросмотр для этого профиля недоступен. Список — в кнопке «Поддерживаемые клиенты…».')
            return
        token = self.generation
        resources = self.window.preview_resources
        strings = self.window.strings.snapshot()
        string_generation = self.window.strings.generation
        context, state = self.context.currentData(), self.state.currentData()
        ui_scale = self.ui_scale.value() if document.summary()['schema'] in SCALABLE_PREVIEW_SCHEMAS else 0
        self.running, self.pending = True, False
        self.set_status('Загрузка ресурсов и отрисовка…')
        def render():
            return render_preview(document.preview_snapshot(node), resources, context, state, strings, ui_scale)
        def done(result, error):
            self.running = False
            current = token == self.generation and document is self.pane.document and node == self.pane.node_id and resources is self.window.preview_resources and string_generation == self.window.strings.generation
            if current and self.active() and not self.window.busy:
                if error:
                    self.set_status('Не удалось построить предпросмотр')
                    self.show_notices([dict(reason='Ошибка предпросмотра', entries=[dict(element='', detail=error)])])
                elif result.revision == document.summary()['revision']:
                    self.result = result
                    self.png.setEnabled(True)
                    self.update_image()
                    self.set_status('Размер: {width}×{height}; текстур: {textures}; замечаний: {warnings}',
                                    width=result.image.width(), height=result.image.height(), textures=len(result.textures), warnings=len(result.warnings))
                    self.show_notices(result.warning_groups)
                else:
                    self.pending = True
            elif self.active():
                self.pending = True
            if self.pending and self.active():
                self.timer.start()
        self.window.submit(render, done)

    def update_image(self, *_):
        if self.result is None:
            return
        image = self.result.image
        factor = self.zoom.currentData()
        if not factor:
            size = self.scroll.viewport().size()
            factor = min(8.0, max(.05, min((size.width() - 8) / image.width(), (size.height() - 8) / image.height())))
        width, height = max(1, round(image.width() * factor)), max(1, round(image.height() * factor))
        pixmap = QPixmap.fromImage(image).scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.canvas.setPixmap(pixmap)
        self.canvas.resize(pixmap.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'zoom') and not self.zoom.currentData():
            QTimer.singleShot(0, self.update_image)

    def eventFilter(self, watched, event):
        if hasattr(self, 'scroll') and watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            if not self.zoom.currentData():
                QTimer.singleShot(0, self.update_image)
        return super().eventFilter(watched, event)

    def export_dialog(self):
        if self.result is None:
            return
        name = self.pane.document.info(self.pane.node_id)['name']
        name = re.sub(r'[<>:"/\\|?*]', '_', name) or 'preview'
        filename, _ = QFileDialog.getSaveFileName(self, self.window.t('Сохранить предпросмотр в PNG'), name + '.png', 'PNG (*.png)')
        if filename:
            self.export_png(filename)

    def export_png(self, filename):
        if self.result is None:
            raise ValueError('No completed preview to export')
        image = self.result.image
        self.png.setEnabled(False)
        def done(_, error):
            self.png.setEnabled(self.result is not None)
            if error:
                self.window.error(error)
            else:
                self.window.statusBar().showMessage(self.window.t('PNG сохранён: {filename}', filename=str(filename)))
        self.window.submit(lambda: save_png(image, filename), done)

    def stop(self):
        self.generation += 1
        self.pending = False
        self.timer.stop()
