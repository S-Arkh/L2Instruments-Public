"""Non-blocking schema discovery, selection and draft creation."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QPlainTextEdit, QFileDialog, QInputDialog, QProgressDialog)
from _interface_core import Document
from schema_tools import probe, draft_package, report


def analyze(window, filename, selected, original_error):
    t = window.t
    progress = QProgressDialog(t('Подбор схемы…'), t('Отмена'), 0, 1, window)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    window.set_busy(True, 'Подбор схемы…')
    catalog_text = window.schema_text
    versions = {}
    for label, schema in json.loads(catalog_text)['versions']:
        versions.setdefault(schema, []).append(label)
    candidates = list(versions)
    results = []
    state = {'cancelled': False}
    progress.canceled.connect(lambda: state.update(cancelled=True))

    def finish():
        progress.close()
        progress.deleteLater()
        window.set_busy(False)

    def ready(value, error):
        if state['cancelled']:
            finish()
            return
        if error:
            finish()
            window.error(error)
            return
        data, document = value
        progress.setMaximum(len(candidates))

        def next_probe():
            if state['cancelled']:
                finish()
                return
            index = len(results)
            progress.setValue(index)
            if index == len(candidates):
                finish()
                show_results(window, filename, selected, data, results, original_error)
                return
            schema = candidates[index]
            label = ' / '.join(versions[schema])
            progress.setLabelText(f'{index + 1}/{len(candidates)}: {label}')
            def completed(result, error):
                if error:
                    finish()
                    window.error(error)
                    return
                results.append(result)
                next_probe()
            window.submit(lambda: probe(document, data, schema, label), completed)
        next_probe()

    def prepare():
        with Path(filename).open('rb') as source:
            data = source.read(256 * 1024 * 1024 + 1)
        if len(data) > 256 * 1024 * 1024:
            raise ValueError('File too large')
        return data, Document(catalog_text)
    window.submit(prepare, ready)


def show_results(window, filename, selected, data, results, original_error):
    t = window.t
    dialog = QDialog(window)
    dialog.setWindowTitle(t('Анализ схем XDAT'))
    dialog.resize(800, 500)
    layout = QVBoxLayout(dialog)
    failed = QLabel(t('Не удалось открыть файл по схеме {schema}.', schema=selected))
    failed.setWordWrap(True)
    layout.addWidget(failed)
    matches = sorted((r for r in results if r['compatible']), key=lambda r: r['tail_bytes'])
    candidates = matches or sorted(results, key=lambda r: r['offset'], reverse=True)
    message = ('Найдены совместимые схемы. Выберите схему для открытия.' if matches else
               'Совместимая схема не найдена. Выберите основу для черновика.')
    label = QLabel(t(message))
    label.setWordWrap(True)
    layout.addWidget(label)
    note = QLabel(t('Необработанный хвост сохраняется как байты. Совместимость не определяет хроники однозначно.' if matches else
        'Смещение ошибки — подсказка, а не оценка правильности. Черновик требует ручной доработки JSON и повторной проверки.'))
    note.setWordWrap(True)
    layout.addWidget(note)
    combo = QComboBox()
    for r in candidates:
        suffix = t('хвост: {count} байт', count=r['tail_bytes']) if matches else f"@{r['offset']}"
        combo.addItem(f"{r['label']} — {r['schema']} ({suffix})", r['schema'])
    layout.addWidget(combo)
    details = QPlainTextEdit()
    details.setReadOnly(True)
    details.setPlainText(original_error + '\n\n' + json.dumps(results, ensure_ascii=False, indent=2))
    details.hide()
    toggle = QPushButton(t('Подробности'))
    toggle.clicked.connect(lambda: details.setVisible(not details.isVisible()))
    layout.addWidget(toggle)
    layout.addWidget(details)
    action = QPushButton(t('Переключиться и открыть' if matches else 'Создать черновик схемы…'))
    layout.addWidget(action)
    save = QPushButton(t('Сохранить отчёт анализа'))
    layout.addWidget(save)
    retry = QPushButton(t('Повторить анализ после правки схем'))
    layout.addWidget(retry)
    close = QPushButton(t('Отмена'))
    close.clicked.connect(dialog.reject)
    layout.addWidget(close)

    def save_report():
        path, _ = QFileDialog.getSaveFileName(dialog, t('Сохранить отчёт анализа'), str(Path(filename).with_suffix('.analysis.json')), 'JSON (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(report(filename, data, selected, results), ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception as error:
                window.error(str(error))
    save.clicked.connect(save_report)

    def activate():
        if matches:
            dialog.accept()
            window.load_file(filename, combo.currentData())
            return
        label, ok = QInputDialog.getText(dialog, t('Создать черновик схемы…'), t('Название схемы'))
        if not ok or not label.strip():
            return
        try:
            package = draft_package(window.schema_text, combo.currentData(), label.strip())
            directory = window.user_schema_directory
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / (package['versions'][0][1] + '.json')
            with path.open('x', encoding='utf-8') as output:
                json.dump(package, output, ensure_ascii=False, indent=2)
            details.setPlainText(t('Черновик сохранён: {filename}', filename=str(path)) + '\n\n' + t('Измените JSON и нажмите «Повторить анализ после правки схем».'))
            details.show()
            window.reload_schemas()
        except Exception as error:
            window.error(str(error))
    action.clicked.connect(activate)

    def recheck():
        window.reload_schemas()
        dialog.accept()
        analyze(window, filename, selected, original_error)
    retry.clicked.connect(recheck)
    dialog.exec()
    dialog.deleteLater()
