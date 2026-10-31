"""UI scale metadata, rotations, and grouped preview diagnostics."""
import json

import pytest
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QDialog, QTreeWidget
from PySide6.QtCore import QSettings

from test_preview_textures import app, japan, korea
from preview_render import render_preview, ResourceCache, ScaleSettings, Notices, PREVIEW_PROFILES
from main import Editor


def child(doc, parent, name):
    return next(n['id'] for n in doc.children(parent) if n['name'] == name)


class Pattern:
    def image(self, name):
        image = QImage(40, 20, QImage.Format.Format_RGBA8888)
        for y in range(20):
            for x in range(40):
                image.setPixelColor(x, y, QColor('red' if x < 20 else 'blue'))
        return image, None


@pytest.mark.parametrize('angle,axis,first', [(-9999, (0, 1, 0), 'red'),
    (0, (0, 1, 0), 'red'), (180, (-9999, 1, -9999), 'blue'),
    (180, (-9999, -9999, 1), 'blue'), (180, (-9999, -9999, -9999), 'blue')])
def test_rotation_pixels_and_sentinel(angle, axis, first):
    application = app()
    p = dict(name='Texture', size=1, size_absolute_values=1, size_absolute_width=40,
             size_absolute_height=20, rotationAngle=angle, axisVectorX=axis[0],
             axisVectorY=axis[1], axisVectorZ=axis[2], file='Test.Image', alpha=255,
             colorModify=0xffffffff, type=0)
    snapshot = dict(schema='korea_native.XDAT', revision=1, selected=1, context=1,
                    root=dict(id=1, type='Texture', properties=p, children=[]),
                    scalableData={'scale0': dict(widthRate=100, heightRate=100)})
    before = json.dumps(snapshot)
    result = render_preview(snapshot, Pattern())
    assert not result.warnings
    assert result.image.pixelColor(17, 17) == QColor(first)
    assert json.dumps(snapshot) == before


def test_z_rotation_expands_isolated_crop():
    application = app()
    node = dict(id=1, type='Texture', properties=dict(name='rotated', size=1, size_absolute_values=1,
        size_absolute_width=40, size_absolute_height=20, rotationAngle=90, axisVectorZ=1,
        file='Test.Image', alpha=255, colorModify=0xffffffff, type=0), children=[])
    result = render_preview(dict(schema='ct26.XDAT', revision=0, selected=1, context=1, root=node), Pattern())
    assert (result.image.width(), result.image.height()) == (44, 64)
    assert result.image.pixelColor(17, 17) == QColor('red')
    assert result.image.pixelColor(17, 47) == QColor('blue')


@pytest.mark.parametrize('mode', [1, 2])
def test_ui_scale_applies_to_natural_and_tiled_texture_pixels(mode):
    application = app()
    node = dict(id=2, type='Texture', properties=dict(name='texture', size=1, size_absolute_values=1,
        size_absolute_width=40, size_absolute_height=20, file='Test.Image', alpha=255,
        colorModify=0xffffffff, type=mode), children=[])
    root = dict(id=1, type='Window', properties=dict(name='window', scalable=1, size=1,
        size_absolute_values=1, size_absolute_width=40, size_absolute_height=20), children=[node])
    snapshot = dict(schema='korea_native.XDAT', revision=0, selected=2, context=1, root=root,
                    scalableData={'scale100': dict(widthRate=200, heightRate=200)})
    result = render_preview(snapshot, Pattern(), ui_scale=100)
    assert result.image.size().width() == 104
    assert result.image.pixelColor(42, 17) == QColor('red')
    assert result.image.pixelColor(72, 17) == QColor('blue')


