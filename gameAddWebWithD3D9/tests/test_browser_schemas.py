"""Gracia's browser layout transfers controls from an independent HF document."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_gracia_preparation_loads_both_profiles_and_matches_full_catalog(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'interface_editor/app'))
    from _interface_core import Document
    import schema_catalog

    source = ROOT / 'gameAddWebWithD3D9/profiles/gracia'
    monkeypatch.syspath_prepend(str(source))
    spec = importlib.util.spec_from_file_location('browser_gracia_prepare', source / 'prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path / 'gracia'
    module.SHARED = tmp_path / 'hf'
    (module.ROOT / 'inputs').mkdir(parents=True)
    (module.ROOT / 'result/system').mkdir(parents=True)
    (module.SHARED / 'result/system').mkdir(parents=True)
    (module.SHARED / 'options.config').write_text('{}')
    # Native patching is outside this UI regression; an existing Core is preserved.
    core = module.ROOT / 'result/system/Core.dll'
    core.write_bytes(b'synthetic-existing-core')

    def children(doc, node):
        return next(n['id'] for n in doc.children(node) if n['name'] == 'children')

    for prefix, folder in [('ct24', module.ROOT / 'inputs'), ('ct26', module.SHARED / 'result/system')]:
        doc = Document(schema_catalog.profile_text(prefix + '.XDAT'))
        doc.create(prefix + '.XDAT')
        windows = next(n['id'] for n in doc.children() if n['name'] == 'windows')
        template = doc.add_configured(windows, prefix + '.Window',
                                     {'name': 'MacroListWnd' if prefix == 'ct24' else 'BrowserWnd'})
        for kind in ('Button', 'EditBox', 'Texture'):
            doc.add_configured(children(doc, template), prefix + '.' + kind, {'name': 'Fixture' + kind})
        if prefix == 'ct24':
            login = doc.add_configured(windows, prefix + '.Window', {'name': 'LoginMenuWnd'})
            doc.add_configured(children(doc, login), prefix + '.Button', {'name': 'btnReplay'})
        (folder / 'Interface.xdat').write_bytes(doc.serialize())

    module.prepare_xdat()
    result = (module.ROOT / 'result/system/Interface.xdat').read_bytes()
    full = schema_catalog.catalog_text()
    monkeypatch.setattr(schema_catalog, 'profile_text', lambda *args: full)
    module.prepare_xdat()
    assert (module.ROOT / 'result/system/Interface.xdat').read_bytes() == result
    assert core.read_bytes() == b'synthetic-existing-core'
    doc = Document(full)
    doc.load_bytes(result, 'ct24.XDAT')
    assert doc.search('BrowserWnd')['matches']
    assert doc.search('btnBrowser')['matches']
