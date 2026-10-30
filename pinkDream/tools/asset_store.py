"""Immutable content-addressed assets shared by themes and client revisions."""
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from PIL import Image
from inventory import ROOT

STORE = ROOT / 'assets/objects/sha256'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def put(data, suffix):
    h = digest(data)
    path = STORE / h[:2] / (h + '.' + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if digest(path.read_bytes()) != h:
            raise ValueError('Corrupted asset store object')
    else:
        fd, name = tempfile.mkstemp(prefix='.object-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            try:
                os.link(name, path)  # Publish complete bytes without replacing an existing object.
            except FileExistsError:
                if digest(path.read_bytes()) != h:
                    raise ValueError('Corrupted concurrently published object')
        finally:
            Path(name).unlink(missing_ok=True)
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': h, 'bytes': len(data)}


def read(ref):
    path = (ROOT / ref['path']).resolve()
    if not path.is_relative_to(STORE.resolve()):
        raise ValueError('Object path escapes store')
    data = path.read_bytes()
    if digest(data) != ref['sha256']:
        raise ValueError(f'Asset hash mismatch: {path}')
    return data


def picture(image, fmt='PNG'):
    out = io.BytesIO()
    image.save(out, format=fmt)
    return put(out.getvalue(), fmt.lower())


def load_image(ref):
    return Image.open(io.BytesIO(read(ref))).convert('RGBA')


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
