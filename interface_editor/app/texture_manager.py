"""User texture projects and HF button/texture assignment dialogs."""
from pathlib import Path
import re
import traceback

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog, QMessageBox,
    QDialogButtonBox, QFormLayout, QLineEdit, QComboBox, QSpinBox)

from texture_project import TextureProject, IDENTIFIER


class TextureBindingsDialog(QDialog):
    def __init__(self, editor, project, fields, selected=None, button=False):
        super().__init__(editor)
        self.editor, self.project, self.button = editor, project, button
        self.setWindowTitle(editor.t('Создать кнопку с текстурами') if button else editor.t('Назначить текстуры'))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = {}
        self.name = QLineEdit('btnNativeTest')
        self.caption = QLineEdit('Native test')
        self.caption_mode = QComboBox()
        self.caption_mode.addItem(editor.t('Прямой текст'), 'literal')
        self.caption_mode.addItem('SysString', 'sysstring')
        self.string_id = None
        self.string_label = QLabel()
        self.string_button = QPushButton(editor.t('Выбрать или создать строку…'))
        self.string_button.clicked.connect(self.choose_string)
        self.caption_mode.currentIndexChanged.connect(self.caption_controls)
        self.x, self.y, self.width, self.height = [QSpinBox() for _ in range(4)]
        for control in (self.x, self.y): control.setRange(-8192, 8192)
        for control in (self.width, self.height): control.setRange(1, 4096)
        chosen = project.asset(selected) if selected else project.data['assets'][0]
        self.width.setValue(chosen['content_width']); self.height.setValue(chosen['content_height'])
        if button:
            form.addRow(editor.t('Имя кнопки'), self.name)
            form.addRow(editor.t('Источник подписи'), self.caption_mode)
            form.addRow(editor.t('Подпись'), self.caption)
            form.addRow(self.string_button, self.string_label)
            for label, control in (('X', self.x), ('Y', self.y), ('Width', self.width), ('Height', self.height)):
                form.addRow(label, control)
        for i, field in enumerate(fields):
            combo = QComboBox()
            if not button: combo.addItem(editor.t('Не менять'), None)
            combo.addItem('undefined', 'undefined')
            for a in project.data['assets']:
                reference = project.reference(a)
                combo.addItem(reference, reference)
            if i == 0: combo.setCurrentIndex(combo.findData(project.reference(chosen)))
            self.fields[field] = combo
            form.addRow(field, combo)
        layout.addLayout(form)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.caption_controls()

    def caption_controls(self, *_):
        use_string = self.caption_mode.currentData() == 'sysstring'
        self.caption.setEnabled(not use_string)
        self.string_button.setEnabled(use_string)

    def choose_string(self):
        identifier = self.editor.select_string()
        if identifier is not None:
            self.string_id = identifier
            self.string_label.setText(str(identifier) + ': ' + (self.editor.strings.snapshot() or {}).get(identifier, ''))

    def validate(self):
        if self.button and not IDENTIFIER.fullmatch(self.name.text()):
            self.message.setText(self.editor.t('Имя: латинские буквы, цифры и подчёркивание'))
            return
        if self.button and self.fields['normalTex'].currentData() == 'undefined':
            self.message.setText(self.editor.t('Выберите обычную текстуру кнопки'))
            return
        if self.button and self.caption_mode.currentData() == 'sysstring' and self.string_id not in (self.editor.strings.snapshot() or {}):
            self.message.setText(self.editor.t('Выберите строку SysString'))
            return
        self.accept()

    def values(self):
        result = {name: combo.currentData() for name, combo in self.fields.items() if combo.currentData() is not None}
        if self.button:
            use_string = self.caption_mode.currentData() == 'sysstring'
            result.update(name=self.name.text(), buttonNameText='undefined' if use_string else self.caption.text(), buttonName=self.string_id if use_string else -9999,
                          size=1, size_absolute_values=1, size_absolute_width=self.width.value(),
                          size_absolute_height=self.height.value(), usePosition=1, relativePoint=1,
                          anchorPoint=1, relativeTo='', anchor_x=float(self.x.value()), anchor_y=float(self.y.value()))
        return result


