"""Material graph, decoded parameters and texture-link inspection."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QImage,QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QListWidget,
                              QLabel,QPlainTextEdit,QPushButton,QSplitter)
from resource_view import summary_text
from material_graph import float_value


class MaterialView(QWidget):
    requested=Signal(int)
    navigate=Signal(str,int)
    def __init__(self):
        super().__init__();self.graph=None
        layout=QVBoxLayout(self)
        self.info=QLabel('Материалы · только просмотр');layout.addWidget(self.info)
        split=QSplitter();layout.addWidget(split,1)
        self.nodes=QListWidget();split.addWidget(self.nodes)
        right=QWidget();column=QVBoxLayout(right);split.addWidget(right)
        self.preview=QLabel();self.preview.setAlignment(Qt.AlignCenter);column.addWidget(self.preview)
        self.parameters=QPlainTextEdit();self.parameters.setReadOnly(True);column.addWidget(self.parameters,1)
        self.links=QListWidget();column.addWidget(self.links)
        self.open_button=QPushButton('Открыть выбранный ресурс');column.addWidget(self.open_button)
        self.nodes.currentRowChanged.connect(self.select)
        self.links.itemActivated.connect(self.follow)
        self.open_button.clicked.connect(self.open_resource)

    def set_loading(self,busy):
        self.nodes.setEnabled(not busy);self.links.setEnabled(not busy);self.open_button.setEnabled(not busy)

    def clear(self):
        self.graph=None;self.nodes.clear();self.links.clear();self.preview.clear();self.parameters.clear()

    def load(self,graph):
        self.clear();self.graph=graph;self.nodes.blockSignals(True)
        for node in graph['nodes']:
            self.nodes.addItem(node.get('name',str(node['id']))+' · '+node.get('kind',node.get('error','')))
        self.nodes.blockSignals(False)
        self.info.setText(f'Граф: {len(graph["nodes"])} ресурсов · '
                          +('достигнут лимит' if graph['truncated'] else 'параметры и ссылки, без исполнения шейдеров'))
        self.nodes.setCurrentRow(0)

    def select(self,index):
        self.preview.clear();self.links.clear()
        if not self.graph or index<0:return
        node=self.graph['nodes'][index];doc=node.get('document',{})
        values=[]
        for tag in doc.get('tags',[]):
            value=tag.get('value',tag.get('bytes',tag.get('words',tag.get('elements',tag.get('members')))))
            if 'bits' in tag:value=dict(value=float_value(tag['bits']),bits=tag['bits'])
            values.append(dict(name=tag['name'],kind=tag['kind'],subscript=tag.get('subscript'),value=value))
        self.parameters.setPlainText(summary_text(dict(parameters=values,serialized=doc,error=node.get('error'))))
        for link in node['links']:
            text=f'{link["field"]} → {link["reference"]["path"]}'
            if 'error' in link:text+=' · '+link['error']
            self.links.addItem(text)
            self.links.item(self.links.count()-1).setData(Qt.UserRole,link.get('node'))
        self.requested.emit(index)

    def follow(self,item):
        index=item.data(Qt.UserRole)
        if index is not None:self.nodes.setCurrentRow(index)

    def open_resource(self):
        if self.graph and self.nodes.currentRow()>=0:
            node=self.graph['nodes'][self.nodes.currentRow()]
            self.navigate.emit(node['path'],node['id'])

    def display(self,result):
        if not result:return
        if 'error' in result:self.preview.setText(result['error']);return
        image=QImage(result['pixels'],result['width'],result['height'],result['width']*4,QImage.Format_RGBA8888).copy()
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(256,256,Qt.KeepAspectRatio,Qt.SmoothTransformation))