@pytest.mark.parametrize('factory', [japan, korea])
def test_scale_snapshot_fonts_geometry_and_undo(factory):
    application = app()
    doc, button = factory()
    schema = doc.summary()['schema'].split('.')[0]
    scalable = child(doc, 0, 'scalableData')
    scale = child(doc, scalable, 'scale50')
    doc.set_many(scale, dict(widthRate=150, heightRate=200))
    doc.set(0, 'hasFontDefinition', 1)
    fonts = child(doc, 0, 'fontDefinition')
    doc.set(fonts, 'defaultFontName', 'Base')
    definitions = child(doc, fonts, 'fonts')
    doc.add_configured(definitions, schema + '.Font.FontData', dict(name='Base', size=10))
    doc.add_configured(definitions, schema + '.Font.FontData', dict(name='Large', size=16))
    font_scale = child(doc, scalable, 'fontScale50')
    doc.set(font_scale, 'defaultFontName', 'Large')
    doc.add_configured(child(doc, font_scale, 'mappings'), schema + '.FontMapping', dict(name='Base', fontName='Large'))
    doc.set_many(button, dict(rotationAngle=-9999., size_absolute_values=0,
                             size_percent_width=.5, size_absolute_width=-10))
    original = doc.serialize()
    snapshot = doc.preview_snapshot(button)
    assert snapshot['scalableData']['scale50'] == dict(widthRate=150, heightRate=200)
    settings = ScaleSettings(snapshot, 50, Notices())
    font, name = settings.font({}, True)
    assert (name, font.pointSize()) == ('Large', 16)  # mapped size, not 16 * scale
    assert settings.font({}, False)[0].pointSize() == 10
    assert settings.font(dict(useFont=1, fontName='Unmapped'), True)[1] == 'Unmapped'
    result = render_preview(snapshot, ResourceCache(), True, ui_scale=50)
    assert result.rectangles[button] == (15, 40, 210, 60)
    assert doc.serialize() == original
    doc.set(scale, 'widthRate', 175)
    assert doc.preview_snapshot(button)['scalableData']['scale50']['widthRate'] == 175
    assert snapshot['scalableData']['scale50']['widthRate'] == 150
    doc.undo()
    assert doc.serialize() == original
    parent = doc.info(doc.info(button)['parent'])['parent']
    doc.set(parent, 'scalable', 0)
    fixed = render_preview(doc.preview_snapshot(button), ResourceCache(), True, ui_scale=50)
    assert fixed.rectangles[button] == (10, 20, 140, 30)
    doc.set(parent, 'scalable', -1)
    default = render_preview(doc.preview_snapshot(button), ResourceCache(), True, ui_scale=50)
    assert default.rectangles[button] == (10, 20, 140, 30)
    assert any(g['reason'] == 'Масштабирование не включено для окна' for g in default.warning_groups)


def test_grouped_warnings_and_clients_dialog(tmp_path):
    application = app()
    doc, button = korea()
    siblings = doc.info(button)['parent']
    doc.set(button, 'rotationAngle', -9999.)
    doc.add_configured(siblings, 'korea_native.Button', dict(name='Second', size=1,
        size_absolute_values=1, size_absolute_width=20, size_absolute_height=20,
        normalTex='Preview.Missing', rotationAngle=-9999.))
    result = render_preview(doc.preview_snapshot(button), ResourceCache(), True)
    group = next(g for g in result.warning_groups if g['reason'] == 'Не удалось загрузить текстуру')
    assert {e['element'] for e in group['entries']} == {'PreviewWindow.btnCredit', 'PreviewWindow.Second'}
    assert all('Preview.Missing' in e['detail'] for e in group['entries'])
    assert not any('поворот' in g['reason'] for g in result.warning_groups)
    window = Editor(QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    preview = window.panes[0].preview
    preview.show_notices([group])
    item = preview.details.topLevelItem(0)
    assert item.childCount() == 2 and item.text(0).endswith('2')
    assert item.child(0).text(0).startswith('btnCredit')
    assert 'PreviewWindow.btnCredit' in item.child(0).toolTip(0)
    assert not item.isExpanded()
    item.setExpanded(True)
    preview.retranslate()
    assert preview.details.topLevelItem(0).isExpanded()
    preview.clients.click()
    dialog = preview.findChild(QDialog)
    table = dialog.findChild(QTreeWidget)
    assert {table.topLevelItem(i).text(1) for i in range(table.topLevelItemCount())} == set(PREVIEW_PROFILES)
    dialog.close()
    window.close()
    application.processEvents()


def test_invalid_scale_falls_back_and_invalid_index_rejected():
    application = app()
    doc, button = korea()
    snapshot = doc.preview_snapshot(button)
    snapshot['scalableData']['scale50'] = dict(widthRate=0, heightRate=-1)
    result = render_preview(snapshot, ResourceCache(), ui_scale=50)
    assert result.rectangles[button][2:] == (98, 30)
    assert any(g['reason'] == 'Таблица масштаба недоступна' for g in result.warning_groups)
    with pytest.raises(ValueError, match='scale index'):
        render_preview(snapshot, ResourceCache(), ui_scale=101)
