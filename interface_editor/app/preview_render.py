"""Static client UI mockups painted on QImage, suitable for background workers."""
from collections import OrderedDict
from dataclasses import dataclass, field
import math
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QFont, QTransform
from _interface_core import TextureStore


PREVIEW_PROFILES = {
    'ct24.XDAT': 'Gracia Epilogue',
    'ct26.XDAT': 'High Five',
    'essence_native.XDAT': 'Essence / Japan (normal / Classic)',
    'korea_native.XDAT': 'Korea (normal / Classic)',
}
SUPPORTED_PREVIEW_SCHEMAS = frozenset(PREVIEW_PROFILES)
SCALABLE_PREVIEW_SCHEMAS = frozenset(('essence_native.XDAT', 'korea_native.XDAT'))


class Notices:
    def __init__(self):
        self.groups = OrderedDict()

    def add(self, reason, element='', detail=''):
        entries = self.groups.setdefault(reason, OrderedDict())
        entries[(element, detail)] = dict(element=element, detail=detail)

    def grouped(self):
        return [dict(reason=reason, entries=list(entries.values())) for reason, entries in self.groups.items()]

    def messages(self):
        return [reason + (': ' + ' — '.join(v for v in (element, detail) if v) if element or detail else '')
                for reason, entries in self.groups.items() for element, detail in entries]


def rotation_transform(properties, rect):
    """Static centre-pivot transform; never interpret the XDAT -9999 sentinel as an angle."""
    angle = number(properties.get('rotationAngle'))
    if angle == -9999 or angle % 360 == 0:
        return QTransform(), ''
    axis = [number(properties.get('axisVector' + key), -9999) for key in 'XYZ']
    axis = [0., 0., 1.] if all(value == -9999 for value in axis) else [0 if value == -9999 else value for value in axis]
    transform = QTransform()
    center = rect.center()
    transform.translate(center.x(), center.y())
    if axis[0] == axis[1] == 0 and axis[2] != 0:
        transform.rotate(angle if axis[2] > 0 else -angle)
    elif angle % 360 == 180 and sum(v != 0 for v in axis) == 1:
        transform.scale(-1 if axis[1] else 1, -1 if axis[0] else 1)
    else:
        return QTransform(), 'Неподдерживаемая ось/угол поворота'
    transform.translate(-center.x(), -center.y())
    return transform, ''


class ScaleSettings:
    def __init__(self, snapshot, index, notices):
        if not isinstance(index, int) or not 0 <= index <= 100:
            raise ValueError('UI scale index must be between 0 and 100')
        self.index = index
        self.rates = (1., 1.)
        self.font_table = {}
        self.fonts = {f['name']: f for f in snapshot.get('fontDefinition', {}).get('fonts', [])}
        self.default_font = snapshot.get('fontDefinition', {}).get('defaultFontName', '')
        self.styles = {s['name']: s for s in snapshot.get('styles', [])}
        self.modern = snapshot['schema'] in SCALABLE_PREVIEW_SCHEMAS
        if not self.modern:
            return
        data = snapshot.get('scalableData', {})
        entry = data.get('scale' + str(index), {})
        rates = (number(entry.get('widthRate')), number(entry.get('heightRate')))
        if all(0 < rate <= 1000 for rate in rates):
            self.rates = tuple(rate / 100 for rate in rates)
            self.font_table = data.get('fontScale' + str(index), {})
        else:
            notices.add('Таблица масштаба недоступна', detail=str(index))

    def font(self, properties, scaled):
        name = self.default_font
        if properties.get('useFont') == 1:
            style = self.styles.get(properties.get('styleName'), {})
            name = style.get('fontName', name)
            if useful(properties.get('fontName')):
                name = properties['fontName']
        if scaled and self.font_table:
            mapping = {m['name']: m['fontName'] for m in self.font_table.get('mappings', [])}
            name = mapping.get(name, name) if useful(name) else self.font_table.get('defaultFontName', '')
        definition = self.fonts.get(name, {})
        size = number(definition.get('size'), 10)
        return QFont('Arial', max(1, min(128, round(size)))), name


