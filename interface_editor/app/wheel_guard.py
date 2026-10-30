"""Keep wheel scrolling over property editors from silently changing XDAT values."""
from PySide6.QtCore import QObject, QEvent, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget, QComboBox, QAbstractSpinBox


class PropertyWheelGuard(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        QApplication.instance().installEventFilter(self)

    def uninstall(self):
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or self.window.wheel_values.isChecked() or not isinstance(watched, QWidget):
            return False
        for pane in self.window.panes:
            if not pane.table.isAncestorOf(watched):
                continue
            control = watched
            while control is not None and control is not pane.table:
                if isinstance(control, (QComboBox, QAbstractSpinBox)):
                    viewport = pane.table.viewport()
                    position = QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint()))
                    forwarded = QWheelEvent(position, event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                                            event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                                            event.source(), event.pointingDevice())
                    QApplication.sendEvent(viewport, forwarded)
                    event.accept()
                    return True
                control = control.parentWidget()
        return False
