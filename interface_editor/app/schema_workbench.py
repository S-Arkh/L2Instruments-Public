"""Interactive schema research, with explicit acceptance of layout hypotheses."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QPlainTextEdit, QFileDialog, QSplitter, QTreeWidget, QTreeWidgetItem,
    QListWidget, QSpinBox, QInputDialog)

from schema_tools import draft_package, export_package, import_package, validate_package, report, validation_info
from schema_research import inspect_samples, suggest, apply_change, scan_anchors


class SchemaWorkbench(QDialog):
    def __init__(self, window, filename=None, schema=None):
        super().__init__(window)
        self.window, self.t = window, window.t
        self.setWindowTitle(self.t('Исследование схем XDAT'))
        self.resize(1250, 850)
        self.running = False
        self.cancelled = False
        self.samples, self.results, self.hypotheses, self.history = [], [], [], []
        self.package = draft_package(window.schema_text, schema or window.version.currentData(), 'Custom XDAT')
        layout = QVBoxLayout(self)
        note = QLabel(self.t('Гипотезы требуют проверки. Смещение ошибки и побайтное совпадение не доказывают смысл полей.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.sample = QComboBox()
        self.sample.currentIndexChanged.connect(self.show_trace)
        row.addWidget(self.sample, 1)
        self.buttons = []

        def button(label, callback, parent=row):
            result = QPushButton(self.t(label))
            result.clicked.connect(callback)
            parent.addWidget(result)
            self.buttons.append(result)
            return result

        button('Добавить образцы…', self.add_samples)
        button('Убрать образец', self.remove_sample)
        button('Загрузить схему…', self.load_package)
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 120)
        self.seconds.setValue(20)
        self.seconds.setSuffix(self.t(' с'))
        row.addWidget(self.seconds)
        button('Разобрать', lambda: self.run(False))
        button('Подобрать изменения', lambda: self.run(True))
        self.cancel_button = QPushButton(self.t('Отмена'))
        self.cancel_button.clicked.connect(lambda: setattr(self, 'cancelled', True))
        self.cancel_button.setEnabled(False)
        row.addWidget(self.cancel_button)
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(json.dumps(self.package, ensure_ascii=False, indent=2))
        self.editor.textChanged.connect(self.invalidate)
        split.addWidget(self.editor)
        self.trace = QTreeWidget()
        self.trace.setHeaderLabels([self.t('Объект / поле'), self.t('Тип'), self.t('Смещение'), self.t('Размер'), self.t('Значение')])
        self.trace.currentItemChanged.connect(self.show_hex)
        split.addWidget(self.trace)
        split.setSizes([450, 750])
        self.hex = QPlainTextEdit()
        self.hex.setReadOnly(True)
        self.hex.setMaximumHeight(130)
        layout.addWidget(self.hex)
        self.choices = QListWidget()
        self.choices.setMaximumHeight(110)
        layout.addWidget(self.choices)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        button('Принять гипотезу', self.accept_hypothesis, actions)
        button('Отменить изменение схемы', self.undo_schema, actions)
        button('Экспорт схемы…', self.export, actions)
        button('Установить черновик…', self.install, actions)
        button('Сохранить отчёт анализа', self.save_report, actions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        if filename:
            self.read_samples([filename])

    def reject(self):
        if self.running:
            self.cancelled = True
            return
        super().reject()

    def closeEvent(self, event):
        if self.running:
            self.cancelled = True
            event.ignore()
        else:
            super().closeEvent(event)

    def read_samples(self, paths):
        for path in paths:
            with Path(path).open('rb') as stream:
                data = stream.read(256 * 1024 * 1024 + 1)
            if len(data) > 256 * 1024 * 1024:
                raise ValueError('File too large')
            if any(data == previous for _, previous in self.samples):
                continue
            if sum(len(b) for _, b in self.samples) + len(data) > 512 * 1024 * 1024:
                raise ValueError('Sample set too large')
            self.samples.append((Path(path).name, data))
            self.sample.addItem(Path(path).name)
        self.invalidate()

    def add_samples(self):
        paths, _ = QFileDialog.getOpenFileNames(self, self.t('Добавить образцы…'), '', 'XDAT (*.xdat)')
        try:
            self.read_samples(paths)
        except Exception as error:
            self.window.error(str(error))

    def current_package(self):
        return validate_package(json.loads(self.editor.toPlainText()))

    def remove_sample(self):
        index = self.sample.currentIndex()
        if 0 <= index < len(self.samples):
            self.invalidate()
            del self.samples[index]
            self.sample.removeItem(index)

    def invalidate(self):
        self.results, self.hypotheses = [], []
        self.trace.clear()
        self.choices.clear()
        self.hex.clear()
        self.status.clear()

    def replace_package(self, package):
        self.history.append(self.editor.toPlainText())
        self.package = package
        self.editor.setPlainText(json.dumps(package, ensure_ascii=False, indent=2))
        self.invalidate()

    def load_package(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t('Загрузить схему…'), '', 'JSON (*.json)')
        if path:
            try:
                if Path(path).stat().st_size > 16 * 1024 * 1024:
                    raise ValueError('Schema package too large')
                self.replace_package(validate_package(json.loads(Path(path).read_text(encoding='utf-8'))))
            except Exception as error:
                self.window.error(str(error))

    def run(self, hypotheses):
        try:
            package = self.current_package()
            if not self.samples:
                raise ValueError(self.t('Добавьте хотя бы один образец XDAT.'))
        except Exception as error:
            self.window.error(str(error))
            return
        self.package = package
        self.running, self.cancelled = True, False
        self.editor.setReadOnly(True)
        for button in self.buttons:
            button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.window.set_busy(True, 'Подбор схемы…')
        samples = [data for _, data in self.samples]
        seconds = self.seconds.value()

        def work():
            if hypotheses:
                return suggest(package, samples, lambda: self.cancelled, seconds=seconds, max_trials=640)
            results = []
            for data in samples:
                if self.cancelled:
                    break
                results.extend(inspect_samples(package, [data]))
            return {'baseline': results, 'hypotheses': [], 'trials': 0,
                    'stopped': 'cancelled' if self.cancelled else 'complete'}

        def ready(value, error):
            self.running = False
            self.editor.setReadOnly(False)
            for button in self.buttons:
                button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.window.set_busy(False)
            if error:
                self.window.error(error)
                return
            self.results, self.hypotheses = value['baseline'], value['hypotheses']
            self.choices.clear()
            for hypothesis in self.hypotheses:
                c = hypothesis['change']
                self.choices.addItem(f"{c['record']}.{c['field']}: {c['action']} {c.get('kinds', c.get('kind', c.get('count', '')))} — {hypothesis['progress']}")
            self.status.setText(self.t('Проверено гипотез: {count}; остановка: {reason}', count=value['trials'], reason=value['stopped']))
            self.status.setText(self.status.text() + '\n' + self.t(
                'Образцов: {total}; побайтное совпадение: {matched}; без хвоста: {complete}',
                total=len(self.results), matched=sum(r['compatible'] for r in self.results),
                complete=sum(r['compatible'] and not r['tail_bytes'] for r in self.results)))
            self.show_trace()
        self.window.submit(work, ready)

    def show_trace(self, *_):
        self.trace.clear()
        index = self.sample.currentIndex()
        if not 0 <= index < len(self.results):
            return
        result = self.results[index]
        groups = {}
        if result.get('first_anomaly'):
            event = result['first_anomaly']
            group = QTreeWidgetItem(self.trace, [self.t('Подозрительное значение (эвристика)')])
            item = QTreeWidgetItem(group, [event['path'], event['kind'], str(event['offset']),
                                          str(event['size']), str(event.get('value', ''))[:150]])
            item.setData(0, Qt.ItemDataRole.UserRole, event)
        for event in result['trace']:
            path = event['path']
            parent_path = path.rsplit('.', 1)[0] if 'field' in event else path
            if parent_path not in groups:
                groups[parent_path] = QTreeWidgetItem(self.trace, [parent_path])
            item = QTreeWidgetItem(groups[parent_path], [event.get('field', event.get('condition', '')),
                event['kind'], str(event['offset']), str(event['size']), str(event.get('value', ''))[:150]])
            item.setData(0, Qt.ItemDataRole.UserRole, event)
        if result.get('failure'):
            event = dict(result['failure'], size=0)
            item = QTreeWidgetItem(self.trace, [event['path'], event['kind'], str(event['offset']), '!', event['message']])
            item.setData(0, Qt.ItemDataRole.UserRole, event)
            self.trace.setCurrentItem(item)
        else:
            self.hex.setPlainText(self.t('Побайтное совпадение: {match}; необработанный хвост: {tail}',
                match=result['compatible'], tail=result['tail_bytes']))
        if result.get('failure'):
            group = QTreeWidgetItem(self.trace, [self.t('Возможные теги типов (границы не подтверждены)')])
            for event in scan_anchors(self.package, self.samples[index][1], result['failure']['offset']):
                item = QTreeWidgetItem(group, [event['field'], 'anchor', str(event['offset']), str(event['size'])])
                item.setData(0, Qt.ItemDataRole.UserRole, event)
        if result['trace_truncated']:
            QTreeWidgetItem(self.trace, [self.t('Показаны последние события: {shown} из {total}',
                shown=len(result['trace']), total=result['trace_count'])])
        self.trace.expandAll()
        self.trace.resizeColumnToContents(0)

    def show_hex(self, item, *_):
        if item is None:
            return
        event = item.data(0, Qt.ItemDataRole.UserRole)
        if not event:
            return
        data = self.samples[self.sample.currentIndex()][1]
        start = max(0, event['offset'] - 32) // 16 * 16
        lines = []
        for offset in range(start, min(len(data), start + 128), 16):
            block = data[offset:offset + 16]
            lines.append(f"{offset:08x}  {block.hex(' '):47}  " + ''.join(chr(b) if 32 <= b < 127 else '.' for b in block))
        self.hex.setPlainText(f"{event['path']} @ {event['offset']} (0x{event['offset']:x}), {event['size']} bytes\n" + '\n'.join(lines))

    def accept_hypothesis(self):
        index = self.choices.currentRow()
        if 0 <= index < len(self.hypotheses):
            try:
                if self.current_package() != self.package:
                    raise ValueError(self.t('Схема изменена: повторите анализ.'))
                self.replace_package(apply_change(self.package, self.hypotheses[index]['change']))
                self.run(False)
            except Exception as error:
                self.window.error(str(error))

    def undo_schema(self):
        if self.history:
            self.editor.setPlainText(self.history.pop())
            self.invalidate()

    def export(self):
        try:
            package = self.current_package()
            portable = export_package(json.dumps(package), package['versions'][0][1])
            portable.pop('validation', None)
            portable['status'] = 'draft'
            if package == self.package and len(self.results) == len(self.samples) and self.results:
                portable.update(validation_info([data for _, data in self.samples], self.results))
            path, _ = QFileDialog.getSaveFileName(self, self.t('Экспорт схемы…'), 'custom-schema.json', 'JSON (*.json)')
            if path:
                Path(path).write_text(json.dumps(portable, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as error:
            self.window.error(str(error))

    def install(self):
        try:
            package = self.current_package()
            label, ok = QInputDialog.getText(self, self.t('Установить черновик…'), self.t('Название схемы'))
            if not ok or not label.strip():
                return
            package = draft_package(json.dumps(package), package['versions'][0][1], label.strip())
            if self.current_package() == self.package and len(self.results) == len(self.samples) and self.results:
                package.update(validation_info([data for _, data in self.samples], self.results))
            validate_package(package)
            directory = self.window.user_schema_directory
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / (package['versions'][0][1] + '.json')).open('x', encoding='utf-8') as output:
                json.dump(package, output, ensure_ascii=False, indent=2)
            self.window.reload_schemas()
            self.window.version.setCurrentIndex(self.window.version.findData(package['versions'][0][1]))
            self.status.setText(self.t('Черновик установлен. Выберите его при открытии XDAT.'))
        except Exception as error:
            self.window.error(str(error))

    def save_report(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(self, self.t('Сохранить отчёт анализа'), 'schema-analysis.json', 'JSON (*.json)')
        if path:
            try:
                reports = [report('', data, self.package['versions'][0][1], [result])
                           for (_, data), result in zip(self.samples, self.results)]
                Path(path).write_text(json.dumps(reports, indent=2), encoding='utf-8')
            except Exception as error:
                self.window.error(str(error))


def research(window, filename=None, schema=None):
    dialog = SchemaWorkbench(window, filename, schema)
    dialog.exec()
    dialog.deleteLater()


def import_schema(window):
    path, _ = QFileDialog.getOpenFileName(window, window.t('Импорт схемы…'), '', 'JSON (*.json)')
    if path:
        try:
            import_package(path, window.user_schema_directory, window.schema_text)
            window.reload_schemas()
        except Exception as error:
            window.error(str(error))


def export_schema(window):
    path, _ = QFileDialog.getSaveFileName(window, window.t('Экспорт схемы…'), 'schema.json', 'JSON (*.json)')
    if path:
        try:
            package = export_package(window.schema_text, window.version.currentData())
            Path(path).write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as error:
            window.error(str(error))
