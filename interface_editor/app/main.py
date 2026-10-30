"""Desktop XDAT editor: C++ document, two independent PySide6 views."""
import json
import math
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, QSettings, QTranslator, QLibraryInfo, QStandardPaths
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTreeView, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox, QInputDialog,
    QAbstractItemView, QProgressBar, QScrollBar, QMenu, QToolButton, QTabWidget, QDialog,
)
from _interface_core import Document
from model import TreeModel, TreeFilter
from comparison import align_properties, ORANGE, RED
from i18n import text
from wheel_guard import PropertyWheelGuard
from preview_render import ResourceCache
from preview_widget import PreviewWidget
from texture_project import TextureProject
from texture_manager import TextureManager, TextureBindingsDialog
from localization import StringCatalog
from strings_dialog import StringsDialog
from _interface_core import register_dat_profile
from schema_tools import load_schemas
from schema_dialog import analyze

ROOT = Path(__file__).resolve().parents[1]


class Signals(QObject):
    done = Signal(object, object)


class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            self.signals.done.emit(self.function(), None)
        except Exception:
            self.signals.done.emit(None, traceback.format_exc())


class Pane(QWidget):
    edit_requested = Signal(int, str, object)
    selected = Signal(object)

    def __init__(self, side, window):
        super().__init__()
        self.window = window
        self.side = side
        self.title_key = 'Левая область' if side == 'left' else 'Правая область'
        self.note_key = None
        self.note_values = {}
        self.document = None
        self.model = None
        self.node_id = None
        self.props = []
        self.all_props = []
        self.rendered_props = []
        self.property_names = []
        self.loading = False
        self.generation = 0
        self.expanded_ids = set()
        self.restoring = False
        self.search_busy = False
        self.pending_query = None
        layout = QVBoxLayout(self)
        self.title_label = QLabel()
        layout.addWidget(self.title_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Поиск по имени или типу…')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.options_menu = QMenu(self)
        self.options_button = QToolButton()
        self.options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.options_button.setMenu(self.options_menu)
        self.neighbors = QAction(self)
        self.neighbors.setCheckable(True)
        legacy = window.settings.value(f'{self.title_key}/neighbors', False, type=bool)
        self.neighbors.setChecked(window.settings.value(f'panes/{side}/neighbors', legacy, type=bool))
        self.neighbors.toggled.connect(self.query_changed)
        self.neighbors.toggled.connect(lambda value: window.settings.setValue(f'panes/{side}/neighbors', value))
        self.options_menu.addAction(self.neighbors)
        options_row = QHBoxLayout()
        options_row.addWidget(self.options_button)
        options_row.addStretch()
        layout.addLayout(options_row)
        self.note = QLabel('')
        layout.addWidget(self.note)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeView()
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        split.addWidget(self.tree)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Свойство', 'Значение'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self.property_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.property_menu)
        self.table.verticalScrollBar().valueChanged.connect(lambda value: window.scroll_from_table(self, value))
        self.table.verticalScrollBar().rangeChanged.connect(lambda *_: window.refresh_shared_scroll())
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, '')
        self.preview = PreviewWidget(self)
        self.tabs.addTab(self.preview, '')
        self.tabs.currentChanged.connect(self.tab_changed)
        split.addWidget(self.tabs)
        split.setSizes([330, 400])
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        self.command_buttons = []
        for label, command in [('Добавить', 'add'), ('Копировать', 'copy'), ('Вставить копию', 'paste'), ('Дублировать', 'duplicate'), ('Удалить', 'delete')]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, cmd=command: window.command(self, cmd))
            self.command_buttons.append((button, label))
            actions.addWidget(button)
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self.start_search)
        self.search.textChanged.connect(self.query_changed)
        self.tree.expanded.connect(lambda index: self.track_expansion(index, True))
        self.tree.collapsed.connect(lambda index: self.track_expansion(index, False))

    def retranslate(self):
        tr = self.window.t
        self.title_label.setText(tr(self.title_key))
        self.search.setPlaceholderText(tr('Поиск по имени или типу…'))
        self.options_button.setText(tr('Опции окна'))
        self.options_menu.setTitle(tr('Опции окна'))
        self.neighbors.setText(tr('Показывать соседей и их ветки'))
        self.table.setHorizontalHeaderLabels([tr('Свойство'), tr('Значение')])
        self.tabs.setTabText(0, tr('Свойства'))
        self.tabs.setTabText(1, tr('Предпросмотр'))
        self.preview.retranslate()
        for button, label in self.command_buttons:
            button.setText(tr(label))
        self.set_note(self.note_key, **self.note_values)

    def set_note(self, key=None, **values):
        self.note_key, self.note_values = key, values
        self.note.setText(self.window.t(key, **values) if key else '')

    def track_expansion(self, index, expanded):
        if self.restoring or self.search.text():
            return
        node = index.data(Qt.ItemDataRole.UserRole)
        if expanded:
            self.expanded_ids.add(node)
        else:
            self.expanded_ids.discard(node)

    def set_document(self, document, model):
        self.generation += 1
        self.document, self.model = document, model
        self.node_id = None
        self.expanded_ids.clear()
        old_proxy = getattr(self, 'proxy', None)
        self.proxy = TreeFilter(self)
        self.proxy.setSourceModel(model)
        self.tree.setModel(self.proxy)
        if old_proxy:
            old_proxy.setSourceModel(None)
            old_proxy.deleteLater()
        self.tree.selectionModel().currentChanged.connect(self.selection_changed)
        self.tree.setColumnWidth(0, 230)
        self.table.setRowCount(0)
        self.search.clear()
        model.fetchMore(model.index_for_id(model.root.data['id']))

    def selection_changed(self, current, previous):
        if self.restoring:
            return
        self.node_id = current.data(Qt.ItemDataRole.UserRole) if current.isValid() else None
        self.show_properties()
        self.selected.emit(self)

    def show_properties(self):
        self.window.refresh_properties()
        self.preview.invalidate()

    def tab_changed(self, *_):
        self.window.refresh_properties()
        if self.preview.active():
            self.preview.invalidate()
        else:
            self.preview.stop()

    def render_properties(self, rows, side, highlight):
        self.loading = True
        try:
            self.rendered_props = [row['fields'][side] for row in rows]
            self.property_names = [row['name'] for row in rows]
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows))
            for row, description in enumerate(rows):
                prop = description['fields'][side]
                color = (RED if description['status'] == 'missing' else ORANGE if description['status'] == 'different' else None) if highlight else None
                tooltip = self.window.t('Значения или типы отличаются') if description['status'] == 'different' else ''
                name = QTableWidgetItem(description['name'])
                name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 0, name)
                if color:
                    name.setBackground(QColor(color))
                    name.setForeground(QColor('#111111'))
                if prop is None:
                    item = QTableWidgetItem(self.window.t('Нет поля'))
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setToolTip(self.window.t(description['reasons'][side]))
                    name.setToolTip(self.window.t(description['reasons'][side]))
                    if color:
                        item.setBackground(QColor(color))
                        item.setForeground(QColor('#111111'))
                    self.table.setItem(row, 1, item)
                    continue
                if description['status'] == 'missing':
                    tooltip = self.window.t('На другой стороне: {reason}', reason=self.window.t(description['reasons'][1 - side]))
                name.setToolTip(tooltip)
                value = prop['value']
                if prop['enum'] or prop['kind'] == 'bool':
                    combo = QComboBox()
                    options = prop['enum'] or [dict(label=self.window.t('Не задано (-1)'), value=-1), dict(label=self.window.t('Нет (0)'), value=0), dict(label=self.window.t('Да (1)'), value=1)]
                    for option in options:
                        combo.addItem(f"{option['label']} ({option['value']})" if prop['enum'] else option['label'], option['value'])
                    index = combo.findData(value)
                    if index < 0:
                        combo.addItem(self.window.t('Неизвестное: {value}', value=value), value)
                        index = combo.count() - 1
                    combo.setCurrentIndex(index)
                    combo.setEnabled(not prop['readonly'])
                    combo.setToolTip(tooltip)
                    if color:
                        combo.setStyleSheet(f'QComboBox {{ background-color: {color}; color: #111111; }}')
                    combo.activated.connect(lambda i, c=combo, p=prop: self.edit_requested.emit(self.node_id, p['name'], c.itemData(i)))
                    self.table.setCellWidget(row, 1, combo)
                else:
                    text = f'0x{value:08X}' if prop['kind'] in ('color', 'rgba') else str(value)
                    item = QTableWidgetItem(text)
                    if prop['readonly'] or isinstance(value, float) and not math.isfinite(value):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setToolTip(self.window.t('{kind} — изменения применяются после Enter. {details}', kind=prop['kind'], details=tooltip))
                    if color:
                        item.setBackground(QColor(color))
                        item.setForeground(QColor('#111111'))
                    self.table.setItem(row, 1, item)
        finally:
            self.loading = False

    def property_changed(self, item):
        if self.loading or item.column() != 1 or not self.node_id:
            return
        prop = self.rendered_props[item.row()]
        if prop is None:
            return
        try:
            text = item.text()
            value = text if prop['kind'] == 'string' else float(text) if prop['kind'] == 'float' else int(text, 16 if text.lower().startswith('0x') else 10)
        except ValueError:
            self.window.error(self.window.t('Неверный формат значения'))
            self.show_properties()
            return
        self.edit_requested.emit(self.node_id, prop['name'], value)

    def property_menu(self, position):
        index = self.table.indexAt(position)
        if not index.isValid() or index.row() >= len(self.rendered_props): return
        prop = self.rendered_props[index.row()]
        if prop and prop['kind'] == 'int' and not prop['readonly'] and not prop['enum'] and prop['name'] in ('buttonName', 'sysstring', 'title', 'tooltipText', 'popupValue', 'tooltip', 'textStringId'):
            menu = QMenu(self)
            action = menu.addAction(self.window.t('Выбрать строку SysString…'))
            action.triggered.connect(lambda: self.window.choose_string_for_field(self, prop['name']))
            menu.exec(self.table.viewport().mapToGlobal(position))
            menu.deleteLater()

    def query_changed(self, *_):
        self.generation += 1
        self.timer.start()

    def start_search(self):
        if not self.document:
            return
        if self.window.busy:
            self.timer.start()
            return
        query = self.search.text().strip()
        if self.search_busy:
            self.pending_query = query
            return
        self.pending_query = None
        if not query:
            self.restoring = True
            try:
                self.proxy.set_visible(None)
                self.tree.viewport().update()
            finally:
                self.restoring = False
            self.set_note()
            self.restore()
            return
        generation = self.generation
        document = self.document
        neighbors = self.neighbors.isChecked()
        self.search_busy = True
        self.set_note('Поиск…')
        def done(result, error):
            self.search_busy = False
            if generation == self.generation and document is self.document:
                if error:
                    self.set_note('Ошибка поиска')
                    self.window.error(error)
                else:
                    self.restoring = True
                    try:
                        # Materialize only paths to the first matches, not the entire tree.
                        for node_id in result['matches'][:200]:
                            self.model.index_for_id(node_id)
                        self.proxy.set_visible(result['visible'], result['matches'])
                        self.tree.viewport().update()
                        for node_id in result['matches'][:200]:
                            index = self.proxy.mapFromSource(self.model.index_for_id(node_id))
                            parent = index.parent()
                            while parent.isValid():
                                self.tree.expand(parent)
                                parent = parent.parent()
                        self.set_note('Совпадений: {count}. Автораскрытие: до 200.', count=len(result['matches']))
                    finally:
                        self.restoring = False
            if self.pending_query is not None:
                self.start_search()
        self.window.submit(lambda: document.search(query, neighbors), done)

    def reveal(self, node_id):
        """Display an existing object without mutating the shared document."""
        clear_filter = self.search_busy or self.timer.isActive() or (self.proxy.visible is not None and node_id not in self.proxy.visible)
        self.generation += 1
        self.timer.stop()
        self.pending_query = None
        self.restoring = True
        try:
            if clear_filter:
                self.search.clear()
                self.timer.stop()
                self.proxy.set_visible(None)
                self.set_note()
            index = self.proxy.mapFromSource(self.model.index_for_id(node_id))
            parent = index.parent()
            while parent.isValid():
                self.tree.expand(parent)
                self.expanded_ids.add(parent.data(Qt.ItemDataRole.UserRole))
                parent = parent.parent()
            self.node_id = node_id
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)
        finally:
            self.restoring = False
        self.show_properties()

    def restore(self):
        self.restoring = True
        try:
            for node_id in self.expanded_ids.copy():
                try:
                    self.tree.expand(self.proxy.mapFromSource(self.model.index_for_id(node_id)))
                except RuntimeError:
                    self.expanded_ids.discard(node_id)
            if self.node_id:
                try:
                    index = self.proxy.mapFromSource(self.model.index_for_id(self.node_id))
                    if index.isValid():
                        self.tree.setCurrentIndex(index)
                except RuntimeError:
                    self.node_id = None
        finally:
            self.restoring = False
        self.show_properties()