class TextureManager(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.working = False
        self.thumbnail_token = 0
        self.setWindowTitle(editor.t('Пользовательские текстуры'))
        self.resize(950, 620)
        layout = QVBoxLayout(self)
        self.path = QLabel()
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path)
        tools = QHBoxLayout()
        self.buttons = {}
        for label, method in (('Новый проект', self.new_project), ('Открыть проект', self.open_project),
                              ('Добавить изображение', self.add_image), ('Заменить изображение', self.replace_image),
                              ('Собрать UTX', self.build), ('Установить в клиент', self.install)):
            button = QPushButton(editor.t(label))
            button.clicked.connect(method)
            self.buttons[label] = button
            tools.addWidget(button)
        layout.addLayout(tools)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.thumbnail)
        body.addWidget(self.list, 2)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(240, 200)
        body.addWidget(self.image, 1)
        layout.addLayout(body, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        for label, callback in (('Назначить выбранному элементу', lambda: editor.assign_project_textures(self.selected())),
                                ('Создать кнопку с текстурами', lambda: editor.create_texture_button(self.selected())),
                                ('Копировать имя текстуры', self.copy_reference)):
            button = QPushButton(editor.t(label))
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.refresh()

    @property
    def project(self):
        return self.editor.texture_project

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self, selected=None):
        selected = selected or self.selected()
        self.thumbnail_token += 1
        self.list.clear(); self.image.clear()
        project = self.project
        self.path.setText(str(project.file) if project else self.editor.t('Проект текстур не открыт'))
        if project:
            for a in project.data['assets']:
                item = QListWidgetItem(f"{project.reference(a)}   {a['content_width']}×{a['content_height']} → {a['width']}×{a['height']}")
                item.setData(Qt.ItemDataRole.UserRole, a['id'])
                self.list.addItem(item)
                if a['id'] == selected: self.list.setCurrentItem(item)
            if self.list.currentItem() is None and self.list.count(): self.list.setCurrentRow(0)
            self.status.setText(self.editor.t('UTX готов') if project.build_info() else self.editor.t('Нужна сборка UTX'))
        for key in ('Добавить изображение', 'Заменить изображение', 'Собрать UTX', 'Установить в клиент'):
            self.buttons[key].setEnabled(project is not None)

    def thumbnail(self, *_):
        self.thumbnail_token += 1
        token = self.thumbnail_token
        asset_id, project = self.selected(), self.project
        self.image.clear()
        if not asset_id or project is None: return
        filename = project.asset_path(project.asset(asset_id)['image'])
        def read():
            reader = QImageReader(str(filename))
            size = reader.size()
            reader.setScaledSize(size.scaled(QSize(300, 300), Qt.AspectRatioMode.KeepAspectRatio))
            return reader.read()
        def done(image, error):
            if token == self.thumbnail_token and self.isVisible() and not error and not image.isNull():
                self.image.setPixmap(QPixmap.fromImage(image))
        self.editor.submit(read, done)

    def work(self, function, completed=None):
        if self.working: return
        self.working = True
        self.setEnabled(False)
        self.editor.set_busy(True, 'Обработка текстур…')
        def done(value, error):
            self.working = False
            self.setEnabled(True)
            self.editor.set_busy(False)
            if error:
                self.editor.error(error)
            elif completed:
                completed(value)
            self.refresh()
        self.editor.submit(function, done)

    def use_project(self, project):
        self.editor.texture_project = project
        self.editor.settings.setValue('texture_project', str(project.file))
        self.editor.reload_resources()

    def new_project(self):
        parent = QFileDialog.getExistingDirectory(self, self.editor.t('Каталог нового проекта текстур'))
        if not parent: return
        name, ok = QInputDialog.getText(self, self.editor.t('Новый проект'), self.editor.t('Имя пакета'), text='L2UI_Custom')
        if ok:
            self.work(lambda: TextureProject.create(Path(parent) / name, name), self.use_project)

    def open_project(self):
        filename, _ = QFileDialog.getOpenFileName(self, self.editor.t('Открыть проект'), self.editor.settings.value('texture_project', ''), 'JSON (*.json)')
        if filename: self.work(lambda: TextureProject(filename), self.use_project)

    def image_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, self.editor.t('Выбрать изображение'), '', 'Images (*.png *.tga)')
        if not filename: return None
        reader = QImageReader(filename)
        size = reader.size()
        if not size.isValid():
            self.editor.error(reader.errorString()); return None
        w, h = size.width(), size.height()
        pad = bool(w & (w-1) or h & (h-1))
        if pad and QMessageBox.question(self, self.editor.t('Размер изображения'), self.editor.t('Дополнить изображение прозрачным полем до степени двойки?'),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return None
        return filename, pad

    def add_image(self):
        if self.project is None: return
        image = self.image_dialog()
        if not image: return
        name = re.sub(r'[^A-Za-z0-9_]', '_', Path(image[0]).stem)
        if not name or name[0].isdigit(): name = 'Texture_' + name
        name, ok = QInputDialog.getText(self, self.editor.t('Добавить изображение'), self.editor.t('Имя текстуры'), text=name[:63])
        if not ok: return
        group, ok = QInputDialog.getText(self, self.editor.t('Добавить изображение'), self.editor.t('Группа'), text='Buttons')
        if not ok: return
        project = self.project
        self.work(lambda: project.add_image(image[0], name, group, image[1]))

    def replace_image(self):
        if not self.selected(): return
        image = self.image_dialog()
        if not image: return
        project, asset = self.project, self.project.asset(self.selected())
        self.work(lambda: project.add_image(image[0], asset['name'], asset['group'], image[1], asset['id']))

    def build(self):
        if self.project is not None:
            self.work(self.project.build, lambda _: self.editor.reload_resources())

    def install(self):
        if self.project is None: return
        directory = QFileDialog.getExistingDirectory(self, self.editor.t('Выбрать SysTextures закрытого клиента'), self.editor.preview_resources.directory)
        if directory:
            self.work(lambda: self.project.install(directory), lambda result: self.editor.set_resources(str(result.parent)))

    def copy_reference(self):
        if self.selected():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.project.reference(self.project.asset(self.selected())))

    def closeEvent(self, event):
        if self.working:
            event.ignore()
        else:
            self.thumbnail_token += 1
            event.accept()
