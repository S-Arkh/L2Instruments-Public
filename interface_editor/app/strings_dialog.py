"""SysString editor. Envelope, record schema and displayed language are separate."""
import json
from pathlib import Path
import traceback

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QPushButton, QLineEdit, QTableView, QHeaderView, QFileDialog,
    QMessageBox, QDialogButtonBox, QSpinBox, QPlainTextEdit, QCheckBox)
from _interface_core import dat_codecs, sysstring_schemas, register_dat_profile
from localization import StringCatalog


class StringRows(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent); self.rows = []

    def update(self, rows):
        self.beginResetModel(); self.rows = rows; self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self, parent=QModelIndex()): return 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return str(self.rows[index.row()]['id']) if index.column() == 0 else self.rows[index.row()]['text']
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ('ID', self.parent().editor.t('Текст'))[section]
        return None


class StringEditDialog(QDialog):
    def __init__(self, editor, identifier=None, translations=False):
        super().__init__(editor)
        self.editor = editor
        self.setWindowTitle(editor.t('Новая строка' if identifier is None else 'Редактирование строки'))
        layout = QVBoxLayout(self); form = QFormLayout()
        self.identifier = QSpinBox(); self.identifier.setRange(0, 2147483647)
        self.identifier.setValue(editor.strings.suggest_id() if identifier is None else identifier)
        self.identifier.setEnabled(identifier is None)
        form.addRow('ID', self.identifier)
        self.all_languages = QCheckBox(editor.t('Все загруженные языки'))
        self.all_languages.setChecked(translations)
        self.all_languages.setEnabled(len(editor.strings.entries) > 1)
        form.addRow(self.all_languages)
        self.edits = {}
        for entry in editor.strings.entries:
            edit = QPlainTextEdit()
            edit.setMaximumHeight(90)
            if identifier is not None:
                edit.setPlainText(entry['table'].lookup(identifier) or '')
            self.edits[entry['id']] = edit
            form.addRow(entry['language'] + ' — ' + Path(entry['info']['file']).name, edit)
        layout.addLayout(form)
        self.all_languages.toggled.connect(self.enable_fields)
        self.enable_fields()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def enable_fields(self, *_):
        for key, edit in self.edits.items():
            edit.setEnabled(self.all_languages.isChecked() or key == self.editor.strings.active_id)

    def values(self):
        return {key: edit.toPlainText() for key, edit in self.edits.items() if edit.isEnabled()}


class LoadStringsDialog(QDialog):
    def __init__(self, editor, filename):
        super().__init__(editor)
        self.setWindowTitle(editor.t('Параметры SysString'))
        layout = QVBoxLayout(self); form = QFormLayout()
        self.schema = QComboBox()
        for item in sysstring_schemas(): self.schema.addItem(item['name'], item['id'])
        suffix = Path(filename).stem.rsplit('-', 1)[-1].lower()
        label = {'e': 'English', 'en': 'English', 'ru': 'Русский', 'r': 'Русский', 'kr': 'Korean', 'k': 'Korean', 'j': 'Japanese', 'jp': 'Japanese', 'cn': 'Chinese', 'c': 'Chinese', 'tw': 'Chinese (Traditional)'}.get(suffix, suffix)
        self.language = QLineEdit(label)
        self.encoding = QComboBox()
        for name in ('cp1252', 'cp1251', 'cp949', 'cp932', 'cp936', 'cp950', 'utf-8', 'latin1'): self.encoding.addItem(name, name)
        encoding = {'r': 'cp1251', 'ru': 'cp1251', 'k': 'cp949', 'kr': 'cp949', 'j': 'cp932', 'jp': 'cp932', 'cn': 'cp936', 'c': 'cp936', 'tw': 'cp950'}.get(suffix, 'cp1252')
        self.encoding.setCurrentText(encoding)
        self.profile = QComboBox()
        for text, key in ((editor.t('Авто (по заголовку)'), 'auto'), (editor.t('Без оболочки'), 'plain'), ('RSA: L2EncDec', 'l2encdec'), (editor.t('RSA: оригинальные ключи'), 'original')):
            self.profile.addItem(text, key)
        for name in sorted({p['profile'] for p in dat_codecs() if p['profile'].startswith('custom-')}): self.profile.addItem(name, name)
        form.addRow(editor.t('Схема данных'), self.schema)
        form.addRow(editor.t('Язык текста'), self.language)
        form.addRow(editor.t('Кодировка ANSI'), self.encoding)
        form.addRow(editor.t('Профиль чтения'), self.profile)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)


