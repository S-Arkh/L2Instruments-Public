"""Generate original sample button artwork and a separate reusable texture project."""
import argparse
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QApplication
from texture_project import TextureProject


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'examples/L2UI_Custom')
    args = parser.parse_args()
    application = QApplication.instance() or QApplication([])
    project = TextureProject.create(args.out, 'L2UI_Custom')
    artwork = project.root / 'artwork'
    artwork.mkdir()
    for state, top, bottom in (('Normal', '#447fa2', '#1b3d57'), ('Pressed', '#172d3b', '#315970'), ('Hover', '#70b7d3', '#326787')):
        image = QImage(128, 32, QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, 32)
        gradient.setColorAt(0, QColor(top)); gradient.setColorAt(1, QColor(bottom))
        painter.setBrush(gradient); painter.setPen(QPen(QColor('#a6d6e8'), 1))
        painter.drawRoundedRect(QRectF(1, 1, 126, 30), 5, 5)
        painter.end()
        filename = artwork / (state + '.png')
        if not image.save(str(filename)): raise RuntimeError('Could not save demo artwork')
        project.add_image(filename, 'NativeTest_' + state, 'Buttons')
    print(project.build())
    print(project.file)


if __name__ == '__main__': main()
