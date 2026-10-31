import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import struct
import sys
import time

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from _interface_core import Document, TextureStore, decode_texture
from texture_project import TextureProject, image_rgba
from preview_render import ResourceCache, render_preview, Layout, preview_root
from main import Editor


def app():
    return QApplication.instance() or QApplication([])


def image_file(path, width=30, height=20, color=QColor(240, 30, 50, 180)):
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(color)
    assert image.save(str(path))
    return path


def hf():
    d = Document((ROOT / 'schemas/schemas.json').read_text())
    d.load(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT')
    credit = next(n for n in d.search('btnCredit')['matches'] if d.info(n)['type'] == 'Button')
    return d, credit


def gracia():
    return synthetic_preview('ct24')


def japan():
    return synthetic_preview('essence_native')


def korea():
    return synthetic_preview('korea_native')


def synthetic_preview(profile):
    doc = Document((ROOT / 'schemas/schemas.json').read_text())
    doc.create(profile + '.XDAT')
    windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
    parent = doc.add_configured(windows, profile + '.Window', dict(name='PreviewWindow', size=1,
        size_absolute_values=1, size_absolute_width=300, size_absolute_height=240))
    if profile != 'ct24':
        doc.set(parent, 'scalable', 1)
        scalable = next(n['id'] for n in doc.children() if n['name'] == 'scalableData')
        for n in doc.children(scalable):
            if n['name'].startswith('scale'):
                rate = 100 + int(n['name'][5:])
                doc.set_many(n['id'], dict(widthRate=rate, heightRate=rate))
    children = next(n['id'] for n in doc.children(parent) if n['name'] == 'children')
    position = dict(anchor=1, anchor_parent=1, anchor_this=1) if profile == 'ct24' else dict(
        usePosition=1, relativePoint=1, anchorPoint=1)
    credit = doc.add_configured(children, profile + '.Button', dict(name='btnCredit', size=1,
        size_absolute_values=1, size_absolute_width=98, size_absolute_height=30,
        anchor_x=10.0, anchor_y=20.0,
        normalTex='Preview.Missing', buttonNameText='Test', **position))
    # Reload to establish a clean baseline, including serialization of the conditional fields.
    payload = doc.serialize()
    doc.load_bytes(payload, profile + '.XDAT')
    credit = next(n for n in doc.search('btnCredit')['matches'] if doc.info(n)['type'] == 'Button')
    return doc, credit


def test_pixel_decoders():
    assert decode_texture(5, 1, 1, b'\x12\x34\x56\x78')['rgba'] == b'\x56\x34\x12\x78'
    red = struct.pack('<HHI', 0xf800, 0x07e0, 0)
    assert decode_texture(3, 4, 4, red)['rgba'] == bytes([255, 0, 0, 255]) * 16
    transparent = struct.pack('<HHI', 0, 0xffff, 0xffffffff)
    assert decode_texture(3, 4, 4, transparent)['rgba'] == bytes(64)
    assert decode_texture(7, 4, 4, bytes([0x88]) * 8 + red)['rgba'] == bytes([255, 0, 0, 136]) * 16
    alpha = sum(2 << (3*i) for i in range(16))
    block = bytes([0, 255]) + alpha.to_bytes(6, 'little') + red
    assert decode_texture(8, 3, 2, block)['rgba'] == bytes([255, 0, 0, 51]) * 6
    palette = bytearray(1024); palette[4:8] = bytes([10, 20, 30, 0])
    assert decode_texture(0, 2, 1, b'\0\1', bytes(palette), True)['rgba'] == bytes([0, 0, 0, 0, 10, 20, 30, 255])
    assert decode_texture(10, 1, 1, b'\x00\x80')['rgba'] == bytes([128, 128, 128, 255])
    with pytest.raises(RuntimeError): decode_texture(3, 4, 4, b'bad')
    with pytest.raises(RuntimeError): decode_texture(5, 0, 0, b'')


def test_project_build_replace_install_and_foreign_package(tmp_path):
    application = app()
    project = TextureProject.create(tmp_path / 'project')
    source = image_file(tmp_path / 'button.png')
    with pytest.raises(ValueError): project.add_image(source, 'Test', pad=False)
    assert not project.data['assets']
    asset = project.add_image(source, 'Test', pad=True)
    assert (asset['width'], asset['height']) == (32, 32)
    assert (asset['content_width'], asset['content_height']) == (30, 20)
    assert not project.build_info()
    output = project.build()
    original = output.read_bytes()
    texture = TextureStore(str(output.parent)).load(project.reference(asset))
    expected, _, _ = image_rgba(project.asset_path(asset['image']))
    assert texture['rgba'] == bytes(expected.constBits())
    assert texture['grid'] == [0, 30, 30, 0, 20, 20]
    assert project.build_info()['pixel_roundtrip']
    project.build()
    assert output.read_bytes() == original
    client = tmp_path / 'client/SysTextures'; client.mkdir(parents=True)
    stock = client / 'L2UI_CT1.utx'; stock.write_bytes(b'untouched stock file')
    installed = project.install(client)
    assert installed.read_bytes() == original
    changed = image_file(tmp_path / 'changed.png', color=QColor(0, 255, 0, 255))
    project.add_image(changed, 'Test', pad=True, replace_id=asset['id'])
    assert not project.build_info()
    project.build(); project.install(client)
    assert installed.read_bytes() != original
    assert installed.with_suffix('.utx.bak').read_bytes() == original
    assert stock.read_bytes() == b'untouched stock file'
    other = TextureProject.create(tmp_path / 'other')
    other.add_image(source, 'Other', pad=True); other.build()
    with pytest.raises(ValueError): other.install(client)
    with pytest.raises(ValueError): TextureProject.create(tmp_path / 'bad', 'L2UI_CT1')
    reopened = TextureProject(project.file)
    assert reopened.reference(reopened.data['assets'][0]) == 'L2UI_Custom.Buttons.Test'


def test_atomic_texture_assignment_and_button_wizard_core():
    doc, credit = hf(); original = doc.serialize()
    with pytest.raises(RuntimeError): doc.set_many(credit, {'normalTex': 'Test.Button', 'size_absolute_width': 2**40})
    assert doc.serialize() == original and not doc.summary()['undo']
    doc.set_many(credit, {'normalTex': 'L2UI_Custom.Buttons.Normal', 'pushedTex': 'L2UI_Custom.Buttons.Pressed'})
    assert doc.summary()['undo'] == 1
    doc.undo(); assert doc.serialize() == original
    parent = doc.info(credit)['parent']
    new = doc.add_configured(parent, 'ct26.Button', dict(name='btnNativeTest', normalTex='L2UI_Custom.Buttons.Normal',
        size=1, size_absolute_values=1, size_absolute_width=80, size_absolute_height=30,
        usePosition=1, relativePoint=1, anchorPoint=1, anchor_x=5.0, anchor_y=6.0, buttonNameText='Test'))
    assert doc.info(new)['name'] == 'btnNativeTest'
    assert doc.summary()['undo'] == 1
    doc.undo(); assert doc.serialize() == original
    doc.redo(); assert doc.info(new)['name'] == 'btnNativeTest'


@pytest.mark.parametrize('factory', [hf, gracia, japan, korea], ids=['hf', 'gracia', 'japan', 'korea'])
def test_layout_and_static_preview_do_not_change_document(tmp_path, factory):
    application = app()
    doc, credit = factory(); original = doc.serialize()
    snapshot = doc.preview_snapshot(credit)
    result = render_preview(snapshot, ResourceCache(), context=True)
    assert result.rectangles[credit] == (10.0, 20.0, 98.0, 30.0)
    assert result.image.width() == 324 and result.image.height() == 264
    assert result.warnings and not result.textures
    assert doc.serialize() == original and not doc.summary()['dirty']
    node = dict(id=1, type='Window', properties=dict(name='parent', size=1, size_absolute_values=1,
        size_absolute_width=200, size_absolute_height=100), children=[dict(id=2, type='Texture',
        properties=dict(name='child', size=1, size_absolute_values=0, size_percent_width=1.0,
        size_percent_height=.5, size_absolute_width=-20, size_absolute_height=0, usePosition=1,
        relativePoint=9, anchorPoint=9, anchor_x=-5, anchor_y=-2), children=[])])
    layout = Layout(node)
    rect = layout.rect(2)
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (15, 48, 180, 50)


@pytest.mark.parametrize('profile,factory', [('ct24', gracia), ('essence_native', japan),
                                           ('korea_native', korea)], ids=['gracia', 'japan', 'korea'])
def test_controls_anchors_states_and_snapshot_isolation(tmp_path, profile, factory):
    application = app()
    doc, credit = factory()
    siblings = doc.info(credit)['parent']
    position = dict(anchor=1, anchor_parent=9, anchor_this=1, anchor_ctrl='btnCredit') if profile == 'ct24' else dict(
        usePosition=1, relativePoint=9, anchorPoint=1, relativeTo='btnCredit')
    common = dict(size=1, size_absolute_values=1, size_absolute_width=40, size_absolute_height=20,
                  anchor_x=2.0, anchor_y=3.0, **position)
    font = {'text_color' if profile == 'ct24' else 'fontColor': 0xff12ab34}
    ids = {}
    for kind, extra in [('Texture', dict(file='Preview.Texture', alpha=255, type=0, colorModify=0xffffffff)),
                        ('TextBox', dict(text='日本語', useFont=1, **font)),
                        ('ScrollArea', {})]:
        ids[kind] = doc.add_configured(siblings, profile + '.' + kind, dict(common, name=kind, **extra))
    doc.set_many(credit, dict(normalTex='Preview.Normal', pushedTex='Preview.Pressed',
                              highlightTex='Preview.Hover', buttonNameText=''))
    doc.set_many(ids['ScrollArea'], dict(size_absolute_values=0, size_percent_width=.5,
                                       size_percent_height=.5, size_absolute_width=-10,
                                       size_absolute_height=0))
    original = doc.serialize()
    snapshot = doc.preview_snapshot(credit)
    before = json.dumps(snapshot, sort_keys=True)

    class Resources:
        def image(self, name):
            image = QImage(8, 8, QImage.Format.Format_RGBA8888)
            image.fill(QColor({'Preview.Normal': 'red', 'Preview.Pressed': 'green',
                              'Preview.Hover': 'blue'}.get(name, 'white')))
            return image, None

    images = []
    for state, texture in [('normal', 'Normal'), ('pressed', 'Pressed'), ('hover', 'Hover')]:
        result = render_preview(snapshot, Resources(), context=True, state=state)
        assert 'Preview.' + texture in result.textures
        assert 'Preview.Texture' in result.textures
        assert [g['reason'] for g in result.warning_groups] == ([] if profile == 'ct24' else [
            'Шрифт отображается приближённо'])
        assert result.rectangles[ids['Texture']] == (110, 53, 40, 20)
        assert result.rectangles[ids['ScrollArea']] == (110, 53, 140, 120)
        images.append(result.image)
    assert images[0] != images[1] and images[1] != images[2]
    normalized = Layout(preview_root(snapshot))
    assert normalized.nodes[ids['TextBox']]['properties']['fontColor'] == 0xff12ab34
    assert json.dumps(snapshot, sort_keys=True) == before
    assert doc.serialize() == original


@pytest.mark.parametrize('factory', [japan, korea], ids=['japan', 'korea'])
def test_modern_parent_size_and_rotation_notice(factory):
    application = app()
    doc, credit = factory()
    doc.set_many(credit, dict(equalToParentSize=1, rotationAngle=15.0, buttonNameText='', buttonName=42))
    result = render_preview(doc.preview_snapshot(credit), ResourceCache(), strings={42: '日本語'})
    assert result.rectangles[credit] == (10, 20, 300, 240)
    assert any(g['reason'] == 'Неподдерживаемая ось/угол поворота' for g in result.warning_groups)
    assert not any('SysString' in warning for warning in result.warnings)


@pytest.mark.parametrize('schema', ['ct23.XDAT', 'ct25.XDAT', 'etoa5.XDAT'])
def test_other_preview_profiles_remain_unsupported(schema):
    with pytest.raises(ValueError, match='Gracia Epilogue'):
        render_preview({'schema': schema}, ResourceCache())


@pytest.mark.skipif(not os.environ.get('INTERFACE_CLIENT_RESOURCES'), reason='Set INTERFACE_CLIENT_RESOURCES for real UTX validation')
def test_actual_client_textures():
    application = app()
    resources = os.environ['INTERFACE_CLIENT_RESOURCES']
    store = TextureStore(resources)
    first = store.load('L2UI_CT1.Button.Button_DF')
    assert first['width'] == 32 and first['split9']
    store.load('L2UI_CT1.Windows.Windows_DF_Drawer_Bg')
    assert store.package_reads == 1
    doc, credit = hf()
    doc.set(credit, 'normalTex', 'L2UI_CT1.Button.Button_DF')
    result = render_preview(doc.preview_snapshot(credit), ResourceCache(resources), True)
    assert 'L2UI_CT1.Button.Button_DF' in result.textures


@pytest.mark.parametrize('factory', [hf, gracia, japan, korea], ids=['hf', 'gracia', 'japan', 'korea'])
def test_preview_tabs_refresh_stale_result_and_png(tmp_path, factory):
    application = app()
    project = TextureProject.create(tmp_path / 'project')
    source = image_file(tmp_path / 'button.png', 32, 32)
    asset = project.add_image(source, 'Test'); project.build()
    window = Editor(QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    errors = []; window.error = errors.append
    window.texture_project = project; window.reload_resources(); window.show()
    def wait(predicate):
        deadline = time.monotonic() + 30
        while not predicate():
            application.processEvents(); time.sleep(.01)
            assert time.monotonic() < deadline, errors
        application.processEvents(); assert not errors
    source_doc, _ = factory()
    source_path = tmp_path / 'source.xdat'
    source_doc.save(str(source_path))
    window.load_file(str(source_path), source_doc.summary()['schema'])
    wait(lambda: not window.busy)
    doc = window.document
    credit = next(n for n in doc.search('btnCredit')['matches'] if doc.info(n)['type'] == 'Button')
    doc.set_many(credit, {'normalTex': project.reference(asset), 'buttonNameText': 'Custom'})
    left, right = window.panes
    left.reveal(credit); right.reveal(credit)
    left.tabs.setCurrentIndex(1)
    wait(lambda: left.preview.result is not None)
    assert right.tabs.currentIndex() == 0 and not window.shared_scroll.isVisible()
    assert left.preview.result.textures == [project.reference(asset)]
    wait(lambda: left.preview.canvas.width() <= left.preview.scroll.viewport().width()
         and left.preview.canvas.height() <= left.preview.scroll.viewport().height())
    before = doc.serialize()
    left.preview.context.setCurrentIndex(1)
    wait(lambda: left.preview.result is not None)
    assert doc.serialize() == before
    parent = doc.info(doc.info(credit)['parent'])['parent']
    left.reveal(parent); left.reveal(credit)
    wait(lambda: left.preview.result is not None)
    assert left.preview.result.selected == credit
    output = tmp_path / 'preview.png'; left.preview.export_png(output)
    wait(lambda: output.exists() and not window.tasks)
    assert not QImage(str(output)).isNull()
    if factory in (japan, korea):
        assert left.preview.ui_scale.isEnabled()
        before_scale = doc.serialize()
        left.preview.ui_scale.setValue(50)
        wait(lambda: left.preview.result is not None)
        assert left.preview.result.rectangles[credit][2] == 147
        assert doc.serialize() == before_scale
        left.preview.ui_scale.setValue(0)
        wait(lambda: left.preview.result is not None)
    window.edit(credit, 'size_absolute_width', 120)
    wait(lambda: not window.busy and left.preview.result is not None)
    assert left.preview.result.rectangles[credit][2] == 120
    window.history(False)
    wait(lambda: not window.busy and left.preview.result is not None)
    assert left.preview.result.rectangles[credit][2] == 98
    left.tabs.setCurrentIndex(0)
    wait(lambda: not window.tasks)
    doc.save(str(tmp_path / 'modified.xdat'))
    window.close(); application.processEvents()


def test_assignment_dialog_and_button_creation_are_single_commands(tmp_path, monkeypatch):
    from texture_manager import TextureBindingsDialog
    from PySide6.QtWidgets import QDialog
    application = app()
    project = TextureProject.create(tmp_path / 'project')
    image = image_file(tmp_path / 'state.png', 64, 32)
    normal = project.add_image(image, 'Normal')
    pressed = project.add_image(image, 'Pressed')
    project.build()
    window = Editor(QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    window.texture_project = project
    errors = []; window.error = errors.append
    window.show()
    def wait():
        deadline = time.monotonic() + 30
        while window.busy or window.tasks:
            application.processEvents(); time.sleep(.01)
            assert time.monotonic() < deadline, errors
        application.processEvents(); assert not errors, errors
    window.load_file(str(ROOT / 'tests/fixtures/Interface_high_five.xdat'), 'ct26.XDAT'); wait()
    doc = window.document; original = doc.serialize()
    credit = next(n for n in doc.search('btnCredit')['matches'] if doc.info(n)['type'] == 'Button')
    window.active = window.panes[0]; window.active.reveal(credit)
    def accept(dialog):
        dialog.fields['pushedTex'].setCurrentIndex(dialog.fields['pushedTex'].findData(project.reference(pressed)))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(TextureBindingsDialog, 'exec', accept)
    window.assign_project_textures(normal['id']); wait()
    props = {p['name']: p['value'] for p in doc.properties(credit)}
    assert props['normalTex'] == project.reference(normal)
    assert props['pushedTex'] == project.reference(pressed)
    assert doc.summary()['undo'] == 1
    window.history(False); wait(); assert doc.serialize() == original
    window.create_texture_button(normal['id']); wait()
    added = window.active.node_id
    assert doc.info(added)['name'] == 'btnNativeTest'
    assert doc.summary()['undo'] == 1
    props = {p['name']: p['value'] for p in doc.properties(added)}
    assert props['size_absolute_width'] == 64 and props['parentName'] == 'LoginMenuWnd'
    window.history(False); wait(); assert doc.serialize() == original
    window.close(); application.processEvents()
