"""Static HF mockups painted on QImage, suitable for background workers."""
from collections import OrderedDict
from dataclasses import dataclass
import math
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QFont
from _interface_core import TextureStore


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


class Layout:
    def __init__(self, root):
        self.nodes = {}
        self.parents = {}
        self.paths = {}
        self.names = {}
        self.rects = {}
        self.pending = set()
        self.warnings = []
        self.root = root['id']
        self.viewport = QRectF(0, 0, 1280, 720)

        def visit(node, parent=None, prefix=''):
            ident = node['id']
            self.nodes[ident] = node
            self.parents[ident] = parent
            name = node['properties'].get('name', str(ident))
            path = prefix + name
            self.paths[path.casefold()] = ident
            self.names.setdefault(name.casefold(), []).append(ident)
            for child in node['children']:
                visit(child, ident, path + '.')
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
            self.warnings.append('Unresolved layout reference: ' + name)
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
            self.warnings.append('Cyclic layout reference')
            return QRectF(0, 0, 100, 30)
        self.pending.add(node_id)
        node = self.nodes[node_id]
        p = node['properties']
        container = node['type'] in ('Window', 'ScrollArea')
        width, height = (320, 200) if container else (100, 28)
        if p.get('size') == 1:
            width = number(p.get('size_absolute_width'), width)
            height = number(p.get('size_absolute_height'), height)
            if p.get('size_absolute_values') == 0:
                reference = self.reference(node_id, p.get('size_percent_window', ''))
                width += reference.width() * number(p.get('size_percent_width'))
                height += reference.height() * number(p.get('size_percent_height'))
        width, height = max(0, min(width, 8192)), max(0, min(height, 8192))
        parent = self.parents[node_id]
        reference = self.rect(parent) if parent is not None else self.viewport
        x, y = reference.x(), reference.y()
        if node_id == self.root:
            x = y = 0  # Crop to the window, not its screen position.
        elif p.get('usePosition') == 1:
            reference = self.reference(node_id, p.get('relativeTo', ''))
            rx, ry = self.anchor(p.get('relativePoint'))
            ax, ay = self.anchor(p.get('anchorPoint'))
            x = reference.x() + reference.width() * rx - width * ax + number(p.get('anchor_x'))
            y = reference.y() + reference.height() * ry - height * ay + number(p.get('anchor_y'))
        rect = QRectF(x, y, width, height)
        self.rects[node_id] = rect
        self.pending.remove(node_id)
        return rect


def draw_nine_slice(painter, destination, image, grid):
    """Split9 values are cumulative source coordinates, not border widths."""
    if not grid:
        painter.drawImage(destination, image)
        return
    x1, x2, x3, y1, y2, y3 = grid
    if not (0 <= x1 <= x2 <= x3 <= image.width() and 0 <= y1 <= y2 <= y3 <= image.height() and x3 and y3):
        painter.drawImage(destination, image)
        return

    def axis(a, b, c, size):
        # A zero stretch region is a fixed-height strip (e.g. Button_DF).
        if a == b:
            return [0, c], [0, size]
        left, right = a, c - b
        scale = min(1.0, size / (left + right)) if left + right else 1.0
        return [0, a, b, c], [0, left * scale, size - right * scale, size]
    sx, dx = axis(x1, x2, x3, destination.width())
    sy, dy = axis(y1, y2, y3, destination.height())
    for yi in range(len(sy) - 1):
        for xi in range(len(sx) - 1):
            src = QRectF(sx[xi], sy[yi], sx[xi + 1] - sx[xi], sy[yi + 1] - sy[yi])
            dst = QRectF(destination.x() + dx[xi], destination.y() + dy[yi], dx[xi + 1] - dx[xi], dy[yi + 1] - dy[yi])
            if src.width() > 0 and src.height() > 0 and dst.width() > 0 and dst.height() > 0:
                painter.drawImage(dst, image, src)


def render_preview(snapshot, resources, context=False, state='normal', strings=None):
    if snapshot['schema'] != 'ct26.XDAT':
        raise ValueError('Preview currently supports High Five (ct26)')
    layout = Layout(snapshot['root'])
    selected = snapshot['selected']
    focus = snapshot['context'] if context else selected
    if focus not in layout.nodes:
        raise ValueError('Selected object is outside the preview subtree')
    crop = layout.rect(focus)
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
    warnings = []
    textures = []

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
                    for y in range(math.ceil(rect.height() / picture.height())):
                        for x in range(math.ceil(rect.width() / picture.width())):
                            count += 1
                            if count > 10000:
                                raise ValueError('Texture tiling limit exceeded')
                            painter.drawImage(QPointF(rect.x() + x * picture.width(), rect.y() + y * picture.height()), picture)
                elif natural and not grid:
                    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
                    painter.drawImage(QPointF(rect.x(), rect.y()), picture)
                else:
                    draw_nine_slice(painter, rect, picture, grid)
            finally:
                painter.restore()
            textures.append(name)
            return True
        except Exception as error:
            warnings.append(f'{name}: {error}')
            return False

    def label(p, kind):
        literal = p.get('buttonNameText' if kind == 'Button' else 'text', '')
        if useful(literal):
            return literal
        ident = int(number(p.get('buttonName' if kind == 'Button' else 'sysstring'), -9999))
        if ident >= 0:
            if strings is not None and ident in strings:
                return strings[ident]
            warnings.append(f'SysString #{ident}: ' + ('localized string is not loaded' if strings is None else 'ID not found in the selected language'))
            return f'#{ident}'
        return ''

    def paint(node, force=False):
        p, kind = node['properties'], node['type']
        if p.get('hidden') == 1 and not force and node['id'] != selected:
            return
        rect = layout.rect(node['id'])
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        try:
            parent = layout.parents[node['id']]
            if p.get('useParentClipRect') == 1 and parent is not None:
                painter.setClipRect(layout.rect(parent), Qt.ClipOperation.IntersectClip)
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
                    warnings.append('Separate alphaMask is not rendered: ' + p['alphaMask'])
                if p.get('colorModify', 0xffffffff) != 0xffffffff:
                    warnings.append('Texture colorModify is approximated by the original image')
            elif kind == 'TextBox':
                texture(rect, p.get('backTex', ''))
            else:
                placeholder(rect, kind + '\n' + p.get('name', ''))
                warnings.append('Unsupported control: ' + kind)
            if kind in ('Button', 'TextBox'):
                caption = label(p, kind)
                if caption:
                    font = QFont('Arial', 10)
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
        finally:
            painter.restore()

    try:
        paint(layout.nodes[focus], True)
        if context and selected in layout.nodes:
            painter.setPen(QPen(QColor('#ffbf69'), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(layout.rect(selected).adjusted(1, 1, -1, -1))
    finally:
        painter.end()
    warnings.extend(layout.warnings)
    if scale < 1:
        warnings.append('Large preview reduced to 2048 pixels')
    return RenderResult(image, selected, snapshot['revision'], list(dict.fromkeys(warnings)),
                        list(dict.fromkeys(textures)), {key: (r.x(), r.y(), r.width(), r.height()) for key, r in layout.rects.items()},
                        (logical_w, logical_h))
