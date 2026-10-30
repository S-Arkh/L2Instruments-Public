"""Offscreen UI smoke test and screenshot on an actual client XDAT."""
import argparse
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from PySide6.QtWidgets import QApplication
from main import Editor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/editor.png')
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--right-query', default='btnOption')
    parser.add_argument('--language', choices=('ru', 'en'), default='ru')
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--strings', type=Path)
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle('Fusion')
    window = Editor()
    window.set_language(args.language)
    if args.resources:
        window.set_resources(str(args.resources))
    if args.strings:
        from _interface_core import SysStrings
        strings = SysStrings(); strings.load(str(args.strings))
        window.strings.attach(strings, 'English')
    errors = []
    window.error = errors.append
    window.resize(1600, 900)
    window.show()
    window.load_file(str(args.client), 'ct26.XDAT')
    deadline = time.monotonic() + 30
    while window.busy or window.tasks:
        app.processEvents()
        if time.monotonic() > deadline:
            raise RuntimeError('UI task timed out')
        time.sleep(0.01)
    if errors:
        raise RuntimeError('\n'.join(errors))
    for pane, query in zip(window.panes, ('btnCredit', args.right_query)):
        node = next(n for n in window.document.search(query)['matches'] if not window.document.info(n)['list'])
        source = window.model.index_for_id(node)
        index = pane.proxy.mapFromSource(source)
        parent = index.parent()
        while parent.isValid():
            pane.tree.expand(parent)
            parent = parent.parent()
        pane.tree.setCurrentIndex(index)
        pane.tree.scrollTo(index)
    window.sync_scroll.setChecked(True)
    window.compare_action.setChecked(args.compare)
    if args.preview:
        for pane in window.panes:
            pane.tabs.setCurrentIndex(1)
        deadline = time.monotonic() + 30
        while any(p.preview.result is None for p in window.panes) or window.tasks:
            app.processEvents()
            if time.monotonic() > deadline:
                raise RuntimeError('Preview timed out: ' + ' | '.join(p.preview.details.toPlainText() for p in window.panes))
            time.sleep(.01)
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assert window.grab().save(str(args.output))
    window.close()
    app.processEvents()
    print(args.output)


if __name__ == '__main__': main()