class Editor(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle('Interface Editor — C++ / Python')
        self.resize(1600, 900)
        self.user_schema_directory = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)) / 'L2Tools' / 'InterfaceEditor' / 'schemas'
        self.schema_text, self.schema_errors = load_schemas(ROOT / 'schemas/schemas.json', self.user_schema_directory)
        self.document = None
        self.model = None
        self.clipboard_id = None
        self.active = None
        self.tasks = set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.busy = False
        self._properties_guard = False
        self._scroll_guard = False
        self.settings = settings if settings is not None else QSettings('L2Tools', 'InterfaceEditor')
        if settings is None and not self.settings.value('migration_complete', False, type=bool):
            previous = QSettings('L2Tools', 'XdatEditorNative')
            project_root = ROOT.parent.parent if ROOT.parent.name == 'dist' else ROOT
            for key in previous.allKeys():
                if not self.settings.contains(key):
                    value = previous.value(key)
                    if isinstance(value, str):
                        normalized = value.replace('\\', '/')
                        old_root = (project_root.parent / 'xdat_editor').as_posix()
                        if normalized.casefold().startswith(old_root.casefold() + '/'):
                            value = project_root.as_posix() + normalized[len(old_root):]
                    self.settings.setValue(key, value)
            self.settings.setValue('migration_complete', True)
        self.preview_resources = ResourceCache(self.settings.value('resource_directory', ''))
        self.texture_project = None
        self.strings = StringCatalog(self.settings, self)
        self.strings.changed.connect(self.strings_changed)
        self.language = self.settings.value('language', 'ru')
        if self.language not in ('ru', 'en'):
            self.language = 'ru'
        self.qt_translator = None
        self.bar = self.addToolBar('Файл и правка')
        bar = self.bar
        self.version = QComboBox()
        for label, schema in json.loads(self.schema_text)['versions']:
            self.version.addItem(label, schema)
        self.version.setCurrentIndex(max(0, self.version.findData('ct26.XDAT')))
        bar.addWidget(self.version)
        self.file_menu = QMenu(self)
        self.file_button = self.menu_button(bar, self.file_menu)
        self.open_action = self.action(self.file_menu, 'Открыть', self.open_file, QKeySequence.StandardKey.Open)
        self.save_action = self.action(self.file_menu, 'Сохранить', self.save_file, QKeySequence.StandardKey.Save)
        self.save_as_action = self.action(self.file_menu, 'Сохранить как', lambda: self.save_file(True), QKeySequence.StandardKey.SaveAs)
        self.file_menu.addSeparator()
        self.open_json_action = self.action(self.file_menu, 'Открыть JSON', self.open_json_dialog)
        self.export_json_action = self.action(self.file_menu, 'Экспорт JSON', self.export_json_dialog)
        self.options_menu = QMenu(self)
        self.options_button = self.menu_button(bar, self.options_menu)
        self.texture_menu = QMenu(self)
        self.texture_button = self.menu_button(bar, self.texture_menu)
        self.action(self.texture_menu, 'Менеджер текстур…', self.open_texture_manager)
        self.action(self.texture_menu, 'Назначить текстуры…', self.assign_project_textures)
        self.action(self.texture_menu, 'Создать кнопку с текстурами', self.create_texture_button)
        self.strings_menu = QMenu(self)
        self.strings_button = self.menu_button(bar, self.strings_menu)
        self.action(self.strings_menu, 'Редактор строк…', self.open_strings)
        self.action(self.strings_menu, 'Выбрать строку для элемента…', self.choose_and_assign_string)
        self.string_language_menu = self.strings_menu.addMenu('')
        self.string_language_group = QActionGroup(self)
        self.string_language_group.setExclusive(True)
        self.sync_scroll = QAction(self)
        self.sync_scroll.setProperty('translation_key', 'Синхронная прокрутка свойств')
        self.sync_scroll.setCheckable(True)
        self.sync_scroll.setChecked(self.settings.value('sync_scroll', True, type=bool))
        self.options_menu.addAction(self.sync_scroll)
        self.wheel_values = QAction(self)
        self.wheel_values.setProperty('translation_key', 'Изменять значения свойств колёсиком')
        self.wheel_values.setCheckable(True)
        self.wheel_values.setChecked(self.settings.value('wheel_values', False, type=bool))
        self.wheel_values.toggled.connect(lambda value: self.settings.setValue('wheel_values', value))
        self.options_menu.addAction(self.wheel_values)
        self.resources_action = self.action(self.options_menu, 'Каталог ресурсов клиента…', self.choose_resources)
        self.reload_resources_action = self.action(self.options_menu, 'Перезагрузить ресурсы', self.reload_resources)
        self.options_menu.addSeparator()
        self.language_menu = self.options_menu.addMenu('')
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.language_actions = {}
        for code, label in (('ru', 'Русский'), ('en', 'English')):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(code == self.language)
            action.triggered.connect(lambda checked=False, lang=code: self.set_language(lang))
            self.language_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[code] = action
        bar.addSeparator()
        self.undo_action = self.action(bar, 'Отменить', lambda: self.history(False), QKeySequence.StandardKey.Undo)
        self.redo_action = self.action(bar, 'Повторить', lambda: self.history(True), QKeySequence.StandardKey.Redo)
        self.addToolBarBreak()
        self.view_bar = self.addToolBar('Сопоставление')
        self.to_right = self.action(self.view_bar, 'Слева → направо', lambda: self.transfer(0, 1))
        self.to_left = self.action(self.view_bar, 'Справа → налево', lambda: self.transfer(1, 0))
        self.compare_action = QAction('Сравнить', self)
        self.compare_action.setProperty('translation_key', 'Сравнить')
        self.compare_action.setCheckable(True)
        self.compare_action.setChecked(self.settings.value('compare', False, type=bool))
        self.view_bar.addAction(self.compare_action)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.panes = [Pane('left', self), Pane('right', self)]
        for pane in self.panes:
            self.split.addWidget(pane)
            pane.edit_requested.connect(self.edit)
            pane.selected.connect(self.pane_selected)
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self.split, 1)
        self.shared_scroll = QScrollBar(Qt.Orientation.Vertical)
        self.shared_scroll.setRange(0, 0)
        self.shared_scroll.setToolTip('Общая прокрутка свойств слева и справа')
        self.shared_scroll.valueChanged.connect(self.scroll_both)
        central_layout.addWidget(self.shared_scroll)
        self.setCentralWidget(central)
        self.sync_scroll.toggled.connect(self.refresh_properties)
        self.sync_scroll.toggled.connect(lambda value: self.settings.setValue('sync_scroll', value))
        self.compare_action.toggled.connect(self.refresh_properties)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.update_actions()
        geometry = self.settings.value('geometry')
        if geometry:
            self.restoreGeometry(geometry)
        splitter = self.settings.value('splitter')
        if splitter:
            self.split.restoreState(splitter)
        self.wheel_guard = PropertyWheelGuard(self)
        self.set_language(self.language)
        self.strings_restore_timer = QTimer(self)
        self.strings_restore_timer.setSingleShot(True)
        self.strings_restore_timer.timeout.connect(self.restore_strings)
        self.strings_restore_timer.start(0)

    def t(self, source, **values):
        return text(self.language, source, **values)

    def menu_button(self, toolbar, menu):
        button = QToolButton()
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        toolbar.addWidget(button)
        return button

    def set_language(self, language):
        if language not in ('ru', 'en'):
            raise ValueError('Unsupported UI language')
        self.language = language
        self.settings.setValue('language', language)
        app = QApplication.instance()
        if self.qt_translator:
            app.removeTranslator(self.qt_translator)
            self.qt_translator.deleteLater()
            self.qt_translator = None
        if language == 'ru':
            translator = QTranslator(self)
            if translator.load('qtbase_ru', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
                app.installTranslator(translator)
                self.qt_translator = translator
            else:
                translator.deleteLater()
        self.language_actions[language].setChecked(True)
        for action in self.findChildren(QAction):
            key = action.property('translation_key')
            if key:
                action.setText(self.t(key))
        self.bar.setWindowTitle(self.t('Файл и правка'))
        self.view_bar.setWindowTitle(self.t('Сопоставление'))
        self.file_menu.setTitle(self.t('Файл'))
        self.file_button.setText(self.t('Файл'))
        self.options_menu.setTitle(self.t('Опции'))
        self.options_button.setText(self.t('Опции'))
        self.texture_button.setText(self.t('Текстуры'))
        self.texture_menu.setTitle(self.t('Текстуры'))
        self.strings_button.setText(self.t('Строки'))
        self.strings_menu.setTitle(self.t('Строки'))
        self.string_language_menu.setTitle(self.t('Язык текста'))
        self.language_menu.setTitle(self.t('Язык'))
        self.shared_scroll.setToolTip(self.t('Общая прокрутка свойств слева и справа'))
        if self.model:
            self.model.set_language(language)
        for pane in self.panes:
            pane.retranslate()
        self.refresh_properties()
        self.update_actions()

    def action(self, bar, label, function, shortcut=None):
        action = QAction(label, self)
        action.setProperty('translation_key', label)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(lambda checked=False: function())
        bar.addAction(action)
        self.addAction(action)  # Keep shortcuts active when the popup menu is closed.
        return action

    def pane_selected(self, pane):
        self.active = pane
        self.update_actions()

    def transfer(self, source, target):
        if self.busy or not self.document or not self.panes[source].node_id:
            return
        self.panes[target].reveal(self.panes[source].node_id)
        self.update_actions()

    def choose_resources(self):
        folder = QFileDialog.getExistingDirectory(self, self.t('Выбрать каталог клиента или SysTextures'), self.preview_resources.directory)
        if folder:
            self.set_resources(folder)

    def set_resources(self, folder):
        self.settings.setValue('resource_directory', str(folder))
        self.reload_resources()

    def reload_resources(self):
        overlays = [str(self.texture_project.output.parent)] if self.texture_project is not None else []
        self.preview_resources = ResourceCache(self.settings.value('resource_directory', ''), overlays)
        for pane in self.panes:
            pane.preview.invalidate()

    def properties_synced(self):
        return self.sync_scroll.isChecked() and all(p.tabs.currentIndex() == 0 for p in self.panes)

    def open_texture_manager(self):
        dialog = TextureManager(self)
        last = self.settings.value('texture_project', '')
        if self.texture_project is None and last and Path(last).is_file():
            dialog.work(lambda: TextureProject(last), dialog.use_project)
        dialog.exec()
        dialog.thumbnail_token += 1
        dialog.deleteLater()

    def strings_changed(self):
        if not hasattr(self, 'string_language_menu'): return
        for action in self.string_language_group.actions():
            self.string_language_group.removeAction(action)
        self.string_language_menu.clear()
        for entry in self.strings.entries:
            label = entry['language'] + ' — ' + entry['info']['file']
            action = self.string_language_menu.addAction(label)
            action.setCheckable(True); action.setChecked(entry['id'] == self.strings.active_id)
            action.triggered.connect(lambda checked=False, key=entry['id']: self.strings.activate(key))
            self.string_language_group.addAction(action)
        for pane in self.panes:
            pane.preview.invalidate()
        self.update_actions()

    def restore_strings(self):
        if self.strings.entries: return
        if self.busy:
            self.strings_restore_timer.start(200); return
        try:
            records = json.loads(self.settings.value('sysstrings/files', '[]'))
        except (ValueError, TypeError): return
        if not records: return
        key_files = self.settings.value('sysstrings/key_files', [])
        if isinstance(key_files, str): key_files = [key_files]
        active_file = self.settings.value('sysstrings/active_file', '')
        self.set_busy(True, 'Чтение SysString…')
        def load():
            restored, errors = [], []
            for file in key_files:
                try: register_dat_profile(json.loads(Path(file).read_text(encoding='utf-8')))
                except Exception as error: errors.append(str(error))
            for record in records:
                try:
                    table = StringCatalog.load_file(record['file'], record['schema'], record['encoding'], record['profile'])
                    restored.append((table, record['language']))
                except Exception as error: errors.append(str(error))
            return restored, errors
        def done(result, error):
            self.set_busy(False)
            if error:
                self.statusBar().showMessage(self.t('Не удалось восстановить таблицы строк')); return
            restored, errors = result
            for table, language in restored:
                self.strings.attach(table, language)
            chosen = next((e for e in self.strings.entries if e['info']['file'] == active_file), None)
            if chosen: self.strings.activate(chosen['id'])
            if errors: self.statusBar().showMessage(self.t('Некоторые таблицы строк не загружены: откройте их вручную'))
        self.submit(load, done)

    def open_strings(self):
        dialog = StringsDialog(self)
        dialog.exec(); dialog.deleteLater()

    def select_string(self):
        dialog = StringsDialog(self, select=True)
        selected = dialog.selected_id if dialog.exec() == QDialog.DialogCode.Accepted else None
        dialog.deleteLater()
        return selected

    def choose_and_assign_string(self):
        if self.document is None: return
        identifier = self.select_string()
        if identifier is not None: self.assign_string_id(identifier)

    def choose_string_for_field(self, pane, field):
        node = pane.node_id
        identifier = self.select_string()
        if identifier is not None: self.assign_string_id(identifier, pane, node, field)

    def assign_string_id(self, identifier, pane=None, node=None, field=None):
        try:
            pane = pane or self.active or self.panes[0]
            node = node or pane.node_id
            if self.document is None or node is None: raise ValueError(self.t('Выберите элемент в дереве'))
            if self.strings.snapshot() is None or identifier not in self.strings.snapshot(): raise ValueError(self.t('Строка отсутствует в выбранном языке'))
            props = self.document.properties(node)
            integers = [p['name'] for p in props if p['kind'] == 'int' and not p['readonly'] and not p['enum']]
            known = [p for p in ('buttonName', 'sysstring', 'title', 'tooltipText', 'popupValue', 'tooltip', 'textStringId') if p in integers]
            if field is None:
                choices = known or integers
                if not choices: raise ValueError(self.t('Нет подходящего поля ID'))
                field, ok = QInputDialog.getItem(self, self.t('Назначить строку'), self.t('Поле ID'), choices, 0, False)
                if not ok: return
            if field not in integers: raise ValueError(self.t('Нет подходящего поля ID'))
            values = {field: identifier}
            literal = {'buttonName': 'buttonNameText', 'sysstring': 'text'}.get(field)
            if literal and any(p['name'] == literal for p in props): values[literal] = 'undefined'
            document = self.document
            self.mutate(lambda: document.set_many(node, values), node)
        except Exception: self.error(traceback.format_exc())

    def texture_target(self):
        if self.document is None or self.document.summary()['schema'] != 'ct26.XDAT':
            raise ValueError(self.t('Текстурные проекты пока поддерживают только High Five'))
        if self.texture_project is None or not self.texture_project.build_info():
            raise ValueError(self.t('Откройте проект текстур и соберите UTX'))
        pane = self.active or self.panes[0]
        if pane.node_id is None:
            raise ValueError(self.t('Выберите элемент в дереве'))
        return pane, self.document.info(pane.node_id)

    def assign_project_textures(self, selected=None):
        try:
            pane, info = self.texture_target()
            fields = {'Button': ['normalTex', 'pushedTex', 'highlightTex'], 'Texture': ['file'],
                      'Window': ['backTex'], 'TextBox': ['backTex']}.get(info['type'])
            if not fields:
                raise ValueError(self.t('Для этого типа нет поддерживаемого поля текстуры'))
            dialog = TextureBindingsDialog(self, self.texture_project, fields, selected)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                document, node, values = self.document, pane.node_id, dialog.values()
                self.mutate(lambda: document.set_many(node, values), node)
            dialog.deleteLater()
        except Exception:
            self.error(traceback.format_exc())

    def create_texture_button(self, selected=None):
        try:
            pane, info = self.texture_target()
            target = pane.node_id
            if not info['list']:
                children = self.document.children(target)
                target = next((n['id'] for n in children if n['list'] and n['name'] == 'children'), info['parent'])
            if 'ct26.Button' not in self.document.allowed_types(target):
                raise ValueError(self.t('Выберите список children нужного окна'))
            dialog = TextureBindingsDialog(self, self.texture_project, ['normalTex', 'pushedTex', 'highlightTex'], selected, button=True)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                document, values = self.document, dialog.values()
                parent = document.info(target)['parent']
                values['parentName'] = document.info(parent)['name']
                values['anchored'] = 0
                self.mutate(lambda: document.add_configured(target, 'ct26.Button', values), completed=pane.reveal)
            dialog.deleteLater()
        except Exception:
            self.error(traceback.format_exc())

    def refresh_properties(self, *_):
        if self._properties_guard or not hasattr(self, 'panes'):
            return
        self._properties_guard = True
        self._scroll_guard = True
        old_scroll = [p.table.verticalScrollBar().value() for p in self.panes]
        common = self.shared_scroll.value()
        try:
            for pane in self.panes:
                try:
                    pane.all_props = pane.document.properties(pane.node_id, True) if pane.document is self.document and pane.node_id else []
                except RuntimeError:
                    pane.node_id = None
                    pane.all_props = []
                pane.props = [p for p in pane.all_props if p.get('active', True)]
            aligned = self.sync_scroll.isChecked() or self.compare_action.isChecked()
            highlight = self.compare_action.isChecked() and all(p.node_id is not None for p in self.panes)
            rows = align_properties(*(p.all_props for p in self.panes)) if aligned else None
            for side, pane in enumerate(self.panes):
                local_rows = rows if aligned else [dict(name=p['name'], fields=[p, p], status='equal', reasons=['', '']) for p in pane.props]
                pane.render_properties(local_rows, side, highlight)
                pane.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if self.properties_synced() else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                pane.table.verticalScrollBar().setValue(old_scroll[side])
            self.shared_scroll.setVisible(self.properties_synced())
        finally:
            self._scroll_guard = False
            self._properties_guard = False
        self.refresh_shared_scroll()
        if self.properties_synced():
            self.scroll_both(common)
        QTimer.singleShot(0, self.refresh_shared_scroll)

    def refresh_shared_scroll(self):
        if self._scroll_guard or not hasattr(self, 'shared_scroll'):
            return
        if not self.properties_synced():
            self.shared_scroll.hide()
            return
        self._scroll_guard = True
        try:
            bars = [pane.table.verticalScrollBar() for pane in self.panes]
            self.shared_scroll.setRange(0, max(bar.maximum() for bar in bars))
            self.shared_scroll.setPageStep(min(bar.pageStep() for bar in bars))
            self.shared_scroll.setSingleStep(28)
        finally:
            self._scroll_guard = False
        self.scroll_both(self.shared_scroll.value())

    def scroll_from_table(self, pane, value):
        if self.properties_synced() and not self._scroll_guard:
            self.scroll_both(value)

    def scroll_both(self, value):
        if self._scroll_guard or not self.properties_synced():
            return
        self._scroll_guard = True
        try:
            self.shared_scroll.setValue(value)
            value = self.shared_scroll.value()
            for pane in self.panes:
                pane.table.verticalScrollBar().setValue(value)
        finally:
            self._scroll_guard = False

    def error(self, text):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(self.t('Ошибка Interface Editor'))
        box.setText(text.splitlines()[-1] if text else self.t('Неизвестная ошибка'))
        box.setDetailedText(text)
        box.exec()

    def submit(self, function, callback):
        task = Task(function)
        self.tasks.add(task)
        def finished(value, error):
            self.tasks.discard(task)
            callback(value, error)
        task.signals.done.connect(finished)
        self.pool.start(task)

    def set_busy(self, busy, message=''):
        self.busy = busy
        self.progress.setVisible(busy)
        self.split.setEnabled(not busy)
        self.version.setEnabled(not busy)
        self.open_action.setEnabled(not busy)
        self.open_json_action.setEnabled(not busy)
        self.view_bar.setEnabled(not busy)
        self.options_button.setEnabled(not busy)
        self.texture_button.setEnabled(not busy)
        self.strings_button.setEnabled(not busy)
        self.shared_scroll.setEnabled(not busy)
        if message:
            self.statusBar().showMessage(self.t(message))
        self.update_actions()

    def update_actions(self):
        info = self.document.summary() if self.document and not self.busy else None
        self.save_action.setEnabled(bool(info) and not self.busy)
        self.save_as_action.setEnabled(bool(info) and not self.busy)
        self.export_json_action.setEnabled(bool(info) and not self.busy)
        self.undo_action.setEnabled(bool(info and info['undo']) and not self.busy)
        self.redo_action.setEnabled(bool(info and info['redo']) and not self.busy)
        self.to_right.setEnabled(bool(info and self.panes[0].node_id) and not self.busy)
        self.to_left.setEnabled(bool(info and self.panes[1].node_id) and not self.busy)
        if info:
            self.setWindowTitle(f"{'* ' if info['dirty'] or self.strings.dirty else ''}{Path(info['file']).name if info['file'] else self.t('Импорт JSON')} — {info['schema']} — Interface Editor")
            message = self.t('{count} объектов · {state}', count=info['nodes'], state=self.t('Есть изменения' if info['dirty'] else 'Сохранено'))
            if self.strings.active:
                message += ' · SysString: ' + self.strings.active['language']
                if self.strings.dirty: message += ' * ' + self.t('Есть несохранённые строки')
            self.statusBar().showMessage(message)
        elif not self.busy and self.strings.active:
            self.statusBar().showMessage('SysString: ' + self.strings.active['info']['file'] + (' *' if self.strings.dirty else ''))

    def discard_confirmed(self, include_strings=False):
        if not (self.document and self.document.summary()['dirty']) and not (include_strings and self.strings.dirty):
            return True
        message = 'Есть несохранённые изменения XDAT и/или SysString. Продолжить без сохранения?' if include_strings else 'Продолжить без сохранения?'
        return QMessageBox.question(self, self.t('Несохранённые изменения'), self.t(message), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def open_file(self):
        if not self.discard_confirmed():
            return
        filename, _ = QFileDialog.getOpenFileName(self, self.t('Открыть XDAT'), self.settings.value('directory', ''), self.t('XDAT (*.xdat);;Все файлы (*)'))
        if filename:
            self.load_file(filename, self.version.currentData())

    def open_json_dialog(self):
        if not self.discard_confirmed():
            return
        filename, _ = QFileDialog.getOpenFileName(self, self.t('Открыть документ JSON'), self.settings.value('directory', ''), 'JSON (*.json)')
        if filename:
            self.load_file(filename, None)

    def export_json_dialog(self):
        if not self.document or self.busy:
            return
        source = self.document.summary()['file']
        suggestion = str(Path(source).with_suffix('.json')) if source else 'Interface.json'
        filename, _ = QFileDialog.getSaveFileName(self, self.t('Экспорт всего документа в JSON'), suggestion, 'JSON (*.json)')
        if filename:
            self.export_json_file(filename)

    def export_json_file(self, filename):
        if not self.document or self.busy:
            return
        self.set_busy(True, 'Экспорт JSON…')
        document = self.document
        def done(_, error):
            self.set_busy(False)
            if error:
                self.error(error)
            else:
                self.statusBar().showMessage(self.t('JSON сохранён: {filename}', filename=filename))
        self.submit(lambda: document.export_json(filename), done)

    def reload_schemas(self):
        self.schema_text, self.schema_errors = load_schemas(ROOT / 'schemas/schemas.json', self.user_schema_directory)
        selected = self.version.currentData()
        self.version.clear()
        for label, schema in json.loads(self.schema_text)['versions']:
            self.version.addItem(label, schema)
        self.version.setCurrentIndex(max(0, self.version.findData(selected)))
        if self.schema_errors:
            self.error('\n'.join(self.schema_errors))

    def load_file(self, filename, schema):
        self.reload_schemas()
        self.set_busy(True, 'Чтение JSON…' if schema is None else 'Чтение XDAT…')
        for pane in self.panes:
            pane.generation += 1
            pane.timer.stop()
            pane.preview.invalidate()
        def load():
            document = Document(self.schema_text)
            if schema is None:
                document.open_json(filename)
            else:
                document.load(filename, schema)
            return document
        def done(document, error):
            if not error:
                old_model = self.model
                self.document = document
                self.clipboard_id = None
                self.model = TreeModel(document, self)
                self.model.set_language(self.language)
                for pane in self.panes:
                    pane.set_document(document, self.model)
                if old_model:
                    old_model.deleteLater()
                self.version.setCurrentIndex(self.version.findData(document.summary()['schema']))
                self.refresh_properties()
                self.settings.setValue('directory', str(Path(filename).parent))
            self.set_busy(False)
            if error:
                if schema is not None and Path(filename).is_file():
                    analyze(self, filename, schema, error)
                else:
                    self.error(error)
        self.submit(load, done)

    def save_file(self, save_as=False):
        if not self.document or self.busy:
            return
        filename = self.document.summary()['file']
        if save_as or not filename:
            filename, _ = QFileDialog.getSaveFileName(self, self.t('Сохранить XDAT'), filename, 'XDAT (*.xdat)')
        if not filename:
            return
        self.set_busy(True, 'Запись и проверка XDAT…')
        document = self.document
        def done(_, error):
            self.set_busy(False)
            if error:
                self.error(error)
        self.submit(lambda: document.save(filename), done)

    def mutate(self, function, node_id=None, completed=None):
        if not self.document or self.busy:
            return
        self.set_busy(True, 'Применение изменения…')
        for pane in self.panes:
            pane.generation += 1
            pane.preview.invalidate()
        def done(value, error):
            if not error:
                if node_id is None or not self.model.refresh_node(node_id):
                    for pane in self.panes:
                        pane.restoring = True
                    self.model.reset_document()
                    for pane in self.panes:
                        pane.restoring = False
                for pane in self.panes:
                    pane.restore()
                    if pane.search.text():
                        pane.timer.start()
                if completed:
                    completed(value)
            else:
                for pane in self.panes:
                    pane.show_properties()
            self.set_busy(False)
            if error:
                self.error(error)
        self.submit(function, done)

    def edit(self, node_id, name, value):
        document = self.document
        self.mutate(lambda: document.set(node_id, name, value), node_id)

    def history(self, redo):
        document = self.document
        self.mutate(document.redo if redo else document.undo)

    def command(self, pane, command):
        if not self.document or not pane.node_id or self.busy:
            return
        document, node = self.document, pane.node_id
        if command == 'copy':
            self.clipboard_id = node
            self.statusBar().showMessage(self.t('Объект выбран для копирования в другую ветку'))
            return
        try:
            if command == 'duplicate':
                self.mutate(lambda: document.duplicate(node))
            elif command == 'delete':
                if QMessageBox.question(self, self.t('Удаление'), self.t('Удалить выбранный объект и его дочерние элементы?')) == QMessageBox.StandardButton.Yes:
                    self.mutate(lambda: document.remove(node))
            else:
                info = document.info(node)
                target = node if info['list'] else info['parent']
                if command == 'paste':
                    if self.clipboard_id:
                        source = self.clipboard_id
                        self.mutate(lambda: document.duplicate(source, target))
                else:
                    types = document.allowed_types(target)
                    selected, ok = QInputDialog.getItem(self, self.t('Добавление'), self.t('Тип объекта'), types, 0, False)
                    if ok:
                        self.mutate(lambda: document.add(target, selected))
        except Exception:
            self.error(traceback.format_exc())

    def closeEvent(self, event):
        if self.busy or self.tasks:
            QMessageBox.information(self, self.t('Операция выполняется'), self.t('Дождитесь завершения текущей операции.'))
            event.ignore()
            return
        if not self.discard_confirmed(include_strings=True):
            event.ignore()
            return
        self.strings_restore_timer.stop()
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.split.saveState())
        self.settings.setValue('sync_scroll', self.sync_scroll.isChecked())
        self.settings.setValue('compare', self.compare_action.isChecked())
        self.settings.setValue('wheel_values', self.wheel_values.isChecked())
        self.settings.setValue('language', self.language)
        for pane in self.panes:
            self.settings.setValue(f'panes/{pane.side}/neighbors', pane.neighbors.isChecked())
            pane.timer.stop()
            pane.generation += 1
            pane.pending_query = None
            pane.preview.stop()
        self.wheel_guard.uninstall()
        if self.qt_translator:
            QApplication.instance().removeTranslator(self.qt_translator)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Editor()
    window.show()
    if len(sys.argv) > 1:
        schema = None if Path(sys.argv[1]).suffix.lower() == '.json' else sys.argv[2] if len(sys.argv) > 2 else 'ct26.XDAT'
        window.load_file(sys.argv[1], schema)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
