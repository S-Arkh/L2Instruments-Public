"""Editable image projects; generated UTX files are separate from stock assets."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QPainter
from _interface_core import build_texture_package, TextureStore

IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}\Z')
RESERVED_PACKAGES = {'core', 'engine', 'editor', 'l2ui', 'l2ui_ch3', 'l2ui_ct1', 'l2font', 'interface', 'nwindow'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_bytes(path, data, backup=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if backup and path.exists():
            atomic_bytes(path.with_name(path.name + '.bak'), path.read_bytes())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def image_rgba(file, pad=False):
    reader = QImageReader(str(file))
    size = reader.size()
    if not size.isValid() or not 0 < size.width() <= 4096 or not 0 < size.height() <= 4096:
        raise ValueError('Image dimensions must be between 1 and 4096')
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString())
    w, h = image.width(), image.height()
    pw, ph = 1 << (w - 1).bit_length(), 1 << (h - 1).bit_length()
    if (w, h) != (pw, ph):
        if not pad:
            raise ValueError('Image needs transparent padding to power-of-two dimensions')
        expanded = QImage(pw, ph, QImage.Format.Format_RGBA8888)
        expanded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(expanded)
        painter.drawImage(0, 0, image)
        painter.end()
        image = expanded
    return image.convertToFormat(QImage.Format.Format_RGBA8888), w, h


def package_guid(path):
    path = Path(path)
    with path.open('rb') as f:
        raw = f.read(92)
    if raw.startswith('Lineage2Ver121'.encode('utf-16le')):
        key = sum(path.name.lower().encode('ascii')) & 255
        raw = bytes(v ^ key for v in raw[28:])
    if len(raw) < 52 or raw[:4] != b'\xc1\x83\x2a\x9e':
        raise ValueError('Existing file is not a supported custom package')
    return raw[36:52].hex()


class TextureProject:
    def __init__(self, file):
        self.file = Path(file).resolve()
        raw = self.file.read_bytes()
        self.data = json.loads(raw.decode('utf-8'))
        self.disk_hash = sha(raw)
        self._validate()

    @classmethod
    def create(cls, directory, name='L2UI_Custom'):
        directory = Path(directory)
        if not IDENTIFIER.fullmatch(name) or name.casefold() in RESERVED_PACKAGES:
            raise ValueError('Choose a new non-stock package name using Latin letters, digits and underscores')
        if directory.exists() and any(directory.iterdir()):
            raise ValueError('Choose a new or empty project directory')
        directory.mkdir(parents=True, exist_ok=True)
        data = dict(format='interface-texture-project', version=1, profile='hf125_38_rgba8',
                    package=name, guid=uuid.uuid4().hex, revision=0, assets=[])
        atomic_bytes(directory / 'project.json', json.dumps(data, indent=2).encode('utf-8'))
        return cls(directory / 'project.json')

    @property
    def root(self):
        return self.file.parent

    @property
    def output(self):
        return self.root / 'output' / (self.data['package'] + '.utx')

    def asset_path(self, relative):
        path = (self.root / relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(self.root):
            raise ValueError('Asset path must remain inside the project')
        return path

    def _validate(self):
        d = self.data
        if d.get('format') not in ('interface-texture-project', 'xdat-texture-project') or d.get('version') != 1 or d.get('profile') != 'hf125_38_rgba8':
            raise ValueError('Unsupported texture project format')
        if not IDENTIFIER.fullmatch(d['package']) or d['package'].casefold() in RESERVED_PACKAGES:
            raise ValueError('Invalid or stock package name')
        if len(bytes.fromhex(d['guid'])) != 16 or type(d['revision']) is not int or d['revision'] < 0:
            raise ValueError('Invalid project identity')
        seen, ids, groups = set(), set(), {}
        for a in d['assets']:
            if not IDENTIFIER.fullmatch(a['name']) or a['name'].casefold() == 'none' or a['group'] and not IDENTIFIER.fullmatch(a['group']):
                raise ValueError('Invalid texture/group name')
            key = (a['group'] + '.' + a['name']).casefold()
            if key in seen or a['id'] in ids:
                raise ValueError('Duplicate texture name or ID')
            seen.add(key); ids.add(a['id'])
            if a['group'].casefold() in groups and groups[a['group'].casefold()] != a['group']:
                raise ValueError('Use the same spelling for a group')
            groups[a['group'].casefold()] = a['group']
            for key in ('image', 'source'):
                if not self.asset_path(a[key]).is_file():
                    raise ValueError('Missing project image: ' + a[key])
            if not (0 < a['content_width'] <= a['width'] <= 4096 and 0 < a['content_height'] <= a['height'] <= 4096):
                raise ValueError('Invalid image dimensions')

    def reference(self, asset):
        return '.'.join(p for p in (self.data['package'], asset['group'], asset['name']) if p)

    def asset(self, asset_id):
        return next(a for a in self.data['assets'] if a['id'] == asset_id)

    def _commit(self, data):
        if sha(self.file.read_bytes()) != self.disk_hash:
            raise ValueError('Project changed externally; reopen it first')
        data['format'] = 'interface-texture-project'
        raw = json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8')
        atomic_bytes(self.file, raw, backup=True)
        self.data, self.disk_hash = data, sha(raw)

    def add_image(self, source, name, group='Buttons', pad=False, replace_id=None):
        source = Path(source)
        if not IDENTIFIER.fullmatch(name) or name.casefold() == 'none' or group and (not IDENTIFIER.fullmatch(group) or group.casefold() == 'none'):
            raise ValueError('Invalid texture/group name')
        for asset in self.data['assets']:
            if asset['group'].casefold() == group.casefold():
                group = asset['group']
            if asset['id'] != replace_id and (asset['group'] + '.' + asset['name']).casefold() == (group + '.' + name).casefold():
                raise ValueError('Texture name already exists')
        image, cw, ch = image_rgba(source, pad)
        nonce = uuid.uuid4().hex
        folder = self.root / 'images'
        folder.mkdir(exist_ok=True)
        original = folder / (nonce + '.source' + source.suffix.lower())
        normalized = folder / (nonce + '.png')
        try:
            atomic_bytes(original, source.read_bytes())
            from preview_widget import save_png
            save_png(image, normalized)
            record = dict(id=replace_id or uuid.uuid4().hex, name=name, group=group,
                          image=normalized.relative_to(self.root).as_posix(), source=original.relative_to(self.root).as_posix(),
                          source_name=source.name, width=image.width(), height=image.height(),
                          content_width=cw, content_height=ch, alpha=image.hasAlphaChannel())
            data = copy.deepcopy(self.data)
            if replace_id:
                index = next(i for i, a in enumerate(data['assets']) if a['id'] == replace_id)
                data['assets'][index] = record
            else:
                data['assets'].append(record)
            data['revision'] += 1
            self._commit(data)
            return record
        except Exception:
            original.unlink(missing_ok=True)
            normalized.unlink(missing_ok=True)
            raise

    def signatures(self):
        result = {}
        for a in self.data['assets']:
            stat = self.asset_path(a['image']).stat()
            result[a['image']] = [stat.st_size, stat.st_mtime_ns]
        return result

    def build_info(self):
        path = self.root / 'output/build.json'
        try:
            info = json.loads(path.read_text(encoding='utf-8'))
            stat = self.output.stat()
            if info['revision'] == self.data['revision'] and info['guid'] == self.data['guid'] and info['output_stat'] == [stat.st_size, stat.st_mtime_ns] and info['images'] == self.signatures():
                return info
        except (OSError, ValueError, KeyError):
            pass
        return None

    def build(self):
        if sha(self.file.read_bytes()) != self.disk_hash:
            raise ValueError('Project changed externally; reopen it first')
        self._validate()
        signatures = self.signatures()
        inputs = []
        for a in self.data['assets']:
            image, _, _ = image_rgba(self.asset_path(a['image']))
            if (image.width(), image.height()) != (a['width'], a['height']):
                raise ValueError('Image dimensions changed; replace the image through the project manager')
            inputs.append(dict(name=a['name'], group=a['group'], width=a['width'], height=a['height'],
                               content_width=a['content_width'], content_height=a['content_height'], rgba=bytes(image.constBits())))
        data = build_texture_package(self.data['package'], inputs, bytes.fromhex(self.data['guid']))
        self.output.parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='verify-', dir=self.output.parent) as temp:
            candidate = Path(temp) / self.output.name
            candidate.write_bytes(data)
            reader = TextureStore(temp)
            for a, expected in zip(self.data['assets'], inputs):
                actual = reader.load(self.reference(a))
                if actual['rgba'] != expected['rgba'] or actual['grid'] != [0, a['content_width'], a['content_width'], 0, a['content_height'], a['content_height']]:
                    raise ValueError('UTX pixel/layout verification failed')
        if signatures != self.signatures() or sha(self.file.read_bytes()) != self.disk_hash:
            raise ValueError('Project inputs changed while building')
        if self.output.exists() and package_guid(self.output) != self.data['guid']:
            raise ValueError('Output belongs to another package; choose a different project directory')
        atomic_bytes(self.output, data, backup=True)
        stat = self.output.stat()
        info = dict(package=self.data['package'], guid=self.data['guid'], revision=self.data['revision'],
                    profile=self.data['profile'], sha256=sha(data), output_stat=[stat.st_size, stat.st_mtime_ns],
                    images=signatures, textures=[self.reference(a) for a in self.data['assets']],
                    pixel_roundtrip=True, game_tested=False)
        atomic_bytes(self.output.parent / 'build.json', json.dumps(info, indent=2).encode('utf-8'))
        return self.output

    def install(self, directory):
        info = self.build_info()
        if not info:
            raise ValueError('Build the current project first')
        data = self.output.read_bytes()
        if sha(data) != info['sha256']:
            raise ValueError('Built package was changed externally')
        directory = Path(directory).resolve()
        if directory.name.casefold() == 'system':
            directory = directory.parent
        if directory.name.casefold() != 'systextures':
            directory = next((p for p in directory.iterdir() if p.is_dir() and p.name.casefold() == 'systextures'), None)
        if directory is None or not directory.is_dir():
            raise ValueError('Select the actual client SysTextures directory')
        target = directory / self.output.name
        existing = [p for p in directory.iterdir() if p.name.casefold() == target.name.casefold()]
        if existing:
            target = existing[0]
            if package_guid(target) != self.data['guid']:
                raise ValueError('Refusing to overwrite a stock or unrelated texture package')
        atomic_bytes(target, data, backup=True)
        return target