def preview_root(snapshot):
    """Normalize known Gracia fields without modifying the document snapshot."""
    if snapshot['schema'] not in SUPPORTED_PREVIEW_SCHEMAS:
        raise ValueError('Preview supports Gracia Epilogue, High Five, Japan (Essence/Japan profile) and Korea')
    if snapshot['schema'] != 'ct24.XDAT':
        return snapshot['root']

    def adapt(node):
        properties = dict(node['properties'])
        for source, target in (('anchor', 'usePosition'), ('anchor_parent', 'relativePoint'),
                               ('anchor_this', 'anchorPoint'), ('anchor_ctrl', 'relativeTo'),
                               ('text_color', 'fontColor')):
            if source in properties:
                properties[target] = properties[source]
        return dict(node, properties=properties, children=[adapt(child) for child in node['children']])

    return adapt(snapshot['root'])


def number(value, default=0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def useful(value):
    return isinstance(value, str) and value.strip().lower() not in ('', 'undefined', 'none')


class ResourceCache:
    """Immutable configuration; each change/refresh creates a new cache instance."""
    def __init__(self, directory='', overlays=()):
        self.directory = str(directory)
        self.directories = list(dict.fromkeys([str(p) for p in overlays if p] + ([self.directory] if self.directory else [])))
        self.stores = {}
        self.images = OrderedDict()
        self.failures = {}
        self.bytes = 0
        self.lock = threading.RLock()
        self.store_errors = {}

    def image(self, name):
        key = name.casefold()
        with self.lock:
            if key in self.images:
                self.images.move_to_end(key)
                return self.images[key]
            if key in self.failures:
                raise ValueError(self.failures[key])
            try:
                if not self.directories:
                    raise ValueError('Choose the client resource directory in Options')
                errors = []
                texture = None
                for directory in self.directories:
                    try:
                        if directory in self.store_errors:
                            raise ValueError(self.store_errors[directory])
                        if directory not in self.stores:
                            try:
                                self.stores[directory] = TextureStore(directory)
                            except Exception as error:
                                self.store_errors[directory] = str(error)
                                raise
                        texture = self.stores[directory].load(name)
                        break
                    except Exception as error:
                        errors.append(str(error))
                if texture is None:
                    raise ValueError('; '.join(errors))
                image = QImage(texture['rgba'], texture['width'], texture['height'], texture['width'] * 4, QImage.Format.Format_RGBA8888).copy()
                size = image.sizeInBytes()
                while self.images and self.bytes + size > 32 * 1024 * 1024:
                    _, (old, _) = self.images.popitem(last=False)
                    self.bytes -= old.sizeInBytes()
                if size <= 32 * 1024 * 1024:
                    self.images[key] = image, texture['grid'] if texture['split9'] else None
                    self.bytes += size
                return image, texture['grid'] if texture['split9'] else None
            except Exception as error:
                if len(self.failures) > 1024:
                    self.failures.clear()
                self.failures[key] = str(error)
                raise ValueError(str(error)) from error


@dataclass
class RenderResult:
    image: QImage
    selected: int
    revision: int
    warnings: list
    textures: list
    rectangles: dict
    logical_size: tuple
    warning_groups: list = field(default_factory=list)


class Layout:
    def __init__(self, root, rates=(1., 1.)):
        self.nodes = {}
        self.parents = {}
        self.paths = {}
        self.names = {}
        self.rects = {}
        self.pending = set()
        self.warnings = []
        self.scaled = {}
        self.rates = rates
        self.node_paths = {}
        self.root = root['id']
        self.viewport = QRectF(0, 0, 1280, 720)

        def visit(node, parent=None, prefix='', scalable=False):
            ident = node['id']
            self.nodes[ident] = node
            self.parents[ident] = parent
            name = node['properties'].get('name', str(ident))
            path = prefix + name
            if node['type'] == 'Window' and node['properties'].get('scalable') in (0, 1):
                scalable = node['properties']['scalable'] == 1
            self.scaled[ident] = scalable
            self.node_paths[ident] = path
            self.paths[path.casefold()] = ident
            self.names.setdefault(name.casefold(), []).append(ident)
            for child in node['children']:
                visit(child, ident, path + '.', scalable)
        visit(root)

    def reference(self, node_id, name):
        parent = self.parents[node_id]
        if not useful(name):
            return self.rect(parent) if parent is not None else self.viewport
        target = self.paths.get(name.casefold())
        if target is None:
            matches = self.names.get(name.casefold(), [])
            siblings = [i for i in matches if self.parents[i] == parent]
            if len(siblings) == 1:
                target = siblings[0]
            elif len(matches) == 1:
                target = matches[0]
        if target is None or target == node_id:
            self.warnings.append('Не найдена привязка: ' + name)
            return self.rect(parent) if parent is not None and parent not in self.pending else self.viewport
        return self.rect(target)

    @staticmethod
    def anchor(value):
        value = int(number(value))
        return ((value - 1) % 3 / 2, (value - 1) // 3 / 2) if 1 <= value <= 9 else (0, 0)

    def rect(self, node_id):
        if node_id in self.rects:
            return self.rects[node_id]
        if node_id in self.pending:
            self.warnings.append('Циклическая привязка')
            return QRectF(0, 0, 100, 30)
        self.pending.add(node_id)
        node = self.nodes[node_id]
        p = node['properties']
        sx, sy = self.rates if self.scaled[node_id] else (1., 1.)
        container = node['type'] in ('Window', 'ScrollArea')
        width, height = (320, 200) if container else (100, 28)
        if p.get('size') == 1:
            width = number(p.get('size_absolute_width'), width) * sx
            height = number(p.get('size_absolute_height'), height) * sy
            if p.get('size_absolute_values') == 0:
                reference = self.reference(node_id, p.get('size_percent_window', ''))
                width += reference.width() * number(p.get('size_percent_width'))
                height += reference.height() * number(p.get('size_percent_height'))
        width, height = max(0, min(width, 8192)), max(0, min(height, 8192))
        parent = self.parents[node_id]
        reference = self.rect(parent) if parent is not None else self.viewport
        if p.get('equalToParentSize') == 1:
            width, height = reference.width(), reference.height()
        x, y = reference.x(), reference.y()
        if node_id == self.root:
            x = y = 0  # Crop to the window, not its screen position.
        elif p.get('usePosition') == 1:
            reference = self.reference(node_id, p.get('relativeTo', ''))
            rx, ry = self.anchor(p.get('relativePoint'))
            ax, ay = self.anchor(p.get('anchorPoint'))
            x = reference.x() + reference.width() * rx - width * ax + number(p.get('anchor_x')) * sx
            y = reference.y() + reference.height() * ry - height * ay + number(p.get('anchor_y')) * sy
        rect = QRectF(x, y, width, height)
        self.rects[node_id] = rect
        self.pending.remove(node_id)
        return rect


def draw_nine_slice(painter, destination, image, grid, rates=(1., 1.)):
    """Split9 values are cumulative source coordinates, not border widths."""
    if not grid:
        painter.drawImage(destination, image)
        return
    x1, x2, x3, y1, y2, y3 = grid
    if not (0 <= x1 <= x2 <= x3 <= image.width() and 0 <= y1 <= y2 <= y3 <= image.height() and x3 and y3):
        painter.drawImage(destination, image)
        return

    def axis(a, b, c, size, rate):
        # A zero stretch region is a fixed-height strip (e.g. Button_DF).
        if a == b:
            return [0, c], [0, size]
        left, right = a * rate, (c - b) * rate
        scale = min(1.0, size / (left + right)) if left + right else 1.0
        return [0, a, b, c], [0, left * scale, size - right * scale, size]
    sx, dx = axis(x1, x2, x3, destination.width(), rates[0])
    sy, dy = axis(y1, y2, y3, destination.height(), rates[1])
    for yi in range(len(sy) - 1):
        for xi in range(len(sx) - 1):
            src = QRectF(sx[xi], sy[yi], sx[xi + 1] - sx[xi], sy[yi + 1] - sy[yi])
            dst = QRectF(destination.x() + dx[xi], destination.y() + dy[yi], dx[xi + 1] - dx[xi], dy[yi + 1] - dy[yi])
            if src.width() > 0 and src.height() > 0 and dst.width() > 0 and dst.height() > 0:
                painter.drawImage(dst, image, src)


def render_preview(snapshot, resources, context=False, state='normal', strings=None, ui_scale=0):
    notices = Notices()
    settings = ScaleSettings(snapshot, ui_scale, notices)
    layout = Layout(preview_root(snapshot), settings.rates)
    selected = snapshot['selected']
    focus = snapshot['context'] if context else selected
    if focus not in layout.nodes:
        raise ValueError('Selected object is outside the preview subtree')
    if settings.modern and ui_scale and not layout.scaled[focus]:
        notices.add('Масштабирование не включено для окна', layout.node_paths[focus])
    crop = layout.rect(focus)
    # Isolated rotated controls need the transformed bounds to avoid clipping.
    focus_transform, _ = rotation_transform(layout.nodes[focus]['properties'], crop)
    crop = focus_transform.mapRect(crop)
    if crop.width() <= 0 or crop.height() <= 0:
        raise ValueError('The selected element has zero size')
    margin = 12
    logical_w, logical_h = crop.width() + margin * 2, crop.height() + margin * 2
    scale = min(1.0, 2048 / logical_w, 2048 / logical_h)
    image = QImage(max(1, math.ceil(logical_w * scale)), max(1, math.ceil(logical_h * scale)), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor('#252a30'))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.scale(scale, scale)
    painter.translate(margin - crop.x(), margin - crop.y())
    painter.setClipRect(crop)
    textures = []
    current_element = ''
    current_rates = (1., 1.)

    def placeholder(rect, label):
        painter.fillRect(rect, QColor(80, 87, 96, 160))
        painter.setPen(QPen(QColor('#a6abb2'), 1, Qt.PenStyle.DashLine))
        painter.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.setFont(QFont('Arial', 8))
        painter.drawText(rect.adjusted(3, 2, -3, -2), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, label)

    def texture(rect, name, tiled=False, source=None, opacity=1.0, natural=False):
        if not useful(name):
            return False
        try:
            picture, grid = resources.image(name)
            painter.save()
            try:
                painter.setOpacity(max(0, min(opacity, 1)))
                if source is not None:
                    painter.drawImage(rect, picture, source)
                elif tiled:
                    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
                    # QPixmap is GUI-thread-only: tile QImage directly with a bound.
                    count = 0
                    tile_w, tile_h = picture.width() * current_rates[0], picture.height() * current_rates[1]
                    for y in range(math.ceil(rect.height() / tile_h)):
                        for x in range(math.ceil(rect.width() / tile_w)):
                            count += 1
                            if count > 10000:
                                raise ValueError('Texture tiling limit exceeded')
                            painter.drawImage(QRectF(rect.x() + x * tile_w, rect.y() + y * tile_h, tile_w, tile_h), picture)
                elif natural and not grid:
                    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
                    painter.drawImage(QRectF(rect.x(), rect.y(), picture.width() * current_rates[0], picture.height() * current_rates[1]), picture)
                else:
                    draw_nine_slice(painter, rect, picture, grid, current_rates)
            finally:
                painter.restore()
            textures.append(name)
            return True
        except Exception as error:
            notices.add('Не удалось загрузить текстуру', current_element, f'{name}: {error}')
            return False

    def label(p, kind):
        literal = p.get('buttonNameText' if kind == 'Button' else 'text', '')
        if useful(literal):
            return literal
        ident = int(number(p.get('buttonName' if kind == 'Button' else 'sysstring'), -9999))
        if ident >= 0:
            if strings is not None and ident in strings:
                return strings[ident]
            notices.add('Строка SysString недоступна', current_element, f'#{ident}')
            return f'#{ident}'
        return ''

    def paint(node, force=False):
        nonlocal current_element, current_rates
        p, kind = node['properties'], node['type']
        if p.get('hidden') == 1 and not force and node['id'] != selected:
            return
        rect = layout.rect(node['id'])
        if rect.width() <= 0 or rect.height() <= 0:
            return
        current_element = layout.node_paths[node['id']]
        current_rates = settings.rates if layout.scaled[node['id']] else (1., 1.)
        painter.save()
        try:
            parent = layout.parents[node['id']]
            if p.get('useParentClipRect') == 1 and parent is not None:
                painter.setClipRect(layout.rect(parent), Qt.ClipOperation.IntersectClip)
            transform, rotation_warning = rotation_transform(p, rect)
            if rotation_warning:
                notices.add(rotation_warning, current_element, str(p.get('rotationAngle')))
            painter.setWorldTransform(transform, True)
            if kind in ('Window', 'ScrollArea'):
                if not texture(rect, p.get('backTex', '')):
                    painter.fillRect(rect, QColor(38, 43, 49, 220))
                    painter.setPen(QColor('#666f7b'))
                    painter.drawRect(rect)
            elif kind == 'Button':
                key = {'normal': 'normalTex', 'pressed': 'pushedTex', 'hover': 'highlightTex'}[state] if node['id'] == selected else 'normalTex'
                name = p.get(key, '')
                if not useful(name):
                    name = p.get('normalTex', '')
                if not texture(rect, name):
                    placeholder(rect, '')
            elif kind == 'Texture':
                opacity = number(p.get('alpha'), 255) / 255
                source = None
                if number(p.get('uSize')) > 0 and number(p.get('vSize')) > 0:
                    source = QRectF(number(p.get('u')), number(p.get('v')), number(p['uSize']), number(p['vSize']))
                if not texture(rect, p.get('file', ''), int(number(p.get('type'))) == 2, source, opacity, p.get('type') == 1):
                    placeholder(rect, f"Texture\n{p.get('file', p.get('name', ''))}")
                if useful(p.get('alphaMask')):
                    notices.add('Отдельная alphaMask не отображается', current_element, p['alphaMask'])
                if p.get('colorModify', 0xffffffff) != 0xffffffff:
                    notices.add('Цвет colorModify не применяется', current_element)
            elif kind == 'TextBox':
                texture(rect, p.get('backTex', ''))
            else:
                placeholder(rect, kind + '\n' + p.get('name', ''))
                notices.add('Неподдерживаемый тип контрола', current_element, kind)
            if kind in ('Button', 'TextBox'):
                caption = label(p, kind)
                if caption:
                    font, font_name = settings.font(p, layout.scaled[node['id']])
                    if settings.modern:
                        notices.add('Шрифт отображается приближённо', current_element, font_name or 'Arial')
                    painter.setFont(font)
                    color = p.get('textColor', p.get('fontColor') if p.get('useFont') == 1 else 0xffdcdcdc)
                    painter.setPen(QColor.fromRgba(int(color or 0xffdcdcdc) & 0xffffffff))
                    align = Qt.AlignmentFlag.AlignCenter
                    if kind == 'TextBox':
                        horizontal = {1: Qt.AlignmentFlag.AlignLeft, 2: Qt.AlignmentFlag.AlignHCenter, 3: Qt.AlignmentFlag.AlignRight}.get(p.get('textAlign'), Qt.AlignmentFlag.AlignLeft)
                        vertical = {1: Qt.AlignmentFlag.AlignTop, 2: Qt.AlignmentFlag.AlignVCenter, 3: Qt.AlignmentFlag.AlignBottom}.get(p.get('textVAlign'), Qt.AlignmentFlag.AlignVCenter)
                        align = horizontal | vertical
                    painter.drawText(rect.adjusted(2, 0, -2, 0), align, caption)
            if kind == 'ScrollArea':
                painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
            def order(child):
                cp = child['properties']
                return -2 if cp.get('alwaysOnBack') == 1 else -1 if child['type'] == 'Texture' and cp.get('layer') == 2 else 1 if cp.get('alwaysOnTop') == 1 else 0
            for child in sorted(node['children'], key=order):
                paint(child)
            if context and node['id'] == selected:
                painter.setPen(QPen(QColor('#ffbf69'), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))
        finally:
            painter.restore()

    try:
        paint(layout.nodes[focus], True)
    finally:
        painter.end()
    for warning in layout.warnings:
        reason, _, detail = warning.partition(': ')
        notices.add(reason, detail=detail)
    if scale < 1:
        notices.add('Большой предпросмотр уменьшен до 2048 пикселей')
    return RenderResult(image, selected, snapshot['revision'], notices.messages(),
                        list(dict.fromkeys(textures)), {key: (r.x(), r.y(), r.width(), r.height()) for key, r in layout.rects.items()},
                        (logical_w, logical_h), notices.grouped())
