"""Resource comparison report; only bounded field differences are displayed."""
from collections import Counter
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QLabel,QPushButton,QTreeWidget,
                              QTreeWidgetItem,QPlainTextEdit,QSplitter)


class CompareView(QWidget):
    back = Signal()
    def __init__(self):
        super().__init__();self.report=None
        layout=QVBoxLayout(self)
        self.return_button=QPushButton('К выбранному объекту')
        self.return_button.clicked.connect(self.back.emit);layout.addWidget(self.return_button)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        split=QSplitter(Qt.Vertical);layout.addWidget(split,1)
        self.rows=QTreeWidget();self.rows.setHeaderLabels(['Объект','Класс','Результат'])
        split.addWidget(self.rows)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);split.addWidget(self.details)
        self.rows.currentItemChanged.connect(self.selected)
        layout.addWidget(QLabel('Уровень проверки: декодированные поля и flags/outer. Код классов исключён.'))

    def clear(self):
        self.report=None;self.rows.clear();self.details.clear();self.info.clear()

    def set_loading(self, busy):
        self.return_button.setEnabled(not busy)

    def loading(self, original, candidate):
        self.clear()
        self.info.setText(f'Сравнение ресурсов…\nОригинал: {original}\nКандидат: {candidate}')

    def error(self, message):
        self.clear();self.info.setText('Сравнение не выполнено: '+message)

    def display(self, report):
        self.clear();self.report=report
        counts=Counter(row['status'] for row in report['rows'])
        state=('Отменено: частичный отчёт' if report['cancelled'] else
               'Ресурсы структурно совпали' if report['equal'] else
               'Проверка завершена: есть отличия или непроверенные объекты' if report['total'] else
               'Ресурсных объектов нет')
        self.info.setText(f'{state}\nОригинал: {report["original"]}\nКандидат: {report["candidate"]}\n'
                          f'Совпало: {counts["equal"]} · отличий: {counts["different"]} · '
                          f'не проверено: {counts["unverified"]} · обработано: '
                          f'{len(report["rows"])}/{report["total"]}\n'
                          f'Профили: {report["profiles"]} · исключено экспортов кода/метаданных: '
                          f'{report["excluded_script_exports"]}')
        labels={'equal':'Совпадает','different':'Отличается','unverified':'Не проверен'}
        for row in report['rows']:
            item=QTreeWidgetItem([row['path'],row['class_name'],labels[row['status']]])
            item.setData(0,Qt.UserRole,row);self.rows.addTopLevelItem(item)
        self.rows.resizeColumnToContents(0)

    def selected(self, item, previous):
        if item is None:self.details.clear();return
        row=item.data(0,Qt.UserRole)
        self.details.setPlainText('\n'.join(row['details']) if row['details'] else
                                 'Декодированные поля и метаданные совпадают.')
