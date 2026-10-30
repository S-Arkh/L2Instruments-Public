from __future__ import annotations
import json
from pathlib import Path
import sys
import threading
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QRegularExpression
from PySide6.QtGui import QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout,
    QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QFileDialog,
    QLabel, QLineEdit, QProgressBar, QMessageBox, QAbstractItemView, QCheckBox, QComboBox)
from backend import Core, export_classes, targets, view_text


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
        self.settings = QSettings('L2Tools', 'uExplorer')
        self.core = Core(); self.worker = None; self.package = None; self.classes = []; self.result = None
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
        for widget in (self.open_button, self.reload_button, self.deps_button, self.output_button, self.selected_button, self.all_button): bar.addWidget(widget)
        self.path_label = QLabel('Выберите каталог с .u'); self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addWidget(self.path_label)
        options = QHBoxLayout(); layout.addLayout(options)
        self.force = QCheckBox('Из байткода даже при наличии ScriptText'); self.force.toggled.connect(self.preview)
        options.addWidget(self.force)
        options.addWidget(QLabel('ANSI ScriptText:'))
        self.encoding = QComboBox(); self.encoding.addItems(['cp1251', 'cp1252', 'latin1', 'cp949']); self.encoding.currentTextChanged.connect(self.refresh_code); options.addWidget(self.encoding)
        options.addStretch(); self.status_label = QLabel(''); options.addWidget(self.status_label)
        split = QSplitter(Qt.Horizontal); layout.addWidget(split, 1)
        left = QWidget(); l = QVBoxLayout(left); l.addWidget(QLabel('Пакеты .u'))
        self.file_filter = QLineEdit(); self.file_filter.setPlaceholderText('Фильтр файлов'); l.addWidget(self.file_filter)
        self.files = QListWidget(); l.addWidget(self.files); split.addWidget(left)
        center = QWidget(); c = QVBoxLayout(center); c.addWidget(QLabel('Классы пакета (Ctrl / Shift — выбор нескольких)'))
        self.class_filter = QLineEdit(); self.class_filter.setPlaceholderText('Фильтр классов'); c.addWidget(self.class_filter)
        self.class_list = QListWidget(); self.class_list.setSelectionMode(QAbstractItemView.ExtendedSelection); c.addWidget(self.class_list); split.addWidget(center)
        self.code = QPlainTextEdit(); self.code.setReadOnly(True); self.code.setLineWrapMode(QPlainTextEdit.NoWrap); self.code.setFont(QFont('Consolas', 11)); split.addWidget(self.code); self.highlight = Highlight(self.code.document())
        split.setSizes([240, 330, 880])
        bottom = QHBoxLayout(); layout.addLayout(bottom); self.progress = QProgressBar(); bottom.addWidget(self.progress)
        self.cancel_button = QPushButton('Отмена'); self.cancel_button.clicked.connect(self.cancel_work); bottom.addWidget(self.cancel_button)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(135); layout.addWidget(self.log)
        self.files.currentItemChanged.connect(self.load_package); self.class_list.currentItemChanged.connect(self.preview)
        self.file_filter.textChanged.connect(lambda text: self.filter_list(self.files, text))
        self.class_filter.textChanged.connect(lambda text: self.filter_list(self.class_list, text))
        self.set_busy(False)
        previous = self.settings.value('directory', '')
        if previous and Path(previous).is_dir(): self.populate(previous)

    @staticmethod
    def filter_list(widget, text):
        for index in range(widget.count()):
            item = widget.item(index); item.setHidden(text.casefold() not in item.text().casefold())

    def set_busy(self, busy):
        for widget in (self.open_button, self.reload_button, self.deps_button, self.output_button, self.files, self.class_list, self.force): widget.setEnabled(not busy)
        self.selected_button.setEnabled(not busy and bool(self.classes)); self.all_button.setEnabled(not busy and bool(self.classes)); self.cancel_button.setEnabled(busy)

    def task(self, work, callback):
        if self.worker is not None: return
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
        self.progress.setRange(0, 100); self.progress.setValue(100); self.set_busy(False)

    def failure(self, text):
        detail=text.strip().splitlines()[-1] if text.strip() else 'Неизвестная ошибка'
        item=self.class_list.currentItem()
        context=f"Пакет: {self.package or 'не выбран'}"
        if item:context+='\nКласс: '+item.text()
        self.log.appendPlainText(context+'\n'+detail+'\n\nТехнические подробности:\n'+text)
        self.status_label.setText('Ошибка: '+detail)

    def update_progress(self, value, total, name):
        self.progress.setRange(0, max(1, total)); self.progress.setValue(value); self.status_label.setText(name)

    def cancel_work(self):
        if self.worker:
            self.worker.cancel.set(); self.status_label.setText('Отмена после текущего класса/операции…')

    def open_directory(self):
        directory = QFileDialog.getExistingDirectory(self, 'Каталог с пакетами .u', self.settings.value('directory', ''))
        if directory: self.populate(directory)

    def populate(self, directory):
        self.files.blockSignals(True); self.files.clear(); self.clear_classes(); self.package=None
        try:
            for path in sorted(Path(directory).iterdir(), key=lambda p: p.name.casefold()):
                if path.is_file() and path.suffix.casefold()=='.u':
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
        self.clear_classes(); self.package=item.data(Qt.UserRole)
        path=self.package; deps=list(self.dependencies)
        self.task(lambda w:self.core.request(operation='inspect',path=path,dependencies=deps,reload=True),self.loaded)

    def clear_classes(self):
        # clear() can emit currentItemChanged while the old item's data is still
        # visible. Never start a preview during a package/directory transition.
        previous=self.class_list.blockSignals(True)
        try:self.class_list.clear()
        finally:self.class_list.blockSignals(previous)
        self.classes=[];self.result=None;self.code.clear()

    def loaded(self, response):
        self.classes=response['package']['classes']; self.class_list.blockSignals(True)
        for info in sorted(self.classes,key=lambda row:row['path'].casefold()):
            item=QListWidgetItem(info['path']);item.setData(Qt.UserRole,info);item.setToolTip('extends '+info['super']);self.class_list.addItem(item)
        self.class_list.blockSignals(False); self.filter_list(self.class_list,self.class_filter.text())
        p=response['package'];self.status_label.setText(f"{p['version']}/{p['licensee']} · {len(self.classes)} классов · {p['envelope']}")
        self.log.appendPlainText(self.package)
        for message in response.get('diagnostics',[]): self.log.appendPlainText(message)

    def preview(self, *_):
        item=self.class_list.currentItem()
        if not item or self.worker or not self.package: return
        info=item.data(Qt.UserRole);path=self.package;deps=list(self.dependencies);force=self.force.isChecked()
        if info not in self.classes:return
        self.result=None;self.code.clear()
        self.task(lambda w:self.core.request(operation='decompile',path=path,dependencies=deps,force_bytecode=force,**{'class':info['path']}),self.previewed)

    def previewed(self,response):
        self.result=response['result'];self.refresh_code();self.status_label.setText(self.result['method']+' · '+self.result['status'])
        for issue in self.result.get('issues',[]):self.log.appendPlainText(issue['scope']+': '+issue['message'])

    def refresh_code(self,*_):
        if self.result:self.code.setPlainText(view_text(self.result,self.encoding.currentText()))

    def choose_output(self):
        directory=QFileDialog.getExistingDirectory(self,'Каталог экспорта',self.output)
        if directory:self.output=directory;self.settings.setValue('output',directory);self.log.appendPlainText('Export: '+directory)

    def export(self,all_classes):
        if not self.package or self.worker:return
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
        if self.worker:
            self.cancel_work();event.ignore();QMessageBox.information(self,'Завершение','Дождитесь завершения текущего класса/операции, затем закройте окно.');return
        super().closeEvent(event)


def main():
    app=QApplication(sys.argv)
    try:window=MainWindow()
    except Exception as error:QMessageBox.critical(None,'uExplorer',str(error));return 1
    window.show();return app.exec()

if __name__=='__main__':sys.exit(main())
