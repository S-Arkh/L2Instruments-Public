import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from color_editor import ColorDialog, ColorEditor, pack_color, unpack_color


@pytest.mark.parametrize('kind,packed', [('color', 0x7f123456), ('rgba', 0x7f563412)])
def test_channel_order_and_initial_selection(kind, packed):
    app = QApplication.instance() or QApplication([])
    color = unpack_color(packed, kind)
    assert color.name() == '#123456'
    assert pack_color(color, packed, kind) == packed
    dialog = ColorDialog(packed, kind, lambda text: text)
    assert dialog.packed_value() == packed
    assert dialog.wheel.hue == pytest.approx(color.hsvHueF())
    assert dialog.wheel.saturation == pytest.approx(color.hsvSaturationF())
    assert dialog.brightness.value() == 0x56
    assert [slider.value() for slider in dialog.channels] == [0x12, 0x34, 0x56]
    assert dialog.code.text() == f'0x{packed:08X}'
    dialog.channels[0].setValue(0xab)
    changed = 0x7fab3456 if kind == 'color' else 0x7f5634ab
    assert dialog.packed_value() == changed
    assert dialog.code.text() == f'0x{changed:08X}'
    assert dialog.wheel.color().red() == 0xab
    dialog.brightness.setValue(255)
    dialog.wheel.select_position(QPointF(248.5, 124.5))
    expected = 0x7fff0000 if kind == 'color' else 0x7f0000ff
    assert dialog.packed_value() == expected
    assert [slider.value() for slider in dialog.channels] == [255, 0, 0]
    assert dialog.code.text() == f'0x{expected:08X}'
    dialog.close()


def test_manual_input_confirm_and_cancel():
    app = QApplication.instance() or QApplication([])
    errors, commits = [], []
    editor = ColorEditor(0x42123456, 'color', False, lambda text: text, errors.append)
    editor.committed.connect(commits.append)
    editor.input.setText('0x7F336699')
    editor.input.returnPressed.emit()
    assert commits == [0x7f336699]
    assert '#336699' in editor.swatch.styleSheet()

    for accept in (False, True):
        def interact():
            dialog = editor.findChild(ColorDialog)
            assert dialog.original == 0x7f336699
            dialog.brightness.setValue(255)
            dialog.wheel.select_position(QPointF(248.5, 124.5))
            buttons = dialog.findChild(QDialogButtonBox)
            role = QDialogButtonBox.ButtonRole.AcceptRole if accept else QDialogButtonBox.ButtonRole.RejectRole
            next(button for button in buttons.buttons() if buttons.buttonRole(button) == role).click()
        QTimer.singleShot(0, interact)
        editor.choose_color()
        if accept:
            assert commits == [0x7f336699, 0x7fff0000]
            assert editor.input.text() == '0x7FFF0000'
            assert '#ff0000' in editor.swatch.styleSheet()
        else:
            assert commits == [0x7f336699]
            assert editor.input.text() == '0x7F336699'
            assert '#336699' in editor.swatch.styleSheet()
        # Deliver deferred deletion before opening another child dialog.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    editor.input.setText('0x100000000')
    editor.input.returnPressed.emit()
    assert errors == ['Неверный формат значения']
    assert len(commits) == 2
    editor.close()
