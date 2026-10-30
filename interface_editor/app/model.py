"""Lazy Qt views of a single C++ document. No Python copy of the XDAT graph."""
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, QSortFilterProxyModel
from PySide6.QtGui import QFont
from i18n import text


class Item:
    def __init__(self, data, parent=None, row=0):
        self.data = data
        self.parent = parent
        self.row = row
        self.children = None


class TreeModel(QAbstractItemModel):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.language = 'ru'
        self.reset_document()

    def set_language(self, language):
        self.language = language
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, 1)

    def reset_document(self):
        self.beginResetModel()
        self.root = Item(self.document.info(0))
        self.items = {self.root.data['id']: self.root}
        self.endResetModel()

    def item(self, index):
        return index.internalPointer() if index.isValid() else self.root

    def columnCount(self, parent=QModelIndex()):
        return 2

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self.item(parent).children or [])

    def hasChildren(self, parent=QModelIndex()):
        return (not parent.isValid() or parent.column() == 0) and self.item(parent).data['children'] > 0

    def canFetchMore(self, parent):
        item = self.item(parent)
        return (not parent.isValid() or parent.column() == 0) and item.children is None and item.data['children'] > 0

    def fetchMore(self, parent):
        if not self.canFetchMore(parent):
            return
        item = self.item(parent)
        rows = self.document.children(item.data['id'])
        if rows:
            self.beginInsertRows(parent, 0, len(rows) - 1)
        item.children = [Item(row, item, i) for i, row in enumerate(rows)]
        self.items.update((child.data['id'], child) for child in item.children)
        if rows:
            self.endInsertRows()

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()
        item = self.item(parent)
        if column < 0 or column >= 2 or not item.children or not 0 <= row < len(item.children):
            return QModelIndex()
        return self.createIndex(row, column, item.children[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        parent = self.item(index).parent
        if parent is None or parent is self.root:
            return QModelIndex()
        return self.createIndex(parent.row, 0, parent)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.item(index)
        if role == Qt.ItemDataRole.DisplayRole:
            return item.data['name'] if index.column() == 0 else item.data['type']
        if role == Qt.ItemDataRole.UserRole:
            return item.data['id']
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{item.data['name']} [{item.data['type']}] — ID {item.data['id']}"
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return text(self.language, ('Объект', 'Тип')[section])
        return None

    def index_for_id(self, node_id):
        if node_id == self.root.data['id']:
            return QModelIndex()
        if node_id not in self.items:
            info = self.document.info(node_id)
            parent_index = self.index_for_id(info['parent'])
            self.fetchMore(parent_index)
        item = self.items.get(node_id)
        return self.createIndex(item.row, 0, item) if item else QModelIndex()

    def refresh_node(self, node_id):
        item = self.items.get(node_id)
        if item:
            row = self.document.info(node_id)
            structural = row['children'] != item.data['children']
            if item.children is not None:
                structural |= [c.data['id'] for c in item.children] != [c['id'] for c in self.document.children(node_id)]
            item.data = row
            if structural:
                return False
            left = self.index_for_id(node_id)
            self.dataChanged.emit(left, left.siblingAtColumn(1))
        return True


class TreeFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.visible = None
        self.matches = set()
        self.setDynamicSortFilter(True)

    def set_visible(self, ids, matches=()):
        self.beginFilterChange()
        self.visible = None if ids is None else set(ids)
        self.matches = set(matches)
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.FontRole and index.data(Qt.ItemDataRole.UserRole) in self.matches:
            font = QFont()
            font.setBold(True)
            return font
        return super().data(index, role)

    def filterAcceptsRow(self, source_row, source_parent):
        if self.visible is None:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        return index.data(Qt.ItemDataRole.UserRole) in self.visible