class StringsDialog(QDialog):
    def __init__(self, editor, select=False):
        super().__init__(editor)
        self.editor, self.catalog = editor, editor.strings
        self.select_mode, self.selected_id = select, None
        self.working, self.refreshing = False, False
        self.last_entry = None
        self.setWindowTitle(editor.t('Строки интерфейса'))
        self.resize(1000, 700)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.language = QComboBox(); top.addWidget(self.language, 1)
        self.language.activated.connect(lambda _: self.catalog.activate(self.language.currentData()))
        for label, function in (('Открыть DAT…', self.open_file), ('Импорт профиля ключей…', self.import_profile)):
            button = QPushButton(editor.t(label)); button.clicked.connect(function); top.addWidget(button)
        layout.addLayout(top)
        self.info = QLabel(); self.info.setWordWrap(True); self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); layout.addWidget(self.info)
        self.search = QLineEdit(); self.search.setPlaceholderText(editor.t('Поиск ID или текста…')); self.search.setClearButtonEnabled(True); layout.addWidget(self.search)
        self.model = StringRows(self)
        self.proxy = QSortFilterProxyModel(self); self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive); self.proxy.setFilterKeyColumn(-1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.table = QTableView(); self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.choose() if self.select_mode else self.edit_row())
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for label, function in (('Добавить строку', self.add_row), ('Изменить текст', self.edit_row), ('Переводы строки', lambda: self.edit_row(True)),
                                ('Отменить строку', lambda: self.history(False)), ('Повторить строку', lambda: self.history(True))):
            button = QPushButton(editor.t(label)); button.clicked.connect(function); actions.addWidget(button)
        layout.addLayout(actions)
        output = QHBoxLayout()
        output.addWidget(QLabel(editor.t('Оболочка записи')))
        self.version = QComboBox(); self.version.addItem(editor.t('Исходная'), -1)
        for v in (0, 111, 120, 121, 211, 212, 411, 412, 413, 414): self.version.addItem('plain' if v == 0 else str(v), v)
        output.addWidget(self.version)
        self.write_profile = QComboBox(); output.addWidget(self.write_profile)
        self.save_button = QPushButton(editor.t('Сохранить DAT')); self.save_button.clicked.connect(lambda: self.save(False)); output.addWidget(self.save_button)
        self.save_as_button = QPushButton(editor.t('Сохранить DAT как…')); self.save_as_button.clicked.connect(lambda: self.save(True)); output.addWidget(self.save_as_button)
        layout.addLayout(output)
        self.version.currentIndexChanged.connect(self.write_profiles)
        self.write_profile.currentIndexChanged.connect(self.save_state)
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        bottom = QHBoxLayout()
        choose = QPushButton(editor.t('Использовать ID' if select else 'Назначить выбранному элементу'))
        choose.clicked.connect(self.choose); bottom.addWidget(choose)
        close = QPushButton(editor.t('Закрыть')); close.clicked.connect(self.reject); bottom.addWidget(close)
        layout.addLayout(bottom)
        self.catalog.changed.connect(self.refresh)
        self.refresh()

    def identifier(self):
        index = self.proxy.mapToSource(self.table.currentIndex())
        return self.model.rows[index.row()]['id'] if index.isValid() else None

    def refresh(self):
        if self.refreshing: return
        self.refreshing = True
        selected = self.identifier()
        self.language.blockSignals(True); self.language.clear()
        for entry in self.catalog.entries:
            label = ('* ' if entry['info']['dirty'] else '') + entry['language'] + ' — ' + entry['info']['file']
            self.language.addItem(label, entry['id'])
        self.language.setCurrentIndex(self.language.findData(self.catalog.active_id)); self.language.blockSignals(False)
        entry = self.catalog.active
        self.model.update(entry['rows'] if entry else [])
        if entry:
            info = entry['info']
            envelope = 'plain' if info['version'] == 0 else 'Lineage2Ver' + str(info['version'])
            counts = self.editor.t('Строк: {count}; хвост: {tail} байт', count=info['rows'], tail=len(info['table_tail_hex'])//2)
            self.info.setText(f"{info['file']}\n{info['schema']} · {info['encoding']} · {envelope} · {info['profile']} · {counts}")
            if entry['id'] != self.last_entry:
                self.version.setCurrentIndex(0)
                self.write_profiles()
                self.last_entry = entry['id']
            if selected is not None:
                for row, value in enumerate(entry['rows']):
                    if value['id'] == selected:
                        self.table.setCurrentIndex(self.proxy.mapFromSource(self.model.index(row, 0))); break
        else:
            self.info.setText(self.editor.t('Таблица строк не открыта'))
        self.refreshing = False
        self.save_state()

    def write_profiles(self, *_):
        self.write_profile.blockSignals(True); self.write_profile.clear()
        self.write_profile.addItem(self.editor.t('Исходный профиль'), 'preserve')
        entry = self.catalog.active
        if entry:
            version = self.version.currentData()
            if version == -1: version = entry['info']['version']
            for p in dat_codecs():
                if p['version'] == version and p['write']: self.write_profile.addItem(p['profile'], p['profile'])
        self.write_profile.blockSignals(False); self.save_state()

    def save_state(self, *_):
        entry = self.catalog.active
        allowed = bool(entry) and not self.working
        if entry:
            info = entry['info']; version = self.version.currentData()
            if version == -1: version = info['version']
            profile = self.write_profile.currentData()
            if profile == 'preserve': profile = info['profile']
            allowed = allowed and not info['ambiguous_padding'] and (version < 411 or
                any(p['version'] == version and p['profile'] == profile and p['write'] for p in dat_codecs()) or
                (version == info['version'] and profile == info['profile'] and not info['dirty']))
            reason = 'Нераспознанный хвост Blowfish: запись отключена' if info['ambiguous_padding'] else 'Выберите совместимый профиль записи: исходный профиль доступен только для чтения'
            self.status.setText(self.editor.t(reason) if not allowed and not self.working else
                                self.editor.t('Есть несохранённые строки' if info['dirty'] else 'Строки сохранены'))
        self.save_button.setEnabled(allowed); self.save_as_button.setEnabled(allowed)

    def work(self, function, callback):
        if self.working: return
        self.working = True; self.setEnabled(False); self.editor.set_busy(True, 'Обработка SysString…')
        def done(value, error):
            self.working = False; self.setEnabled(True); self.editor.set_busy(False)
            if error: self.editor.error(error)
            else:
                try: callback(value)
                except Exception: self.editor.error(traceback.format_exc())
            self.refresh()
        self.editor.submit(function, done)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, self.editor.t('Открыть SysString'), self.editor.settings.value('sysstrings/active_file', ''), 'DAT (*.dat);;All files (*)')
        if not filename: return
        dialog = LoadStringsDialog(self.editor, filename)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            schema, encoding, profile, language = dialog.schema.currentData(), dialog.encoding.currentData(), dialog.profile.currentData(), dialog.language.text()
            self.work(lambda: StringCatalog.load_file(filename, schema, encoding, profile), lambda table: self.catalog.attach(table, language))
        dialog.deleteLater()

    def import_profile(self):
        filename, _ = QFileDialog.getOpenFileName(self, self.editor.t('Импорт профиля ключей…'), '', 'JSON (*.json)')
        if filename:
            try:
                register_dat_profile(json.loads(Path(filename).read_text(encoding='utf-8')))
                profiles = self.editor.settings.value('sysstrings/key_files', [])
                if isinstance(profiles, str): profiles = [profiles]
                self.editor.settings.setValue('sysstrings/key_files', list(dict.fromkeys([*profiles, filename])))
                self.write_profiles()
            except Exception: self.editor.error(traceback.format_exc())

    def add_row(self):
        if not self.catalog.active: return
        dialog = StringEditDialog(self.editor)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                identifier = dialog.identifier.value()
                self.catalog.change_translations(identifier, dialog.values(), new=True)
                self.select_id(identifier)
            except Exception: self.editor.error(traceback.format_exc())
        dialog.deleteLater()

    def select_id(self, identifier):
        for row, item in enumerate(self.model.rows):
            if item['id'] == identifier:
                source = self.model.index(row, 0)
                index = self.proxy.mapFromSource(source)
                if not index.isValid():
                    self.search.clear()
                    index = self.proxy.mapFromSource(source)
                self.table.setCurrentIndex(index)
                self.table.scrollTo(index)
                break

    def edit_row(self, translations=False):
        identifier = self.identifier()
        if identifier is None: return
        dialog = StringEditDialog(self.editor, identifier, translations)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try: self.catalog.change_translations(identifier, dialog.values())
            except Exception: self.editor.error(traceback.format_exc())
        dialog.deleteLater()

    def history(self, redo):
        entry = self.catalog.active
        if entry:
            (entry['table'].redo if redo else entry['table'].undo)()
            self.catalog.refresh(entry)

    def save(self, save_as):
        entry = self.catalog.active
        if not entry: return
        filename = entry['info']['file']
        if save_as:
            filename, _ = QFileDialog.getSaveFileName(self, self.editor.t('Сохранить SysString'), filename, 'DAT (*.dat)')
        if filename:
            version, profile = self.version.currentData(), self.write_profile.currentData()
            self.work(lambda: entry['table'].save(filename, version, profile), lambda _: self.catalog.refresh(entry))

    def choose(self):
        identifier = self.identifier()
        if identifier is None: return
        if self.select_mode:
            self.selected_id = identifier; self.accept()
        else:
            self.editor.assign_string_id(identifier)

    def reject(self):
        if not self.working: super().reject()

    def closeEvent(self, event):
        if self.working: event.ignore()
        else: event.accept()
