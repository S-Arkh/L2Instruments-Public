"""Packed XDAT color editor with an explicit-commit HSV wheel."""
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QSlider, QToolButton, QVBoxLayout, QWidget,
)


def unpack_color(value, kind):
    red, green, blue = (value >> 16) & 255, (value >> 8) & 255, value & 255
    if kind == 'rgba':
        red, blue = blue, red
    return QColor(red, green, blue)


def pack_color(color, original, kind):
    red, green, blue = color.red(), color.green(), color.blue()
    if kind == 'rgba':
        red, blue = blue, red
    return (original & 0xff000000) | (red << 16) | (green << 8) | blue


def wheel_image(size, value=1.0):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    radius = (size - 2) / 2
    center = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            dx, dy = x - center, center - y
            saturation = math.hypot(dx, dy) / radius
            if saturation <= 1:
                hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1
                image.setPixelColor(x, y, QColor.fromHsvF(hue, saturation, value))
    return image


class ColorWheel(QWidget):
    changed = Signal()

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setFixedSize(250, 250)
        self.hue = max(0.0, color.hsvHueF())
        self.saturation = color.hsvSaturationF()
        self.value = color.valueF()
        self.image = wheel_image(250, self.value)

    def color(self):
        return QColor.fromHsvF(self.hue, self.saturation, self.value)

    def set_value(self, value):
        self.value = value / 255
        self.image = wheel_image(250, self.value)
        self.update()
        self.changed.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawImage(0, 0, self.image)
        angle = self.hue * 2 * math.pi
        radius = 124 * self.saturation
        point = QPointF(124.5 + math.cos(angle) * radius, 124.5 - math.sin(angle) * radius)
        painter.setPen(QPen(Qt.GlobalColor.black, 3))
        painter.drawEllipse(point, 5, 5)
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        painter.drawEllipse(point, 5, 5)

    def select_position(self, position):
        dx, dy = position.x() - 124.5, 124.5 - position.y()
        self.hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1
        self.saturation = min(1.0, math.hypot(dx, dy) / 124)
        self.update()
        self.changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.select_position(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.select_position(event.position())


class ColorDialog(QDialog):
    def __init__(self, value, kind, translate, parent=None):
        super().__init__(parent)
        self.original = value
        self.kind = kind
        self.selected_color = unpack_color(value, kind)
        self.setWindowTitle(translate('Выбрать цвет'))
        layout = QVBoxLayout(self)
        self.wheel = ColorWheel(self.selected_color)
        layout.addWidget(self.wheel, alignment=Qt.AlignmentFlag.AlignHCenter)
        controls = QHBoxLayout()
        sliders = QVBoxLayout()
        brightness_row = QHBoxLayout()
        brightness_row.addWidget(QLabel(translate('Яркость')))
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(0, 255)
        self.brightness.setValue(self.selected_color.value())
        self.brightness.valueChanged.connect(self.wheel.set_value)
        brightness_row.addWidget(self.brightness)
        sliders.addLayout(brightness_row)
        self.channels = []
        for name in ('R', 'G', 'B'):
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 255)
            slider.setMinimumWidth(150)
            slider.setAccessibleName(name)
            slider.valueChanged.connect(self.channels_changed)
            self.channels.append(slider)
            row.addWidget(slider)
            sliders.addLayout(row)
        controls.addLayout(sliders, 1)
        self.code = QLineEdit()
        self.code.setReadOnly(True)
        self.code.setFixedWidth(112)
        controls.addWidget(self.code)
        layout.addLayout(controls)
        self.preview = QLabel()
        self.preview.setFixedHeight(24)
        layout.addWidget(self.preview)
        self.wheel.changed.connect(self.color_changed)
        self.update_preview()
        buttons = QDialogButtonBox()
        buttons.addButton(translate('Подтвердить'), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(translate('Отмена'), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def color_changed(self):
        self.selected_color = self.wheel.color()
        self.update_preview()

    def channels_changed(self):
        self.selected_color = QColor(*(slider.value() for slider in self.channels))
        self.wheel.hue = max(0.0, self.selected_color.hsvHueF())
        self.wheel.saturation = self.selected_color.hsvSaturationF()
        self.wheel.value = self.selected_color.valueF()
        self.wheel.image = wheel_image(250, self.wheel.value)
        self.wheel.update()
        self.update_preview()

    def update_preview(self):
        self.preview.setStyleSheet(f'background-color: {self.selected_color.name()}; border: 1px solid #808080;')
        values = (self.selected_color.red(), self.selected_color.green(), self.selected_color.blue())
        for slider, value in zip(self.channels + [self.brightness], values + (self.selected_color.value(),)):
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        self.code.setText(f'0x{self.packed_value():08X}')

    def packed_value(self):
        return pack_color(self.selected_color, self.original, self.kind)


class ColorEditor(QWidget):
    committed = Signal(object)
    _icon = None

    def __init__(self, value, kind, readonly, translate, error, parent=None):
        super().__init__(parent)
        self.value, self.kind = value, kind
        self.translate, self.error = translate, error
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 2, 0)
        layout.setSpacing(4)
        self.input = QLineEdit(f'0x{value:08X}')
        self.input.setReadOnly(readonly)
        self.input.returnPressed.connect(self.commit_text)
        layout.addWidget(self.input, 1)
        self.swatch = QLabel()
        self.swatch.setFixedSize(18, 18)
        layout.addWidget(self.swatch)
        self.button = QToolButton()
        if ColorEditor._icon is None:
            ColorEditor._icon = QIcon(QPixmap.fromImage(wheel_image(24)))
        self.button.setIcon(ColorEditor._icon)
        self.button.setFixedSize(24, 24)
        self.button.setToolTip(translate('Выбрать цвет'))
        self.button.setEnabled(not readonly)
        self.button.clicked.connect(self.choose_color)
        layout.addWidget(self.button)
        self.update_swatch()

    def parsed_value(self):
        text = self.input.text().strip()
        try:
            value = int(text, 16 if text.lower().startswith('0x') else 10)
            if not 0 <= value <= 0xffffffff:
                raise ValueError
            return value
        except ValueError:
            self.error(self.translate('Неверный формат значения'))
            return None

    def update_swatch(self):
        color = unpack_color(self.value, self.kind)
        self.swatch.setStyleSheet(f'background-color: {color.name()}; border: 1px solid #808080;')
        self.swatch.setToolTip(f'0x{self.value:08X}')

    def commit(self, value):
        self.value = value
        self.input.setText(f'0x{value:08X}')
        self.update_swatch()
        self.committed.emit(value)

    def commit_text(self):
        if self.input.isReadOnly():
            return
        value = self.parsed_value()
        if value is not None:
            self.commit(value)

    def choose_color(self):
        value = self.parsed_value()
        if value is None:
            return
        dialog = ColorDialog(value, self.kind, self.translate, self)
        result = dialog.exec()
        selected = dialog.packed_value()
        dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted:
            self.commit(selected)
