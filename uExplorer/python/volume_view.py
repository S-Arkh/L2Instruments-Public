"""Saved BlockingVolume properties, without inventing a world transform."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
from resource_view import summary_text


class BlockingVolumeView(QWidget):
    navigate = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.path = ''
        self.model_id = 0
        layout = QVBoxLayout(self)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setTextFormat(Qt.PlainText)
        layout.addWidget(self.warning)
        self.model_button = QPushButton('Открыть связанную Model')
        self.model_button.clicked.connect(self.open_model)
        layout.addWidget(self.model_button)
        self.properties = QPlainTextEdit()
        self.properties.setReadOnly(True)
        layout.addWidget(self.properties)
        self.clear()

    def clear(self):
        self.path = ''
        self.model_id = 0
        self.warning.clear()
        self.model_button.setText('Открыть связанную Model')
        self.model_button.setEnabled(False)
        self.properties.clear()

    def load(self, document, path):
        self.path = str(path)
        brush = document.get('brush', {})
        identifier = brush.get('id')
        self.model_id = identifier if type(identifier) is int and identifier > 0 and brush.get('class') == 'Model' else 0
        self.model_button.setEnabled(bool(self.model_id))
        self.model_button.setText('Открыть связанную Model: ' + str(brush.get('path', 'не найдена')))
        note = ('Показаны только сохранённые поля BlockingVolume. Наследуемые defaults, '
                'мировое преобразование и игровая коллизия не подтверждены; состояние не исполняется.')
        if document.get('status') == 'partial':
            note += ' Некоторые свойства не разобраны.'
        if any(isinstance(tag, dict) and tag.get('name', '').casefold() in
               {'bdeleteme', 'bpendingdelete'} and tag.get('value') is True
               for tag in document.get('properties', [])):
            note += ' В файле явно сохранён признак удаления; текущее игровое состояние не установлено.'
        self.warning.setText(note)
        self.properties.setPlainText(summary_text(document))

    def open_model(self):
        if self.path and self.model_id:
            self.navigate.emit(self.path, self.model_id)
