"""Release names must remain safe as tags, filenames and shell arguments."""
import importlib
import io
import json
from pathlib import Path
import sys

import pytest


@pytest.fixture
def release_tools(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'tools'))
    return importlib.import_module('release_windows')


@pytest.mark.parametrize('version', ['0.6.0', '0.6.0-rc.1', '1.2.3-preview-2'])
def test_release_identity_accepts_versions(release_tools, version):
    release_tools.validate_identity(version, 'a' * 40)


@pytest.mark.parametrize('version', ['', '../1.2.3', '1.2', 'v1.2.3',
                                     '1.2.3;echo token', '1.2.3\n', '1.2.3-'])
def test_release_identity_rejects_unsafe_or_invalid_versions(release_tools, version):
    with pytest.raises(ValueError, match='Version'):
        release_tools.validate_identity(version, 'a' * 40)


@pytest.mark.parametrize('revision', ['main', 'a' * 7, 'g' * 40, 'a' * 40 + '\n'])
def test_release_identity_requires_exact_commit(release_tools, revision):
    with pytest.raises(ValueError, match='Revision'):
        release_tools.validate_identity('0.6.0', revision)


def test_release_validation_removes_development_environment(release_tools, monkeypatch):
    monkeypatch.setenv('SYSTEMROOT', 'C:/Windows')
    monkeypatch.setenv('PATH', 'development-tools')
    monkeypatch.setenv('PYTHONPATH', 'source-tree')
    monkeypatch.setenv('PYTHONHOME', 'installed-python')
    monkeypatch.setenv('QT_PLUGIN_PATH', 'installed-qt')
    monkeypatch.setenv('PYSIDE6_DESIGNER_PLUGINS', 'source-plugins')
    env = release_tools.isolated_environment()
    assert 'development-tools' not in env['PATH']
    assert not {'PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'PYSIDE6_DESIGNER_PLUGINS'} & env.keys()
    assert env['PYTHONDONTWRITEBYTECODE'] == '1'
    assert env['QT_QPA_PLATFORM'] == 'offscreen'


@pytest.mark.parametrize('cached', [False, True])
def test_release_rejects_corrupt_inputs_before_packaging(release_tools, monkeypatch, tmp_path, cached):
    cache = tmp_path / 'cache'
    cache.mkdir()
    first = json.loads((release_tools.TOOLS / 'portable_inputs.json').read_text())[0]
    target = cache / first['name']
    if cached:
        target.write_bytes(b'corrupt archive')
    monkeypatch.setattr(release_tools.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(b'corrupt archive'))
    monkeypatch.setattr(sys, 'argv', ['release_windows', '--version', '0.6.0', '--revision', 'a' * 40,
                                    '--module', str(tmp_path / 'missing.pyd'), '--work', str(tmp_path / 'work'),
                                    '--cache', str(cache)])
    with pytest.raises(ValueError, match='hash mismatch'):
        release_tools.main()
    assert not (tmp_path / 'work/publish').exists()
    assert not list(cache.glob('*.download'))
    assert target.exists() == cached
